# -*- coding: utf-8 -*-
"""Agent 任务型对话回归：把真机评测里模型实际犯过的错固化成用例。

背景（2026-11-07 截图反馈）：「帮我学第一章、生成 6 组题」的实测里，
模型把 questions 数组传成了字符串，StepFun 平台报"参数校验失败"，
模型拿着没有可执行信息的错误原样重试 8 次，烧光调用预算后一道题都没写成。
这里的用例全部来自那次评测的失败模式。

在线评测（真模型端到端）在 scripts/agent_eval.py，不进 CI。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ai_agent  # noqa: E402
from app import main as app_main  # noqa: E402
from tests.conftest import AuthClient  # noqa: F401  保证 conftest 生效


@pytest.fixture
def party_ctx(client):
    client.post("/api/profile/track", json={"track": "party"})
    kp = client.post(
        "/api/knowledge-points", json={"title": "第一次国共合作", "course": "党史"}
    ).json()
    ctx = ai_agent.AgentContext(client.user_id, "party", app_main.db, app_main.now)
    return ctx, kp["id"]


def _db_question_count(ctx, kp_id) -> int:
    conn = ctx.conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM questions WHERE kp_id=? AND user_id=?", (kp_id, ctx.uid)
        ).fetchone()[0]
    finally:
        conn.close()
    return n


# ---------- 出题工具对坏参数的宽容度 ----------
def test_questions_as_json_string_is_accepted(party_ctx):
    """模型最常见的病：把数组序列化成字符串传进来 → 必须接住，而不是 8 次重试。"""
    ctx, kp_id = party_ctx
    payload = json.dumps(
        [
            {
                "type": "单选题",
                "question": "第一次国共合作发生于哪一年？",
                "answer": "1924年",
                "evidence": "1924年国民党一大召开",
            },
            {
                "type": "简答",
                "question": "简述合作的政治基础。",
                "answer": "新三民主义",
                "evidence": "新三民主义是合作的政治基础",
            },
        ],
        ensure_ascii=False,
    )
    r = ai_agent.execute_tool(
        ctx, "create_questions", {"kp_id": kp_id, "questions": payload}, allow_write=True
    )
    assert r["ok"] is True and r["created"] == 2
    assert _db_question_count(ctx, kp_id) == 2


def test_single_question_object_is_wrapped(party_ctx):
    ctx, kp_id = party_ctx
    r = ai_agent.execute_tool(
        ctx,
        "create_questions",
        {
            "kp_id": kp_id,
            "questions": {"question": "大革命失败的原因？", "answer": "略", "evidence": "原文依据"},
        },
        allow_write=True,
    )
    assert r["ok"] is True and r["created"] == 1


def test_bad_items_are_skipped_with_reasons(party_ctx):
    """混入坏项：跳过并报告原因，好的照常入库。"""
    ctx, kp_id = party_ctx
    r = ai_agent.execute_tool(
        ctx,
        "create_questions",
        {
            "kp_id": kp_id,
            "questions": [
                {"question": "好题", "answer": "好答案", "evidence": "原文依据"},
                "一个字符串",
                {"answer": "没有题干", "evidence": "原文依据"},
                {"question": "  ", "answer": "空题干", "evidence": "原文依据"},
            ],
        },
        allow_write=True,
    )
    assert r["ok"] is True and r["created"] == 1
    assert len(r["skipped"]) == 3
    assert "第2项" in "；".join(r["skipped"]) or "不是对象" in "；".join(r["skipped"])


def test_all_bad_returns_actionable_error(party_ctx):
    """全坏 → 错误信息必须带可照抄的示例，模型才能下一轮改对。"""
    ctx, kp_id = party_ctx
    r = ai_agent.execute_tool(
        ctx, "create_questions", {"kp_id": kp_id, "questions": ["a", "b"]}, allow_write=True
    )
    assert r["ok"] is False
    assert "JSON 数组" in r["error"] and '"question"' in r["error"]


def test_oversized_batch_is_truncated_not_rejected(party_ctx):
    ctx, kp_id = party_ctx
    many = [{"question": f"题{i}", "answer": "略", "evidence": "原文依据"} for i in range(15)]
    r = ai_agent.execute_tool(
        ctx, "create_questions", {"kp_id": kp_id, "questions": many}, allow_write=True
    )
    assert r["ok"] is True and r["created"] == ai_agent.MAX_QUESTIONS_PER_CALL


# ---------- 原文依据硬约束（2026-11-09 用户要求：找不到教材原文不出题） ----------


def test_missing_evidence_questions_are_rejected(party_ctx):
    """没有 evidence（教材原文依据）的题一律不落库，好的照常入库。"""
    ctx, kp_id = party_ctx
    r = ai_agent.execute_tool(
        ctx,
        "create_questions",
        {
            "kp_id": kp_id,
            "questions": [
                {"question": "有依据的题", "answer": "略", "evidence": "教材里的原句"},
                {"question": "没依据的题", "answer": "略"},
                {"question": "空依据的题", "answer": "略", "evidence": "   "},
            ],
        },
        allow_write=True,
    )
    assert r["ok"] is True and r["created"] == 1
    assert len(r["skipped"]) == 2
    assert all("evidence" in s for s in r["skipped"])
    assert _db_question_count(ctx, kp_id) == 1
    # 库里存的 evidence 就是那句原文
    conn = ctx.conn()
    try:
        ev = conn.execute("SELECT evidence FROM questions WHERE kp_id=?", (kp_id,)).fetchone()[0]
    finally:
        conn.close()
    assert ev == "教材里的原句"


def test_all_missing_evidence_returns_actionable_error(party_ctx):
    """整批都没依据 → 报错要引导模型先调 get_node_text 拿原文。"""
    ctx, kp_id = party_ctx
    r = ai_agent.execute_tool(
        ctx,
        "create_questions",
        {"kp_id": kp_id, "questions": [{"question": "题", "answer": "略"}]},
        allow_write=True,
    )
    assert r["ok"] is False
    assert "get_node_text" in r["error"]


def test_get_node_text_returns_text_and_hints(party_ctx):
    """读教材正文：返回原文、总数和出题提示；这是出题依据的唯一入口。"""
    ctx, _kp_id = party_ctx
    r = ai_agent.execute_tool(ctx, "get_node_text", {"node_code": "party-01-01"}, allow_write=False)
    assert r["ok"] is True
    assert r["text"].strip()
    assert r["total_chars"] >= len(r["text"])
    assert "evidence" in r["hint"]


def test_get_node_text_missing_or_empty(party_ctx):
    ctx, _kp_id = party_ctx
    bad = ai_agent.execute_tool(
        ctx, "get_node_text", {"node_code": "party-99-99"}, allow_write=False
    )
    assert bad["ok"] is False and "不存在" in bad["error"]
    empty = ai_agent.execute_tool(ctx, "get_node_text", {}, allow_write=False)
    assert empty["ok"] is False and "node_code" in empty["error"]


# ---------- AI 划重点（highlight_text） ----------
def test_highlight_text_creates_purple_note(party_ctx):
    """quote 逐字摘自正文 → 落一条紫色 text_notes；重复划同一处只更新不重复建。"""
    ctx, _kp_id = party_ctx
    src = ai_agent.execute_tool(
        ctx, "get_node_text", {"node_code": "party-01-01"}, allow_write=False
    )
    assert src["ok"] is True
    quote = " ".join(src["text"].split())[:20]  # 故意掺空白差异，验证定位容错
    r = ai_agent.execute_tool(
        ctx,
        "highlight_text",
        {"node_code": "party-01-01", "quote": quote, "note": "考点"},
        allow_write=True,
    )
    assert r["ok"] is True and r["action"] == "created"
    conn = ctx.conn()
    try:
        row = conn.execute(
            "SELECT color, note, quote FROM text_notes WHERE id=?", (r["note_id"],)
        ).fetchone()
        # 重复划同一处 → updated，不落第二条
        r2 = ai_agent.execute_tool(
            ctx, "highlight_text", {"node_code": "party-01-01", "quote": quote}, allow_write=True
        )
        total = conn.execute(
            "SELECT COUNT(*) FROM text_notes WHERE user_id=? AND node_code=?",
            (ctx.uid, "party-01-01"),
        ).fetchone()[0]
    finally:
        conn.close()
    assert row["color"] == "purple" and row["note"] == "考点" and row["quote"]
    assert r2["ok"] is True and r2["action"] == "updated" and total == 1


def test_highlight_text_rejects_rewritten_quote(party_ctx):
    """改写过语义的句子定位不到 → 拒绝并要求逐字摘录；跨课程节点拒绝。"""
    ctx, _kp_id = party_ctx
    bad = ai_agent.execute_tool(
        ctx,
        "highlight_text",
        {"node_code": "party-01-01", "quote": "这句话绝对不在教材正文里xyz"},
        allow_write=True,
    )
    assert bad["ok"] is False and "逐字" in bad["error"]
    other = ai_agent.execute_tool(
        ctx,
        "highlight_text",
        {"node_code": "reform-01-01", "quote": "随便什么句子"},
        allow_write=True,
    )
    assert other["ok"] is False and "不属于当前课程" in other["error"]


def test_highlight_text_tolerates_punctuation_drift(party_ctx):
    """模型摘录时标点全/半角不一致或多了引号 → 仍应定位成功。"""
    ctx, _kp_id = party_ctx
    src = ai_agent.execute_tool(
        ctx, "get_node_text", {"node_code": "party-01-01"}, allow_write=False
    )
    assert src["ok"] is True
    sentence = src["text"].split("。")[0]  # 取第一句
    drifted = sentence.replace("，", ",").replace("、", ",").replace("：", ":") + "」"
    r = ai_agent.execute_tool(
        ctx, "highlight_text", {"node_code": "party-01-01", "quote": drifted}, allow_write=True
    )
    assert r["ok"] is True, r.get("error")


def test_highlight_text_tolerates_tail_drift(party_ctx):
    """模型照着原文写却在中段改字（保留了前 12+ 字前缀）→ 按最长可定位前缀落库。"""
    ctx, _kp_id = party_ctx
    src = ai_agent.execute_tool(
        ctx, "get_node_text", {"node_code": "party-01-01"}, allow_write=False
    )
    body = "".join(src["text"].split())
    quote = body[:14] + "（模型改写从这里开始）" + body[30:40]
    r = ai_agent.execute_tool(
        ctx, "highlight_text", {"node_code": "party-01-01", "quote": quote}, allow_write=True
    )
    assert r["ok"] is True, r.get("error")
    assert r["length"] <= 16


# ---------- 原样重试的短路 ----------
def test_run_events_short_circuits_identical_failures(party_ctx, monkeypatch):
    """同一个工具+同样参数失败两次：第二次必须被拦截提示，不再真实执行。"""
    ctx, _kp_id = party_ctx
    model_rounds = {"n": 0}
    real_exec = ai_agent.execute_tool
    executed = {"n": 0}

    def counting_exec(c, name, args, allow_write):
        executed["n"] += 1
        return real_exec(c, name, args, allow_write)

    def fake_chat(convo, tools=None, temperature=0.4):
        model_rounds["n"] += 1
        bad = {"name": "create_task", "arguments": '{"title":"坏任务","due_date":"明年"}'}
        if model_rounds["n"] <= 2:  # 前两轮模型都原样发同一个坏调用（真机评测里就是这样）
            return {
                "content": "",
                "tool_calls": [
                    {"id": f"c{model_rounds['n']}", "type": "function", "function": dict(bad)}
                ],
            }
        return {"content": "任务没建成：日期格式不对。", "tool_calls": []}

    monkeypatch.setattr(ai_agent.ai_helper, "chat_completion", fake_chat)
    monkeypatch.setattr(ai_agent, "execute_tool", counting_exec)

    final = ai_agent.run(ctx, [{"role": "user", "content": "帮我建个任务"}], allow_write=True)
    assert executed["n"] == 1  # 第二次同参数被短路，没有再执行
    assert len(final["steps"]) == 2
    assert "原样重试没有意义" in final["steps"][1]["summary"]
    assert "日期格式不对" in final["reply"]


def test_caps_were_raised_for_long_tasks():
    """学整章这种长任务需要更多轮次和调用额度（真机评测里 16 次不够用）。"""
    assert ai_agent.MAX_ROUNDS >= 8
    assert ai_agent.MAX_TOOL_CALLS >= 20


# ---------- UI 动作通道：AI 直接切换页面 ----------
def test_navigate_whitelist(party_ctx):
    ctx, _ = party_ctx
    ok = ai_agent.execute_tool(ctx, "navigate", {"route": "/materials"}, allow_write=True)
    assert ok["ok"] is True
    assert ok["ui"] == {"action": "navigate", "route": "/materials"}
    assert "史料笔记" in ok["message"]
    # 非白名单路径必须拒绝，防止 AI 把学生带到不存在的页面
    bad = ai_agent.execute_tool(ctx, "navigate", {"route": "/admin"}, allow_write=True)
    assert bad["ok"] is False


def test_navigate_works_in_readonly_mode(party_ctx):
    """切页面不是写库，只读模式也应该可用。"""
    ctx, _ = party_ctx
    r = ai_agent.execute_tool(ctx, "navigate", {"route": "/practice"}, allow_write=False)
    assert r["ok"] is True and r["route"] == "/practice"
