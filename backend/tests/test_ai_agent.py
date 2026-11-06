"""AI Agent（对话窗口的底座）测试。

不打网络：只测工具层本身——权限边界、写入校验、去重、错误处理。
「模型会不会自己挑工具」属于线上验证（scripts/smoke_agent.py），不进 CI。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ai_agent  # noqa: E402
from app import main as app_main  # noqa: E402


@pytest.fixture
def party_ctx(client):
    """选课后的上下文：uid 来自已登录的随机用户。"""
    client.post("/api/profile/track", json={"track": "party"})
    tree = client.get("/api/syllabus", params={"track": "party"}).json()
    code = tree["chapters"][0]["sections"][0]["code"]
    ctx = ai_agent.AgentContext(client.user_id, "party", app_main.db, app_main.now)
    return ctx, code


def test_工具数量与权限划分():
    read_only = ai_agent.tool_specs(False)
    full = ai_agent.tool_specs(True)
    assert len(read_only) == 8
    assert len(full) == 13
    assert all(t["function"]["name"] not in {x["function"]["name"] for x in read_only}
               for t in full if t not in read_only)
    assert all(not t["write"] for t in ai_agent.TOOLS.values() if t["spec"] in read_only)


def test_只读模式下写入被拒(party_ctx):
    ctx, code = party_ctx
    r = ai_agent.execute_tool(ctx, "create_task", {"title": "只读模式任务"}, allow_write=False)
    assert r["ok"] is False
    assert "写入权限" in r["error"]


def test_建知识点并去重(party_ctx):
    ctx, code = party_ctx
    first = ai_agent.execute_tool(ctx, "create_knowledge_point",
                                  {"node_code": code, "title": "测试要点", "description": "描述"},
                                  allow_write=True)
    assert first["ok"] and first["id"]
    again = ai_agent.execute_tool(ctx, "create_knowledge_point",
                                  {"node_code": code, "title": "测试要点", "description": "描述"},
                                  allow_write=True)
    assert again["duplicated"] is True
    assert again["id"] == first["id"]


def test_拒绝写入别课节点(party_ctx):
    ctx, _ = party_ctx
    r = ai_agent.execute_tool(ctx, "create_knowledge_point",
                              {"node_code": "prc-01-01", "title": "串课", "description": "x"},
                              allow_write=True)
    assert r["ok"] is False
    assert "不属于当前课程" in r["error"]


def test_生成资料入库可检索(party_ctx):
    ctx, code = party_ctx
    body = "遵义会议确立毛泽东在党中央的领导地位，是党的历史上生死攸关的转折点。" * 4
    r = ai_agent.execute_tool(ctx, "create_material",
                              {"title": "测试生成资料", "content": body, "node_code": code},
                              allow_write=True)
    assert r["ok"] and r["id"]
    hit = ai_agent.execute_tool(ctx, "search_content", {"query": "遵义会议"}, allow_write=True)
    titles = [m["title"] for m in hit["materials"]]
    assert "测试生成资料" in titles


def test_出题与任务(party_ctx):
    ctx, code = party_ctx
    kp = ai_agent.execute_tool(ctx, "create_knowledge_point",
                               {"node_code": code, "title": "出题用要点", "description": "d"},
                               allow_write=True)
    q = ai_agent.execute_tool(ctx, "create_questions", {"kp_id": kp["id"], "questions": [
        {"type": "单选题", "question": "题干？", "answer": "A"},
        {"type": "简答", "question": "简述？", "answer": "答案"},
    ]}, allow_write=True)
    assert q["ok"] and q["created"] == 2

    bad = ai_agent.execute_tool(ctx, "create_task", {"title": "坏日期", "due_date": "下周"},
                                allow_write=True)
    assert bad["ok"] is False

    ok = ai_agent.execute_tool(ctx, "create_task", {"title": "复习要点", "due_date": "2030-01-01"},
                               allow_write=True)
    assert ok["ok"] and ok["id"]


def test_工具异常不抛给上层(party_ctx):
    ctx, _ = party_ctx
    r = ai_agent.execute_tool(ctx, "read_material", {"material_id": 99999999}, allow_write=True)
    assert r["ok"] is False and "error" in r
    r2 = ai_agent.execute_tool(ctx, "不存在的工具", {}, allow_write=True)
    assert r2["ok"] is False


def test_对话接口无key时给提示(client):
    client.post("/api/profile/track", json={"track": "party"})
    r = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "你好"}],
                                         "stream": False})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "unavailable"
    assert "API Key" in data["reply"]


def test_未选课时对话接口报错():
    from tests.conftest import AuthClient

    c = AuthClient()  # 新用户 track 为空
    r = c.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "你好"}]})
    assert r.status_code == 400


def test_工具清单接口(client):
    client.post("/api/profile/track", json={"track": "party"})
    data = client.get("/api/ai/tools").json()
    assert len(data["tools"]) == 13
    assert sum(1 for t in data["tools"] if t["write"]) == 5
