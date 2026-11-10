"""渠道故障转移测试：主模型超时/限流时自动切备用，不丢上下文。"""

import httpx
import pytest

from app import ai_helper


class FakeResp:
    def __init__(self, status_code=200, text="", content="ok"):
        self.status_code = status_code
        self.text = text
        self.request = None
        self._content = content

    def json(self):
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


@pytest.fixture
def two_providers(monkeypatch):
    """主渠道 primary + 备用渠道 backup 的环境。"""
    monkeypatch.setenv("AI_API_KEY", "k1")
    monkeypatch.setenv("AI_BASE_URL", "https://primary/v1")
    monkeypatch.setenv("AI_MODEL", "m1")
    monkeypatch.setenv("AI_BACKUP_BASE_URL", "https://backup/v1")
    monkeypatch.setenv("AI_BACKUP_API_KEY", "k2")
    monkeypatch.setenv("AI_BACKUP_MODEL", "m2")
    monkeypatch.delenv("AI_PROXY", raising=False)


def test_超时自动切备用(two_providers, monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        if "primary" in url:
            raise httpx.ConnectTimeout("timed out", request=None)
        return FakeResp(content="from-backup")

    monkeypatch.setattr(ai_helper.httpx, "post", fake_post)
    msg = ai_helper.chat_completion([{"role": "user", "content": "hi"}])
    assert msg["content"] == "from-backup"
    assert calls == [
        "https://primary/v1/chat/completions",
        "https://backup/v1/chat/completions",
    ]


def test_429自动切备用(two_providers, monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        if "primary" in url:
            return FakeResp(status_code=429, text='{"detail":"rate limit"}')
        return FakeResp(content="ok")

    monkeypatch.setattr(ai_helper.httpx, "post", fake_post)
    msg = ai_helper.chat_completion([{"role": "user", "content": "hi"}])
    assert msg["content"] == "ok"
    assert len(calls) == 2


def test_无备用时超时原地重试一次(two_providers, monkeypatch):
    """主渠道先超时再成功——没配备用也要扛住瞬时抖动。"""
    monkeypatch.delenv("AI_BACKUP_BASE_URL", raising=False)
    monkeypatch.setattr(ai_helper.time, "sleep", lambda s: None)
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=None)
        return FakeResp(content="retry-ok")

    monkeypatch.setattr(ai_helper.httpx, "post", fake_post)
    msg = ai_helper.chat_completion([{"role": "user", "content": "hi"}])
    assert msg["content"] == "retry-ok"
    assert len(calls) == 2 and all("primary" in c for c in calls)


def test_备用也失败抛最后错误(two_providers, monkeypatch):
    def fake_post(url, **kw):
        raise httpx.ReadTimeout("timed out", request=None)

    monkeypatch.setattr(ai_helper.httpx, "post", fake_post)
    with pytest.raises(httpx.ReadTimeout):
        ai_helper.chat_completion([{"role": "user", "content": "hi"}])


def test_非瞬时不切换_带工具先降级(two_providers, monkeypatch):
    """400（参数问题）不算瞬时故障：带 tools 时先在同渠道去工具降级，不成功再切。"""
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw["json"].get("tools") is not None))
        if kw["json"].get("tools") is not None:
            return FakeResp(status_code=400, text="tools unsupported")
        return FakeResp(content="no-tools-ok")

    monkeypatch.setattr(ai_helper.httpx, "post", fake_post)
    msg = ai_helper.chat_completion(
        [{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {}}]
    )
    assert msg["content"] == "no-tools-ok"
    # 两次调用都在主渠道：先带工具，再去工具
    assert calls == [("https://primary/v1/chat/completions", True),
                     ("https://primary/v1/chat/completions", False)]


def test_调用链对状态机透明(two_providers, monkeypatch):
    """切渠道后 tool_calls 结构原样返回——状态机轮次/上下文不受影响。"""
    def fake_post(url, **kw):
        r = FakeResp()
        r.json = lambda: {"choices": [{"message": {
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "find_node", "arguments": "{}"}}]}}]}
        return r

    monkeypatch.setattr(ai_helper.httpx, "post", fake_post)
    msg = ai_helper.chat_completion(
        [{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {}}]
    )
    assert msg["tool_calls"][0]["function"]["name"] == "find_node"
