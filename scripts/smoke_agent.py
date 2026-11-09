# -*- coding: utf-8 -*-
"""AI Agent 工具层冒烟测试。

分两段：
A. 离线：直接调 17 个工具的执行函数（不花 token），验证 SQL、权限、去重、错误处理。
B. 在线：如果有可用 AI key，跑一次真实对话，看模型会不会自己选工具。

结果写 _tmp/agent_smoke.txt（沙箱里 stdout 不稳定，落盘再读）。
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import ai_agent, ai_helper, main, qushi  # noqa: E402

OUT_DIR = ROOT / "_tmp"
OUT_DIR.mkdir(exist_ok=True)
STAMP = time.strftime("%Y%m%d_%H%M%S")
TMP_DB = OUT_DIR / f"agent_smoke_{STAMP}.db"
LOG = OUT_DIR / "agent_smoke.txt"

lines = []


def w(*a):
    line = " ".join(str(x) for x in a)
    lines.append(line)


def check(name, cond, info=""):
    w(("PASS" if cond else "FAIL"), name, info)
    return bool(cond)


try:
    os.environ["AI_DISABLE_BUILTIN"] = os.environ.get("AI_DISABLE_BUILTIN", "")

    # 用临时库，绝不碰开发库
    main.DB_PATH = TMP_DB
    main.UPLOAD_DIR = OUT_DIR / "agent_uploads"
    main.init_db()

    conn = main.db()
    conn.execute("UPDATE users SET track='party' WHERE id=1")
    conn.execute(
        "INSERT INTO materials(user_id,uuid,title,course,filename,filetype,content,node_code,created_at)"
        " VALUES(1,?,'测试史料·遵义会议','党史','t.txt','text',?,'party-03-02',?)",
        ("u-test-1", "遵义会议在一九三五年一月召开，确立了毛泽东在党中央的领导地位。"
                     "会议结束了王明「左」倾教条主义在中央的统治，是党的历史上一个生死攸关的转折点。",
         main.now()),
    )
    conn.commit()
    seeded = qushi.seed_track_events(conn, 1, "party", main.now())
    conn.close()
    w(f"临时库 {TMP_DB.name}，内置事件 {seeded} 条")

    ctx = ai_agent.AgentContext(1, "party", main.db, main.now)

    # ---- A. 只读工具 ----
    r = ai_agent.execute_tool(ctx, "list_syllabus", {"chapter": "遵义"}, True)
    check("list_syllabus 能收窄到章", r.get("chapter_count", 0) >= 1, r.get("text", "")[:60])

    r = ai_agent.execute_tool(ctx, "find_node", {"keyword": "遵义"}, True)
    check("find_node 匹配到节点", r.get("matched", 0) >= 1, str(r.get("nodes"))[:80])
    node_code = (r.get("nodes") or [{}])[0].get("code", "")

    r = ai_agent.execute_tool(ctx, "search_content", {"query": "遵义会议"}, True)
    check("search_content 命中资料", len(r.get("materials") or []) >= 1,
          f"资料 {len(r.get('materials') or [])} 篇 / 事件 {len(r.get('events') or [])} 条")

    mid = (r.get("materials") or [{}])[0].get("material_id")
    r = ai_agent.execute_tool(ctx, "read_material", {"material_id": mid, "length": 100}, True)
    check("read_material 能读正文", "遵义" in (r.get("text") or ""), r.get("hint", ""))

    r = ai_agent.execute_tool(ctx, "read_material", {"material_id": 999999}, True)
    check("read_material 越权/不存在时报错不抛异常", r.get("ok") is False, r.get("error", ""))

    r = ai_agent.execute_tool(ctx, "list_events", {"year_from": 1930, "year_to": 1940}, True)
    check("list_events 年份过滤", all(1930 <= (i["year"] if isinstance(i["year"], int) else 9999) <= 1940
                                      for i in r.get("items") or []), f"{r.get('count')} 条")

    r = ai_agent.execute_tool(ctx, "get_my_stats", {}, True)
    check("get_my_stats 返回总数", "totals" in r, str(r.get("totals"))[:80])

    r = ai_agent.execute_tool(ctx, "get_wrong_book", {}, True)
    check("get_wrong_book 空表也正常", r.get("count") == 0, "")

    # ---- A. 写入工具 ----
    r = ai_agent.execute_tool(ctx, "create_knowledge_point", {
        "node_code": node_code, "title": "遵义会议的历史地位",
        "description": "1935 年 1 月中央政治局扩大会议，确立毛泽东领导地位，是生死攸关的转折点。",
        "exam_type": "argument"}, True)
    check("create_knowledge_point 成功", r.get("ok") and r.get("id"), str(r)[:100])
    kp_id = r.get("id")

    r2 = ai_agent.execute_tool(ctx, "create_knowledge_point", {
        "node_code": node_code, "title": "遵义会议的历史地位", "description": "重复"}, True)
    check("create_knowledge_point 去重", r2.get("duplicated") is True, str(r2)[:80])

    r3 = ai_agent.execute_tool(ctx, "create_knowledge_point", {
        "node_code": "prc-01-01", "title": "跨课污染", "description": "x"}, True)
    check("create_knowledge_point 拒绝别课节点", r3.get("ok") is False, r3.get("error", ""))

    r = ai_agent.execute_tool(ctx, "create_material", {
        "title": "AI 生成：遵义会议要点摘编",
        "content": "一、背景。第五次反「围剿」失败，红军被迫长征。" * 8,
        "node_code": node_code}, True)
    check("create_material 入库", r.get("ok") and r.get("id"), str(r)[:100])

    r = ai_agent.execute_tool(ctx, "create_questions", {"kp_id": kp_id, "questions": [
        {"type": "单选题", "question": "遵义会议召开于哪一年？A.1934 B.1935 C.1936 D.1937", "answer": "B"},
        {"type": "简答", "question": "简述遵义会议的历史意义。", "answer": "确立毛泽东领导地位，是生死攸关的转折点。"},
    ]}, True)
    check("create_questions 建题", r.get("created") == 2, str(r)[:80])

    r = ai_agent.execute_tool(ctx, "create_task", {
        "title": "复习遵义会议", "description": "读完要点后做 2 道题", "due_date": "2026-11-12"}, True)
    check("create_task 建任务", r.get("ok") and r.get("id"), str(r)[:80])

    r = ai_agent.execute_tool(ctx, "create_task", {"title": "坏日期", "due_date": "下周"}, True)
    check("create_task 拒绝非法日期", r.get("ok") is False, r.get("error", ""))

    r = ai_agent.execute_tool(ctx, "create_event", {
        "title": "遵义会议", "year": 1935, "summary": "确立毛泽东在党中央的领导地位。",
        "node_code": node_code}, True)
    check("create_event 幂等（内置已有同名）", r.get("ok"), str(r)[:80])

    r = ai_agent.execute_tool(ctx, "create_event", {
        "title": "AI 测试事件", "year": 1935, "summary": "测试", "node_code": node_code}, True)
    check("create_event 新增", r.get("ok") and r.get("id"), str(r)[:80])

    # ---- 权限开关 ----
    r = ai_agent.execute_tool(ctx, "create_task", {"title": "只读模式"}, False)
    check("navigate 合法路由", ai_agent.execute_tool(ctx, "navigate", {"route": "/materials"}, allow_write=True)["route"] == "/materials")
    check("navigate 非法路由被拒", ai_agent.execute_tool(ctx, "navigate", {"route": "/admin"}, allow_write=True)["ok"] is False)
    check("allow_write=False 时写入被拒", r.get("ok") is False, r.get("error", "")[:40])
    check("只读工具清单 10 个", len(ai_agent.tool_specs(False)) == 10, len(ai_agent.tool_specs(False)))
    check("全量工具 15 个", len(ai_agent.tool_specs(True)) == 15, len(ai_agent.tool_specs(True)))

    conn = main.db()
    counts = {
        "kp": conn.execute("SELECT COUNT(*) c FROM knowledge_points").fetchone()["c"],
        "mat": conn.execute("SELECT COUNT(*) c FROM materials").fetchone()["c"],
        "q": conn.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"],
        "task": conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"],
    }
    conn.close()
    check("数据确实落库", counts["kp"] == 1 and counts["q"] == 2 and counts["task"] == 1, counts)

    # ---- B. 在线对话 ----
    available = ai_helper.is_available() and not os.environ.get("AI_DISABLE_BUILTIN")
    w("AI 可用:", available, "来源:", ai_helper.key_source())
    if available:
        events = []
        result = ai_agent.run(
            ctx,
            [{"role": "user", "content": "帮我看看遵义会议在哪一节，给这一节建一个知识点，再出 2 道题"}],
            allow_write=True,
            on_event=lambda e: events.append(e),
        )
        w("在线对话工具调用序列:", [s["tool"] for s in result.get("steps", [])])
        w("在线对话回复:", (result.get("reply") or "")[:400])
        check("在线对话调用了工具", len(result.get("steps") or []) >= 2, len(result.get("steps") or []))
        check("在线对话有回复", bool((result.get("reply") or "").strip()), "")
        writes = [s for s in result.get("steps", []) if s["tool"].startswith("create_")]
        check("在线对话至少一次写入", len(writes) >= 1, [s["tool"] for s in writes])
except Exception as e:
    import traceback

    w("EXCEPTION", type(e).__name__, e)
    w(traceback.format_exc())

fails = [l for l in lines if l.startswith("FAIL")]
lines.append("")
lines.append(f"结论：{'全部通过' if not fails else str(len(fails)) + ' 项失败'}")
LOG.write_text("\n".join(lines), encoding="utf-8")
print(LOG.read_text(encoding="utf-8"))
