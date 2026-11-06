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
    assert len(read_only) == 9
    assert len(full) == 15
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
    assert len(data["tools"]) == 15
    assert sum(1 for t in data["tools"] if t["write"]) == 6


def _wrong_id(client) -> int:
    """造一条真实错题，返回 wrong_book.id。"""
    client.post("/api/profile/track", json={"track": "party"})
    kp = client.post("/api/knowledge-points", json={"title": "遵义会议", "course": "党史"}).json()
    client.post("/api/questions/generate", json={"kp_id": kp["id"], "num": 1})
    qid = [q for q in client.get("/api/questions").json() if q["kp_id"] == kp["id"]][0]["id"]
    client.post("/api/practice/submit", json={"question_id": qid, "correct": False})
    return client.get("/api/wrong-book").json()[0]["id"]


def test_错因归因打标签(client):
    wid = _wrong_id(client)
    ctx = ai_agent.AgentContext(client.user_id, "party", app_main.db, app_main.now)
    r = ai_agent.execute_tool(
        ctx, "tag_wrong_error",
        {"wrong_id": wid, "error_type": "sequence", "advice": "先把时间轴串一遍"},
        allow_write=True,
    )
    assert r["ok"] is True and r["error_type"] == "时序错位"
    item = client.get("/api/wrong-book").json()[0]
    assert item["error_type"] == "时序错位"
    # 也接受直接写中文分类
    r2 = ai_agent.execute_tool(ctx, "tag_wrong_error",
                               {"wrong_id": wid, "error_type": "记忆不牢"}, allow_write=True)
    assert r2["ok"] is True
    assert client.get("/api/wrong-book").json()[0]["error_type"] == "记忆不牢"


def test_错因归因的边界(client):
    wid = _wrong_id(client)
    ctx = ai_agent.AgentContext(client.user_id, "party", app_main.db, app_main.now)
    # 分类不在词表里 → 拒绝，提示可选值
    bad = ai_agent.execute_tool(ctx, "tag_wrong_error",
                                {"wrong_id": wid, "error_type": "心情不好"}, allow_write=True)
    assert bad["ok"] is False and "error_type" in bad["error"]
    # 别人的错题 → 拒绝（用户隔离）
    other = ai_agent.AgentContext(client.user_id + 999999, "party", app_main.db, app_main.now)
    mine = ai_agent.execute_tool(other, "tag_wrong_error",
                                 {"wrong_id": wid, "error_type": "concept"}, allow_write=True)
    assert mine["ok"] is False
    # 只读模式 → 拒绝
    ro = ai_agent.execute_tool(ctx, "tag_wrong_error",
                               {"wrong_id": wid, "error_type": "concept"}, allow_write=False)
    assert ro["ok"] is False and "写入权限" in ro["error"]
