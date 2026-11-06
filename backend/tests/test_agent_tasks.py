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
    kp = client.post("/api/knowledge-points", json={"title": "第一次国共合作", "course": "党史"}).json()
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
    payload = json.dumps([
        {"type": "单选题", "question": "第一次国共合作发生于哪一年？", "answer": "1924年"},
        {"type": "简答", "question": "简述合作的政治基础。", "answer": "新三民主义"},
    ], ensure_ascii=False)
    r = ai_agent.execute_tool(ctx, "create_questions",
                              {"kp_id": kp_id, "questions": payload}, allow_write=True)
    assert r["ok"] is True and r["created"] == 2
    assert _db_question_count(ctx, kp_id) == 2


def test_single_question_object_is_wrapped(party_ctx):
    ctx, kp_id = party_ctx
    r = ai_agent.execute_tool(ctx, "create_questions",
                              {"kp_id": kp_id,
                               "questions": {"question": "大革命失败的原因？", "answer": "略"}},
                              allow_write=True)
    assert r["ok"] is True and r["created"] == 1


def test_bad_items_are_skipped_with_reasons(party_ctx):
    """混入坏项：跳过并报告原因，好的照常入库。"""
    ctx, kp_id = party_ctx
    r = ai_agent.execute_tool(
        ctx, "create_questions",
        {"kp_id": kp_id,
         "questions": [
             {"question": "好题", "answer": "好答案"},
             "一个字符串",
             {"answer": "没有题干"},
             {"question": "  ", "answer": "空题干"},
         ]},
        allow_write=True)
    assert r["ok"] is True and r["created"] == 1
    assert len(r["skipped"]) == 3
    assert "第2项" in "；".join(r["skipped"]) or "不是对象" in "；".join(r["skipped"])


def test_all_bad_returns_actionable_error(party_ctx):
    """全坏 → 错误信息必须带可照抄的示例，模型才能下一轮改对。"""
    ctx, kp_id = party_ctx
    r = ai_agent.execute_tool(ctx, "create_questions",
                              {"kp_id": kp_id, "questions": ["a", "b"]}, allow_write=True)
    assert r["ok"] is False
    assert "JSON 数组" in r["error"] and '"question"' in r["error"]


def test_oversized_batch_is_truncated_not_rejected(party_ctx):
    ctx, kp_id = party_ctx
    many = [{"question": f"题{i}", "answer": "略"} for i in range(15)]
    r = ai_agent.execute_tool(ctx, "create_questions",
                              {"kp_id": kp_id, "questions": many}, allow_write=True)
    assert r["ok"] is True and r["created"] == ai_agent.MAX_QUESTIONS_PER_CALL


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
            return {"content": "", "tool_calls": [
                {"id": f"c{model_rounds['n']}", "type": "function", "function": dict(bad)}]}
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
