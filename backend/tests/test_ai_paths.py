"""AI 链路冒烟：用假的大模型返回，覆盖 build_context / 解析 / 降级三条路径。

背景：`build_context()` 曾引用未定义的 `MAX_CONTEXT_CHARS`，导致所有带上下文的
AI 接口（出题 / 答疑 / 总结）在真实 key 下必然 NameError，但因为测试全走规则引擎
降级路径，一直没被发现。这里把 AI 分支真正跑一遍。
"""

import json

import pytest
from app import ai_helper, main


@pytest.fixture
def fake_llm(monkeypatch):
    """把大模型调用换成本地假实现，记录收到的 prompt 供断言。"""
    calls = []

    def _call(system_prompt: str, user_prompt: str) -> str:
        calls.append((system_prompt, user_prompt))
        return json.dumps(
            [
                {
                    "type": "名词解释",
                    "question": "解释「郡县制」",
                    "answer": "秦朝地方行政制度，长官由皇帝任免、不世袭。",
                }
            ],
            ensure_ascii=False,
        )

    monkeypatch.setenv("AI_API_KEY", "test-key-1234567890")
    monkeypatch.setenv("AI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AI_MODEL", "fake-model")
    monkeypatch.setattr(ai_helper, "call_llm", _call)
    yield calls
    for name in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL"):
        monkeypatch.delenv(name, raising=False)


def _upload(client, content="秦朝推行郡县制，郡县长官由皇帝直接任免。"):
    resp = client.post(
        "/api/materials/upload",
        files={"file": ("秦制.md", content.encode("utf-8"), "text/markdown")},
        data={"course": "秦"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


class TestBuildContext:
    def test_拼接与截断(self):
        chunks = ["甲" * 10, "乙" * 10]
        assert main.build_context(chunks) == "甲" * 10 + "\n\n" + "乙" * 10
        # 超过上限时立刻停止累加
        assert main.build_context(["甲" * 30, "乙" * 30], limit=40) == "甲" * 30

    def test_空列表返回空串(self):
        assert main.build_context([]) == ""


class TestAiPaths:
    def test_出题走大模型(self, client, fake_llm):
        mid = _upload(client)
        kp = client.post(
            "/api/knowledge-points",
            json={"title": "郡县制", "course": "秦", "material_id": mid},
        ).json()
        r = client.post("/api/questions/generate", json={"kp_id": kp["id"], "num": 1})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source"] == "ai" and body["generated"] == 1
        assert fake_llm, "应当真的调用了大模型"

    def test_无史料的知识点也能出题(self, client, fake_llm):
        """知识点没关联史料时，用描述/标题当上下文，而不是直接降级。"""
        kp = client.post(
            "/api/knowledge-points",
            json={
                "title": "鸦片战争与《南京条约》",
                "course": "晚清",
                "description": "1840—1842 年",
            },
        ).json()
        r = client.post("/api/questions/generate", json={"kp_id": kp["id"], "num": 1})
        assert r.json()["source"] == "ai"
        assert "1840—1842 年" in fake_llm[-1][1]  # 描述被拼进了 prompt

    def test_答疑走大模型(self, client, fake_llm):
        mid = _upload(client)
        r = client.post("/api/ai/ask", json={"question": "郡县长官怎么产生？", "material_id": mid})
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "ai"

    def test_总结走大模型(self, client, fake_llm):
        mid = _upload(client)
        r = client.post("/api/ai/summarize", json={"material_id": mid})
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "ai"

    def test_大模型异常时降级并标注原因(self, client, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "test-key-1234567890")
        kp = client.post("/api/knowledge-points", json={"title": "郡县制", "course": "秦"}).json()

        def boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(ai_helper, "call_llm", boom)
        body = client.post("/api/questions/generate", json={"kp_id": kp["id"], "num": 2}).json()
        assert body["source"] == "fallback" and body["reason"] == "ai_error"
        monkeypatch.delenv("AI_API_KEY", raising=False)


class Test内置默认Key:
    """打包版会把阶跃 key 冻结进 exe，作为「默认供应商」；用户配置优先于它。"""

    @pytest.fixture
    def builtin(self, monkeypatch):
        monkeypatch.delenv("AI_DISABLE_BUILTIN", raising=False)
        monkeypatch.setattr(ai_helper, "_BUILTIN_API_KEY", "sk-builtin-0123456789")
        for name in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL", "DEEPSEEK_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        yield

    def test_没有用户配置时走内置阶跃(self, builtin):
        assert ai_helper.is_available() is True
        assert ai_helper.key_source() == "builtin"
        assert ai_helper.get_api_key() == "sk-builtin-0123456789"
        assert ai_helper.get_base_url() == ai_helper.PROVIDER_PRESETS["stepfun"]["base_url"]
        assert ai_helper.get_model() == ai_helper.PROVIDER_PRESETS["stepfun"]["model"]

    def test_用户配置优先于内置(self, builtin, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "sk-user-0987654321")
        monkeypatch.setenv("AI_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("AI_MODEL", "my-model")
        assert ai_helper.key_source() == "custom"
        assert ai_helper.get_api_key() == "sk-user-0987654321"
        assert ai_helper.get_base_url() == "https://api.example.com/v1"
        assert ai_helper.get_model() == "my-model"

    def test_可用开关关掉内置(self, builtin, monkeypatch):
        monkeypatch.setenv("AI_DISABLE_BUILTIN", "1")
        assert ai_helper.is_available() is False
        assert ai_helper.key_source() == "none"

    def test_健康检查暴露来源(self, builtin, client):
        body = client.get("/api/health").json()
        assert body["ai_available"] is True and body["ai_source"] == "builtin"

    def test_留空保存等于恢复默认(self, builtin, client, monkeypatch, tmp_path):
        # 一定要把 .env 指到临时文件：真实 backend/.env 里有开发机的 key，
        # 「恢复默认」会重写这个文件，误删掉真 key 就麻烦了。
        env_file = tmp_path / ".env"
        env_file.write_text("AI_API_KEY=sk-leftover-123456\nOTHER=1\n", encoding="utf-8")
        monkeypatch.setattr(ai_helper.apppaths, "env_file", lambda: env_file)

        r = client.post(
            "/api/config/ai",
            json={"api_key": "", "base_url": "", "model": "", "proxy": ""},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reset"] is True and body["source"] == "builtin"
        text = env_file.read_text(encoding="utf-8")
        assert "sk-leftover" not in text and "OTHER=1" in text  # 只清 AI_* 行
        assert client.get("/api/config/ai").json()["source_label"].startswith("内置阶跃")
