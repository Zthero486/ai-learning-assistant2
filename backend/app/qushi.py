# -*- coding: utf-8 -*-
"""四史课程骨架：内置教材章节树 + 内置关键事件。

设计取舍
- 章节树是**全局内置数据**，不随用户/同步走，因此不进 USER_TABLES、不进 sync.CHAIN。
- 知识点不存 node_id（本地自增 id 跨机无意义），改存 **node_code**（如 party-03-02），
  同步到另一台机器仍然指向同一节。
- 事件按用户复制一份：用户选课后，把该课的内置关键事件灌进他自己的 events 表，
  这样事件可编辑、可同步，也不需要在查询里到处写 `user_id IN (0, uid)`。
"""

import json
import uuid
from pathlib import Path

DATA_FILE = Path(__file__).with_name("seed_data") / "qushi.json"
CONTENT_FILE = Path(__file__).with_name("seed_data") / "qushi_content.json"
TEXTS_FILE = Path(__file__).with_name("seed_data") / "qushi_texts.json"

_CACHE = None
_CONTENT = None
_TEXTS = None

# 事件种类 → 中文标签
KIND_LABEL = {
    "meeting": "会议",
    "event": "事件",
    "document": "文件",
}

CN_NUM = "一二三四五六七八九十"


def content() -> dict:
    """扩充内容包：追加事件、内置史料、知识点样例题（缺失时返回空骨架）。"""
    global _CONTENT
    if _CONTENT is None:
        try:
            _CONTENT = json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _CONTENT = {"events": [], "materials": [], "kps": []}
    return _CONTENT


def texts() -> dict:
    """教材正文：{node_code: "段落1\n\n段落2"}，只覆盖已撰写的课程。"""
    global _TEXTS
    if _TEXTS is None:
        try:
            _TEXTS = json.loads(TEXTS_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _TEXTS = {}
    return _TEXTS


def load() -> dict:
    global _CACHE
    if _CACHE is None:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        extra = content().get("events") or []
        if extra:
            data["events"] = list(data["events"]) + list(extra)
        _CACHE = data
    return _CACHE


def builtin_materials() -> list:
    """内置史料：[{track,title,content}, ...]。"""
    return content().get("materials") or []


def builtin_kps() -> list:
    """内置知识点样例：[{node_code,title,description,exam_type,question{type,q,a}}, ...]。"""
    return content().get("kps") or []


def tracks() -> list:
    return load()["tracks"]


def track_map() -> dict:
    return {t["key"]: t for t in tracks()}


def track_keys() -> list:
    return [t["key"] for t in tracks()]


def valid_track(key: str) -> bool:
    return key in track_map()


def chapter_no(idx: int) -> str:
    """1 -> 一，10 -> 十。章节最多十章，够用。"""
    return CN_NUM[idx - 1] if 1 <= idx <= len(CN_NUM) else str(idx)


def chapter_code(track: str, ch: int) -> str:
    return f"{track}-{ch:02d}"


def section_code(track: str, ch: int, sec: int) -> str:
    return f"{track}-{ch:02d}-{sec:02d}"


def track_of(code: str) -> str:
    return (code or "").split("-")[0]


def ensure_syllabus(conn) -> int:
    """把内置章节树写进 syllabus_nodes（幂等）。返回新增行数。"""
    added = 0
    for track in track_keys():
        for ci, chap in enumerate(load()["nodes"][track], start=1):
            ccode = chapter_code(track, ci)
            cur = conn.execute(
                """INSERT OR IGNORE INTO syllabus_nodes
                   (code, track, level, parent_code, title, period, order_no)
                   VALUES (?,?,?,?,?,?,?)""",
                (ccode, track, 1, "", chap["t"], chap.get("p", ""), ci),
            )
            added += cur.rowcount
            for si, sec in enumerate(chap["s"], start=1):
                cur = conn.execute(
                    """INSERT OR IGNORE INTO syllabus_nodes
                       (code, track, level, parent_code, title, period, order_no)
                       VALUES (?,?,?,?,?,?,?)""",
                    (section_code(track, ci, si), track, 2, ccode, sec, chap.get("p", ""), si),
                )
                added += cur.rowcount
    # 教材正文：内置节点 content 为空且内容包里有对应文本时补写（幂等）
    filled = 0
    for code, text in texts().items():
        cur = conn.execute(
            "UPDATE syllabus_nodes SET content=? WHERE code=? AND (content IS NULL OR content='')",
            (text, code),
        )
        filled += cur.rowcount
    if added or filled:
        conn.commit()
    return added


def tree(conn, track: str, uid: int = 0) -> list:
    """返回 [{code, title, period, chapter_no, sections:[...]}]，带该用户的学习量。"""
    rows = conn.execute(
        "SELECT code, level, parent_code, title, period, order_no FROM syllabus_nodes "
        "WHERE track=? ORDER BY level, order_no",
        (track,),
    ).fetchall()

    counts = {}
    if uid:
        for r in conn.execute(
            """SELECT k.node_code AS code,
                      COUNT(DISTINCT k.id) AS kp,
                      COUNT(DISTINCT q.id) AS q
               FROM knowledge_points k
               LEFT JOIN questions q ON q.kp_id = k.id
               WHERE k.user_id=? AND k.node_code LIKE ?
               GROUP BY k.node_code""",
            (uid, f"{track}-%"),
        ):
            counts[r["code"]] = {"kp": r["kp"], "q": r["q"]}

    chapters = []
    by_code = {}
    for r in rows:
        if r["level"] == 1:
            node = {
                "code": r["code"],
                "title": f"第{chapter_no(r['order_no'])}章 {r['title']}",
                "period": r["period"],
                "kp": counts.get(r["code"], {}).get("kp", 0),
                "q": counts.get(r["code"], {}).get("q", 0),
                "sections": [],
            }
            chapters.append(node)
            by_code[r["code"]] = node
    for r in rows:
        if r["level"] != 2:
            continue
        parent = by_code.get(r["parent_code"])
        if not parent:
            continue
        c = counts.get(r["code"], {})
        parent["sections"].append(
            {
                "code": r["code"],
                "title": r["title"],
                "order": r["order_no"],
                "kp": c.get("kp", 0),
                "q": c.get("q", 0),
            }
        )
        # 章的统计 = 自身直挂 + 各节之和
        parent["kp"] += c.get("kp", 0)
        parent["q"] += c.get("q", 0)
    return chapters


def node(conn, code: str):
    return conn.execute("SELECT * FROM syllabus_nodes WHERE code=?", (code,)).fetchone()


def path_text(conn, code: str) -> str:
    """party-03-02 -> 第三章 全民族抗日战争的中流砥柱 · 二、…"""
    row = node(conn, code)
    if not row:
        return ""
    if row["level"] == 1:
        return row["title"]
    chap = conn.execute(
        "SELECT title, order_no FROM syllabus_nodes WHERE code=?", (row["parent_code"],)
    ).fetchone()
    head = f"第{chapter_no(chap['order_no'])}章 {chap['title']}" if chap else ""
    return f"{head} · {row['title']}" if head else row["title"]


def builtin_events(track: str) -> list:
    return [e for e in load()["events"] if e["track"] == track]


def seed_track_events(conn, uid: int, track: str, now: str) -> int:
    """把该课的内置关键事件复制到用户名下（幂等：靠 tags 里的 内置 标记去重）。"""
    have = {
        r["title"]
        for r in conn.execute(
            "SELECT title FROM events WHERE user_id=? AND tags LIKE '%内置%'", (uid,)
        )
    }
    name = track_map()[track]["name"]
    added = 0
    for e in builtin_events(track):
        if e["title"] in have:
            continue
        conn.execute(
            """INSERT INTO events
               (user_id, uuid, kp_id, title, era, year, year_end, year_label, place, people,
                cause, process, impact, significance, tags, kind, node_code, created_at)
               VALUES (?,?,NULL,?,?,?,NULL,'',?,'','','',?,?,'内置',?,?,?)""",
            (
                uid,
                uuid.uuid4().hex,
                e["title"],
                name,
                e["year"],
                e.get("place", ""),
                e["digest"],
                e["digest"],
                e["kind"],
                e["node"],
                now,
            ),
        )
        added += 1
    if added:
        conn.commit()
    return added
