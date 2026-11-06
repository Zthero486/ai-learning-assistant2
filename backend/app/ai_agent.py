# -*- coding: utf-8 -*-
"""AI 学习代理（v3）：让软件里配置的大模型**真正能操作软件**。

设计要点
- 工具即权限边界：模型只能调用本文件 `TOOLS` 里登记的 13 个函数，读写都强制带
  `user_id`，写入的 node_code 必须落在当前选中的那一门课里。
- 不提供任何删除类工具：AI 可以新建、补充，但不能删学生的数据。
- 只读工具（8 个）任何情况下都开；写入工具（5 个）受 `allow_write` 开关控制。
- 多轮 tool-calling 循环有硬上限（轮数 6 / 调用 16），防止模型打转烧额度。
- 所有工具返回值为 dict，出错也返回 dict（不抛异常打断对话），便于模型自我纠正。

为什么不放在 main.py：main 已经是上帝模块，这一层是纯逻辑，独立出来才能单测。
依赖通过 AgentContext 注入，避免和 main 循环导入。
"""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Callable

from . import ai_helper, qushi

MAX_ROUNDS = 6          # 一次对话最多几轮「模型→工具→模型」
MAX_TOOL_CALLS = 16     # 一次对话最多执行多少次工具
MAX_TOOL_RESULT = 3000  # 单个工具结果回灌给模型的字符上限
MAX_MATERIAL_CHARS = 20000   # AI 生成资料入库的字数上限
MAX_QUESTIONS_PER_CALL = 10

EXAM_TYPES = {
    "recall": "史实识记",
    "sequence": "时序定位",
    "argument": "史论结合",
    "apply": "现实联系",
}


class AgentContext:
    """一次对话的上下文：谁、学哪门课、怎么连库。"""

    def __init__(self, uid: int, track: str, conn_factory: Callable[[], sqlite3.Connection],
                 now_fn: Callable[[], str]):
        self.uid = uid
        self.track = track
        self.conn = conn_factory
        self.now = now_fn

    @property
    def track_name(self) -> str:
        t = qushi.track_map().get(self.track)
        return t["name"] if t else ""

    def node_ok(self, code: str) -> bool:
        """章节必须存在，且属于当前课程（防止 AI 把党史内容写到别的课里）。"""
        if not code or not code.startswith(self.track + "-"):
            return False
        conn = self.conn()
        try:
            return qushi.node(conn, code) is not None
        finally:
            conn.close()

    def path_of(self, code: str) -> str:
        conn = self.conn()
        try:
            return qushi.path_text(conn, code)
        finally:
            conn.close()


def _clip(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "……"


def _as_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ==================== 只读工具 ====================

def _tool_list_syllabus(ctx: AgentContext, args: dict) -> dict:
    """章节树；可按章名/章号收窄，避免一次吐 193 行。"""
    conn = ctx.conn()
    try:
        chapters = qushi.tree(conn, ctx.track, ctx.uid)
    finally:
        conn.close()
    want = (args.get("chapter") or "").strip()
    if want:
        picked = [
            c for c in chapters
            if want in c["title"] or want == c["code"] or want in c["code"]
        ]
        if picked:
            chapters = picked
    lines = []
    for c in chapters:
        lines.append(f"{c['code']} {c['title']}（知识点 {c['kp']} / 题 {c['q']}）")
        for s in c["sections"]:
            lines.append(f"  {s['code']} {s['title']}（kp {s['kp']}）")
    return {
        "track": ctx.track,
        "track_name": ctx.track_name,
        "chapter_count": len(chapters),
        "text": "\n".join(lines)[:6000],
        "hint": "写入知识点/资料时请用上面的节 code（level 2 优先），不要用章 code。",
    }


def _tool_find_node(ctx: AgentContext, args: dict) -> dict:
    keyword = (args.get("keyword") or "").strip()
    if not keyword:
        return {"ok": False, "error": "keyword 不能为空"}
    conn = ctx.conn()
    try:
        rows = conn.execute(
            "SELECT code, level, title, period FROM syllabus_nodes "
            "WHERE track=? AND title LIKE ? ORDER BY level, order_no LIMIT 20",
            (ctx.track, f"%{keyword}%"),
        ).fetchall()
    finally:
        conn.close()
    return {
        "matched": len(rows),
        "nodes": [
            {"code": r["code"], "level": r["level"], "title": r["title"], "path": ctx.path_of(r["code"])}
            for r in rows
        ],
        "hint": "没匹配到就换更短的关键词（如「遵义」而不是「遵义会议的意义」）。" if not rows else "",
    }


def _tool_search_content(ctx: AgentContext, args: dict) -> dict:
    """全库检索：史料片段 + 知识点 + 时间轴事件，三类一起返回。"""
    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query 不能为空"}
    limit = min(_as_int(args.get("limit"), 5) or 5, 8)
    conn = ctx.conn()
    try:
        mats = conn.execute(
            "SELECT id, title, content, node_code FROM materials WHERE user_id=?", (ctx.uid,)
        ).fetchall()
        scored = []
        for m in mats:
            for chunk in ai_helper.chunk_text(m["content"], 500):
                score = ai_helper.keyword_score(query, chunk)
                if score > 0:
                    scored.append((score, m["id"], m["title"], m["node_code"], chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        seen, snippets = set(), []
        for score, mid, title, code, chunk in scored:
            if mid in seen:
                continue
            seen.add(mid)
            snippets.append(
                {"material_id": mid, "title": title, "node_code": code, "excerpt": _clip(chunk, 420)}
            )
            if len(snippets) >= limit:
                break

        kps = [
            {"id": r["id"], "title": r["title"], "node_code": r["node_code"],
             "description": _clip(r["description"], 220)}
            for r in conn.execute(
                "SELECT id,title,node_code,description FROM knowledge_points "
                "WHERE user_id=? AND (title LIKE ? OR description LIKE ?) LIMIT 6",
                (ctx.uid, f"%{query}%", f"%{query}%"),
            )
        ]
        events = [
            {"id": r["id"], "title": r["title"], "year": r["year"], "node_code": r["node_code"],
             "digest": _clip(r["significance"] or r["impact"] or "", 160)}
            for r in conn.execute(
                "SELECT id,title,year,node_code,impact,significance FROM events "
                "WHERE user_id=? AND (title LIKE ? OR significance LIKE ? OR impact LIKE ?) LIMIT 6",
                (ctx.uid, f"%{query}%", f"%{query}%", f"%{query}%"),
            )
        ]
    finally:
        conn.close()
    return {
        "query": query,
        "materials": snippets,
        "knowledge_points": kps,
        "events": events,
        "hint": "引用史料时请说明出自哪篇（title + material_id）；资料里没有的内容要如实说「资料未涉及」。",
    }


def _tool_read_material(ctx: AgentContext, args: dict) -> dict:
    mid = _as_int(args.get("material_id"))
    if not mid:
        return {"ok": False, "error": "material_id 必须是数字"}
    offset = max(_as_int(args.get("offset"), 0) or 0, 0)
    length = min(_as_int(args.get("length"), 2500) or 2500, 6000)
    conn = ctx.conn()
    try:
        row = conn.execute(
            "SELECT id, title, content, node_code, filetype FROM materials WHERE id=? AND user_id=?",
            (mid, ctx.uid),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": f"资料 {mid} 不存在或不属于当前用户"}
    total = len(row["content"] or "")
    body = (row["content"] or "")[offset:offset + length]
    return {
        "material_id": mid,
        "title": row["title"],
        "node_code": row["node_code"],
        "filetype": row["filetype"],
        "total_chars": total,
        "offset": offset,
        "text": body,
        "has_more": offset + length < total,
        "hint": f"未完可再读 offset={offset + length}。" if offset + length < total else "已读完。",
    }


def _tool_list_knowledge_points(ctx: AgentContext, args: dict) -> dict:
    node_code = (args.get("node_code") or "").strip()
    keyword = (args.get("keyword") or "").strip()
    limit = min(_as_int(args.get("limit"), 30) or 30, 60)
    sql = ("SELECT id,title,node_code,exam_type,description FROM knowledge_points WHERE user_id=?")
    params = [ctx.uid]
    if node_code:
        sql += " AND node_code LIKE ?"
        params.append(f"{node_code}%")
    else:
        sql += " AND node_code LIKE ?"
        params.append(f"{ctx.track}-%")
    if keyword:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        params += [f"%{keyword}%", f"%{keyword}%"]
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    conn = ctx.conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return {
        "count": len(rows),
        "items": [
            {"id": r["id"], "title": r["title"], "node_code": r["node_code"],
             "exam_type": r["exam_type"], "description": _clip(r["description"], 160)}
            for r in rows
        ],
        "hint": "已有知识点不要重复创建；要出题请直接用这些 id。",
    }


def _tool_list_events(ctx: AgentContext, args: dict) -> dict:
    keyword = (args.get("keyword") or "").strip()
    y1, y2 = _as_int(args.get("year_from")), _as_int(args.get("year_to"))
    limit = min(_as_int(args.get("limit"), 30) or 30, 60)
    sql = "SELECT id,title,year,year_label,node_code,kind FROM events WHERE user_id=?"
    params = [ctx.uid]
    if keyword:
        sql += " AND (title LIKE ? OR significance LIKE ?)"
        params += [f"%{keyword}%", f"%{keyword}%"]
    if y1 is not None:
        sql += " AND year>=?"
        params.append(y1)
    if y2 is not None:
        sql += " AND year<=?"
        params.append(y2)
    sql += " ORDER BY year LIMIT ?"
    params.append(limit)
    conn = ctx.conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return {
        "count": len(rows),
        "items": [
            {"id": r["id"], "title": r["title"],
             "year": r["year_label"] or r["year"], "node_code": r["node_code"], "kind": r["kind"]}
            for r in rows
        ],
    }


def _tool_get_my_stats(ctx: AgentContext, args: dict) -> dict:
    conn = ctx.conn()
    try:
        totals = conn.execute(
            """SELECT (SELECT COUNT(*) FROM materials WHERE user_id=?) AS materials,
                      (SELECT COUNT(*) FROM knowledge_points WHERE user_id=?) AS kps,
                      (SELECT COUNT(*) FROM questions q JOIN knowledge_points k ON k.id=q.kp_id
                        WHERE k.user_id=?) AS questions,
                      (SELECT COUNT(*) FROM tasks WHERE user_id=? AND status!='done') AS open_tasks,
                      (SELECT COUNT(*) FROM practice_records WHERE user_id=?) AS attempts,
                      (SELECT COUNT(*) FROM wrong_book WHERE user_id=? AND resolved=0) AS unresolved_wrong""",
            (ctx.uid,) * 6,
        ).fetchone()
        per_kp = conn.execute(
            """SELECT k.id, k.title, COUNT(DISTINCT q.id) AS qn, COUNT(pr.id) AS attempts,
                      SUM(pr.correct) AS correct
               FROM knowledge_points k
               LEFT JOIN questions q ON q.kp_id=k.id
               LEFT JOIN practice_records pr ON pr.question_id=q.id
               WHERE k.user_id=? AND k.node_code LIKE ?
               GROUP BY k.id HAVING attempts>0 ORDER BY k.id""",
            (ctx.uid, f"{ctx.track}-%"),
        ).fetchall()
        due = conn.execute(
            "SELECT title, due_date FROM tasks WHERE user_id=? AND status!='done' "
            "AND due_date IS NOT NULL ORDER BY due_date LIMIT 5",
            (ctx.uid,),
        ).fetchall()
    finally:
        conn.close()
    weak = []
    for r in per_kp:
        acc = round((r["correct"] or 0) / r["attempts"] * 100, 1) if r["attempts"] else None
        if acc is not None and r["attempts"] >= 2 and acc < 60:
            weak.append({"kp_id": r["id"], "title": r["title"], "accuracy": acc, "attempts": r["attempts"]})
    return {
        "track": ctx.track_name,
        "totals": dict(totals),
        "weak_kps": weak,
        "upcoming_tasks": [{"title": d["title"], "due_date": d["due_date"]} for d in due],
        "hint": "给复习建议时请结合 weak_kps 与 unresolved_wrong，不要泛泛而谈。",
    }


def _tool_wrong_book(ctx: AgentContext, args: dict) -> dict:
    limit = min(_as_int(args.get("limit"), 10) or 10, 20)
    conn = ctx.conn()
    try:
        rows = conn.execute(
            """SELECT w.id, w.wrong_count, q.question, q.answer, q.type, k.title AS kp_title, k.id AS kp_id
               FROM wrong_book w
               JOIN questions q ON q.id=w.question_id
               JOIN knowledge_points k ON k.id=q.kp_id
               WHERE w.user_id=? AND w.resolved=0 AND k.node_code LIKE ?
               ORDER BY w.last_wrong_at DESC LIMIT ?""",
            (ctx.uid, f"{ctx.track}-%", limit),
        ).fetchall()
    finally:
        conn.close()
    return {
        "count": len(rows),
        "items": [
            {"wrong_id": r["id"], "kp_id": r["kp_id"], "kp_title": r["kp_title"], "type": r["type"],
             "question": _clip(r["question"], 200), "answer": _clip(r["answer"], 200),
             "wrong_count": r["wrong_count"]}
            for r in rows
        ],
    }


# ==================== 写入工具 ====================

def _tool_create_knowledge_point(ctx: AgentContext, args: dict) -> dict:
    title = (args.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "title 不能为空"}
    node_code = (args.get("node_code") or "").strip() or ctx.track
    if node_code != ctx.track and not ctx.node_ok(node_code):
        return {"ok": False, "error": f"章节 {node_code} 不属于当前课程，请先用 find_node 查正确的节 code"}
    exam_type = (args.get("exam_type") or "").strip()
    if exam_type and exam_type not in EXAM_TYPES:
        exam_type = ""
    conn = ctx.conn()
    try:
        dup = conn.execute(
            "SELECT id FROM knowledge_points WHERE user_id=? AND node_code=? AND title=?",
            (ctx.uid, node_code, title),
        ).fetchone()
        if dup:
            return {"ok": True, "id": dup["id"], "duplicated": True,
                    "message": f"已存在同名知识点（id={dup['id']}），未重复创建"}
        cur = conn.execute(
            "INSERT INTO knowledge_points"
            "(user_id,uuid,material_id,course,title,description,node_code,exam_type,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (ctx.uid, uuid.uuid4().hex, _as_int(args.get("material_id")),
             ctx.track_name, title, (args.get("description") or "").strip(),
             node_code, exam_type, ctx.now()),
        )
        conn.commit()
        kid = cur.lastrowid
    finally:
        conn.close()
    return {"ok": True, "id": kid, "node_code": node_code,
            "path": ctx.path_of(node_code), "message": f"已新建知识点「{title}」"}


def _tool_create_material(ctx: AgentContext, args: dict) -> dict:
    title = (args.get("title") or "").strip()
    content = (args.get("content") or "").strip()
    if not title or not content:
        return {"ok": False, "error": "title 与 content 都不能为空"}
    if len(content) < 80:
        return {"ok": False, "error": "正文太短（<80 字），史料要有实质内容"}
    if len(content) > MAX_MATERIAL_CHARS:
        return {"ok": False, "error": f"正文超过 {MAX_MATERIAL_CHARS} 字上限，请拆成多篇"}
    node_code = (args.get("node_code") or "").strip() or ctx.track
    if node_code != ctx.track and not ctx.node_ok(node_code):
        return {"ok": False, "error": f"章节 {node_code} 不属于当前课程"}
    conn = ctx.conn()
    try:
        dup = conn.execute(
            "SELECT id FROM materials WHERE user_id=? AND title=?", (ctx.uid, title)
        ).fetchone()
        if dup:
            return {"ok": True, "id": dup["id"], "duplicated": True,
                    "message": f"已存在同名资料（id={dup['id']}），未重复创建"}
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        cur = conn.execute(
            "INSERT INTO materials(user_id,uuid,title,course,filename,filetype,content,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (ctx.uid, uuid.uuid4().hex, title, ctx.track_name,
             f"ai-{stamp}.md", "markdown", content, ctx.now()),
        )
        conn.commit()
        mid = cur.lastrowid
    finally:
        conn.close()
    return {"ok": True, "id": mid, "chars": len(content), "node_code": node_code,
            "message": f"已把《{title}》（{len(content)} 字）存入史料笔记"}


def _tool_create_questions(ctx: AgentContext, args: dict) -> dict:
    kp_id = _as_int(args.get("kp_id"))
    if not kp_id:
        return {"ok": False, "error": "kp_id 必须是数字，请先用 list_knowledge_points 查询"}
    items = args.get("questions") or []
    if not isinstance(items, list) or not items:
        return {"ok": False, "error": "questions 必须是非空数组"}
    if len(items) > MAX_QUESTIONS_PER_CALL:
        return {"ok": False, "error": f"一次最多 {MAX_QUESTIONS_PER_CALL} 题"}
    conn = ctx.conn()
    try:
        kp = conn.execute(
            "SELECT id,title FROM knowledge_points WHERE id=? AND user_id=?", (kp_id, ctx.uid)
        ).fetchone()
        if not kp:
            return {"ok": False, "error": f"知识点 {kp_id} 不存在"}
        ids = []
        for q in items:
            question = str(q.get("question") or "").strip()
            answer = str(q.get("answer") or "").strip()
            if not question:
                continue
            cur = conn.execute(
                "INSERT INTO questions(user_id,uuid,kp_id,type,question,answer,source,created_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (ctx.uid, uuid.uuid4().hex, kp_id, str(q.get("type") or "简答"),
                 question, answer, "ai", ctx.now()),
            )
            ids.append(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "created": len(ids), "ids": ids, "kp_title": kp["title"],
            "message": f"已为「{kp['title']}」新增 {len(ids)} 道题"}


def _tool_create_task(ctx: AgentContext, args: dict) -> dict:
    title = (args.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "title 不能为空"}
    due = (args.get("due_date") or "").strip() or None
    if due:
        try:
            datetime.fromisoformat(due)
        except ValueError:
            return {"ok": False, "error": "due_date 需形如 2026-11-12"}
    conn = ctx.conn()
    try:
        cur = conn.execute(
            "INSERT INTO tasks(user_id,uuid,course,kp_id,title,description,due_date,status,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (ctx.uid, uuid.uuid4().hex, ctx.track_name, _as_int(args.get("kp_id")),
             title, (args.get("description") or "").strip(), due, "todo", ctx.now()),
        )
        conn.commit()
        tid = cur.lastrowid
    finally:
        conn.close()
    return {"ok": True, "id": tid, "due_date": due, "message": f"已创建复习任务「{title}」"}


def _tool_create_event(ctx: AgentContext, args: dict) -> dict:
    title = (args.get("title") or "").strip()
    year = _as_int(args.get("year"))
    if not title or year is None:
        return {"ok": False, "error": "title 与 year 都必填（year 为整数，公元前用负数）"}
    node_code = (args.get("node_code") or "").strip() or ctx.track
    if node_code != ctx.track and not ctx.node_ok(node_code):
        return {"ok": False, "error": f"章节 {node_code} 不属于当前课程"}
    digest = (args.get("summary") or "").strip()
    conn = ctx.conn()
    try:
        dup = conn.execute(
            "SELECT id FROM events WHERE user_id=? AND title=?", (ctx.uid, title)
        ).fetchone()
        if dup:
            return {"ok": True, "id": dup["id"], "duplicated": True,
                    "message": f"时间轴已有「{title}」，未重复添加"}
        cur = conn.execute(
            """INSERT INTO events(user_id,uuid,kp_id,title,era,year,year_end,year_label,place,people,
               cause,process,impact,significance,tags,kind,node_code,created_at)
               VALUES(?,?,NULL,?,?,?,NULL,'',?,'','','',?,?,'AI','event',?,?)""",
            (ctx.uid, uuid.uuid4().hex, title, ctx.track_name, year,
             (args.get("place") or "").strip(), digest, digest, node_code, ctx.now()),
        )
        conn.commit()
        eid = cur.lastrowid
    finally:
        conn.close()
    return {"ok": True, "id": eid, "message": f"已加入时间轴：{year} {title}"}


# ==================== 工具注册表 ====================

def _spec(name, desc, props, required=(), write=False):
    return {
        "name": name,
        "write": write,
        "spec": {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": list(required),
                },
            },
        },
    }


_S = lambda desc: {"type": "string", "description": desc}
_I = lambda desc: {"type": "integer", "description": desc}

TOOLS = {
    "list_syllabus": dict(
        _spec("list_syllabus", "列出当前课程的教材章节树（章 code + 节 code + 已有知识点数）。写数据前必须先确认节点 code。",
              {"chapter": _S("可选：章名关键词或章 code，如「遵义」「party-03」；留空列出全部")}),
        fn=_tool_list_syllabus,
    ),
    "find_node": dict(
        _spec("find_node", "按关键词在教材目录里定位章节，返回候选 code。适合「遵义会议在哪一节」这类问题。",
              {"keyword": _S("章节标题里的关键词，越短越好")}, ["keyword"]),
        fn=_tool_find_node,
    ),
    "search_content": dict(
        _spec("search_content", "在学生的史料库、知识点、时间轴里做关键词检索，返回原文片段。回答任何史实问题前都应先调它。",
              {"query": _S("检索关键词"), "limit": _I("返回几篇资料片段，默认 5，最多 8")}, ["query"]),
        fn=_tool_search_content,
    ),
    "read_material": dict(
        _spec("read_material", "读取某一篇史料的正文（可分页）。做史料分析、出材料题前用它看原文。",
              {"material_id": _I("资料 id"), "offset": _I("从第几个字开始，默认 0"),
               "length": _I("读多少字，默认 2500，最多 6000")}, ["material_id"]),
        fn=_tool_read_material,
    ),
    "list_knowledge_points": dict(
        _spec("list_knowledge_points", "列出本人已有的知识点（可按节 code 或关键词过滤），返回 id 供出题使用。",
              {"node_code": _S("可选：节 code 前缀，如 party-03-02"),
               "keyword": _S("可选：标题/描述关键词"), "limit": _I("最多返回几条，默认 30")}),
        fn=_tool_list_knowledge_points,
    ),
    "list_events": dict(
        _spec("list_events", "查时间轴事件，可按关键词与年份区间过滤。做时序题、梳理阶段特征时用。",
              {"keyword": _S("可选：事件名关键词"), "year_from": _I("可选：起始年"),
               "year_to": _I("可选：结束年"), "limit": _I("最多返回几条，默认 30")}),
        fn=_tool_list_events,
    ),
    "get_my_stats": dict(
        _spec("get_my_stats", "查看本人学习数据：资料/知识点/题目/任务数量、练习次数、错题数、薄弱知识点、临近任务。给复习建议前先调它。",
              {}),
        fn=_tool_get_my_stats,
    ),
    "get_wrong_book": dict(
        _spec("get_wrong_book", "看看未掌握的错题（题干、答案、所属知识点）。讲错题、定制复习计划前用。",
              {"limit": _I("最多返回几条，默认 10")}),
        fn=_tool_wrong_book,
    ),
    "create_knowledge_point": dict(
        _spec("create_knowledge_point",
              "新建一条史实要点（知识点）并挂到某一节下。写之前先用 list_knowledge_points 查重。",
              {"node_code": _S("节 code，如 party-03-02（必填，先用 find_node 查）"),
               "title": _S("知识点标题，20 字以内"),
               "description": _S("要点正文：背景/内容/意义，150-400 字，按权威简史表述"),
               "exam_type": _S("考法，可选 recall(史实识记)/sequence(时序定位)/argument(史论结合)/apply(现实联系)"),
               "material_id": _I("可选：关联的史料 id")},
              ["node_code", "title", "description"], write=True),
        fn=_tool_create_knowledge_point,
    ),
    "create_material": dict(
        _spec("create_material",
              "生成一篇史料/学习资料并存入「史料笔记」，学生之后能直接打开阅读、用来出题。适合整理原文要点、专题综述、会议文件摘编。",
              {"title": _S("资料标题"), "content": _S("正文，Markdown 格式，200-5000 字"),
               "node_code": _S("可选：挂到哪一节，默认挂当前课程")},
              ["title", "content"], write=True),
        fn=_tool_create_material,
    ),
    "create_questions": dict(
        _spec("create_questions",
              "给某个知识点批量新建练习题。题型用「单选题/名词解释/时间排序/简答/材料分析/论述」，答案要符合权威简史。",
              {"kp_id": _I("知识点 id（来自 list_knowledge_points）"),
               "questions": {
                   "type": "array",
                   "description": "题目数组，最多 10 项",
                   "items": {
                       "type": "object",
                       "properties": {
                           "type": _S("题型"),
                           "question": _S("题干"),
                           "answer": _S("参考答案"),
                       },
                       "required": ["type", "question", "answer"],
                   },
               }},
              ["kp_id", "questions"], write=True),
        fn=_tool_create_questions,
    ),
    "create_task": dict(
        _spec("create_task", "给学生建一条复习任务（可带截止日期），会出现在「复习任务」页。",
              {"title": _S("任务标题"), "description": _S("任务说明：做什么、做到什么程度"),
               "due_date": _S("截止日期，形如 2026-11-12；可留空"),
               "kp_id": _I("可选：关联知识点 id")},
              ["title"], write=True),
        fn=_tool_create_task,
    ),
    "create_event": dict(
        _spec("create_event", "往时间轴补一条历史事件（会议/事件/文件）。学生问「能不能补进时间轴」或内容缺失时用。",
              {"title": _S("事件名称"), "year": _I("年份整数，公元前用负数"),
               "summary": _S("一句话史实要点（30-120 字）"),
               "place": _S("可选：地点"), "node_code": _S("可选：挂到哪一节")},
              ["title", "year"], write=True),
        fn=_tool_create_event,
    ),
}


def tool_specs(allow_write: bool) -> list:
    return [t["spec"] for t in TOOLS.values() if allow_write or not t["write"]]


def execute_tool(ctx: AgentContext, name: str, args: dict, allow_write: bool) -> dict:
    tool = TOOLS.get(name)
    if not tool:
        return {"ok": False, "error": f"没有名为 {name} 的工具"}
    if tool["write"] and not allow_write:
        return {"ok": False, "error": "当前会话关闭了写入权限，只能查不能改；请提示用户在界面上打开「允许 AI 写入」"}
    try:
        return tool["fn"](ctx, args or {})
    except Exception as e:  # 工具内部异常不该打断整轮对话，回给模型让它换参数重试
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def system_prompt(ctx: AgentContext) -> str:
    return f"""你是「四史学习助手」内置的学科助教兼学习管家，正在辅导一名大学生学习《{ctx.track_name}》。
你不是只会聊天的问答机器人：你能通过工具**直接读写这个软件里的数据**——检索教材目录与史料原文、建知识点、生成资料入库、出题、建复习任务、补时间轴。

工作方式（自主执行，不要反问一堆再动手）：
1. 涉及具体史实、章节、原文的问题，先调 search_content / find_node / list_syllabus 核实，再回答。
2. 学生说「帮我整理/生成/入库」时，直接把结果写进库（create_knowledge_point / create_material / create_questions / create_task），写完用一句话说明写了什么、在哪一页能看到。
3. 学生说「帮我学第 X 章」时，按「查目录 → 检索已有内容 → 补知识点 → 出 2-3 道题 → 建复习任务」的顺序自主跑完，最后给一个三步以内的行动建议。
4. 写作前先用 list_knowledge_points 查重，避免重复入库；一次别超过 10 条知识点或 10 道题。
5. 互不依赖的工具在同一轮里一起调用（例如同时查目录和检索史料），别一个工具磨一轮；正常请求应在 2-3 轮内给结论。

内容要求：
- 口径必须符合权威简史（《百年奋斗重大成就和历史经验的决议》、四本官方简史、二十大报告），重大年份、会议、文件名称不得写错。
- 严格区分「史料原文」与「史家评价」；资料里没有的内容明确说「资料未涉及」，不得编造。
- 只谈《{ctx.track_name}》范围；学生问别的课程，提醒他到「切换课程」，不要混着讲。
- 回答用中文，先给结论，再分点展开；不超过 500 字，需要长文时先给框架。

当前课程：{ctx.track_name}（track={ctx.track}）。章节 code 形如 {ctx.track}-03-02，写入必须用真实的节 code。"""


def _force_final(convo: list) -> str:
    """强制模型不带工具收尾。

    step-3.5-flash 在长上下文里偶尔返回空 content（答案落进 reasoning_content），
    这里补一次「直接回答」，还是空就退而取推理文本，保证学生不会看到空气泡。
    """
    try:
        msg = ai_helper.chat_completion(
            convo + [{"role": "user",
                      "content": "请不要再调用工具，直接用中文给出最终答复：写入了什么、学生下一步做什么。"}],
            tools=None,
        )
        text = (msg.get("content") or "").strip()
        if not text:
            text = (msg.get("reasoning_content") or "").strip()[:1500]
        return text
    except Exception:
        return ""


def run_events(ctx: AgentContext, messages: list, allow_write: bool = True):
    """生成器：边跑边吐事件，最后一个事件是 {"type":"done", ...}。

    事件类型：
    - step/start：开始调某个工具（前端先亮一张「正在检索史料」的卡片）
    - step/end  ：工具跑完（带 ok、一行 summary、完整 detail）
    - error     ：大模型调用失败
    - done      ：最终答复 + 完整步骤记录
    """
    specs = tool_specs(allow_write)
    convo = [{"role": "system", "content": system_prompt(ctx)}]
    for m in messages[-12:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            convo.append({"role": role, "content": content[:4000]})

    steps = []
    used = 0
    for round_no in range(1, MAX_ROUNDS + 1):
        try:
            msg = ai_helper.chat_completion(convo, tools=specs)
        except Exception as e:
            yield {"type": "error", "message": f"调用大模型失败：{e}"}
            yield {"type": "done", "reply": "", "steps": steps, "rounds": round_no,
                   "tool_calls": used, "error": str(e)}
            return

        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            if not text:
                text = _force_final(convo)
            yield {"type": "done", "reply": text, "steps": steps,
                   "rounds": round_no, "tool_calls": used}
            return

        convo.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for tc in calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            desc = TOOLS.get(name, {}).get("spec", {}).get("function", {}).get("description", "")
            yield {"type": "step", "phase": "start", "tool": name,
                   "label": desc[:20], "args": args, "write": bool(TOOLS.get(name, {}).get("write"))}

            if used >= MAX_TOOL_CALLS:
                result = {"ok": False, "error": "工具调用次数已达上限，请直接基于已有信息作答"}
            else:
                result = execute_tool(ctx, name, args, allow_write)
                used += 1

            step = {"tool": name, "args": args, "ok": bool(result.get("ok", True)),
                    "summary": _summarize(name, result)}
            steps.append(step)
            yield {"type": "step", "phase": "end", "tool": name, "ok": step["ok"],
                   "summary": step["summary"], "detail": result}
            convo.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or name,
                "content": json.dumps(result, ensure_ascii=False)[:MAX_TOOL_RESULT],
            })

    # 轮次用尽：不许再调工具，强制模型收尾给结论——否则学生只看到一堆工具卡片没答案
    reply = _force_final(convo)
    yield {"type": "done",
           "reply": reply or "（工具调用轮次用尽，先把上面已经写入的结果用起来；"
                             "要更细的任务请拆成小问题再问一次。）",
           "steps": steps, "rounds": MAX_ROUNDS, "tool_calls": used, "truncated": True}


def run(ctx: AgentContext, messages: list, allow_write: bool = True,
        on_event: Callable[[dict], None] = None) -> dict:
    """非流式包装：跑完返回 done 事件的内容（测试与脚本用）。"""
    final = {"reply": "", "steps": []}
    for ev in run_events(ctx, messages, allow_write):
        if ev["type"] == "done":
            final = ev
        elif on_event:
            on_event(ev)
    return final


def _summarize(name: str, result: dict) -> str:
    """给界面看的一行结果描述。"""
    if result.get("message"):
        return str(result["message"])[:60]
    if result.get("error"):
        return "失败：" + str(result["error"])[:50]
    if "materials" in result:
        return f"资料 {len(result['materials'])} 篇 / 知识点 {len(result.get('knowledge_points') or [])} 条"
    if "items" in result:
        return f"命中 {result.get('count', len(result['items']))} 条"
    if "text" in result:
        return f"读取 {len(result['text'])} 字（共 {result.get('total_chars', '?')} 字）"
    if "created" in result:
        return f"新增 {result['created']} 题"
    if "matched" in result:
        return f"匹配 {result['matched']} 个章节"
    if "totals" in result:
        t = result["totals"]
        return f"资料 {t.get('materials')} / 知识点 {t.get('kps')} / 错题 {t.get('unresolved_wrong')}"
    return "完成"
