# -*- coding: utf-8 -*-
"""语音输入：录音转文字接口。

浏览器自带的 Web Speech API 是第一优先（前端自己探测，测不到）；
这里只测服务端兜底：AI_ASR_URL 配了就转发、没配就明确报 400。
"""

from app import main as app_main
from tests.conftest import AuthClient  # noqa: F401  保证 conftest 生效


def _wav_bytes() -> bytes:
    """1 秒静音的合法 WAV（RIFF 头），模拟一段录音。"""
    import io
    import struct
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<h", 0) * 16000)
    return buf.getvalue()


def test_health_reports_asr_flag(client):
    data = client.get("/api/health").json()
    assert "asr_available" in data


def test_transcribe_requires_config(client):
    """没配 AI_ASR_URL 时必须明确拒绝，而不是 500。"""
    r = client.post(
        "/api/ai/transcribe",
        files={"file": ("voice.webm", b"\x00\x01\x02", "audio/webm")},
    )
    assert r.status_code == 400
    assert "AI_ASR_URL" in r.json()["detail"]


def test_transcribe_forwards_to_asr(client, monkeypatch):
    """配好 ASR 后：转发文件、回传文本；上游失败要兜成 502 而不是崩。"""
    monkeypatch.setenv("AI_ASR_URL", "https://asr.example.com/v1/audio/transcriptions")
    monkeypatch.setenv("AI_ASR_KEY", "sk-test")

    captured = {}

    def fake_transcribe(filename, content, content_type=""):
        captured["filename"] = filename
        captured["content"] = content
        captured["content_type"] = content_type
        return "遵义会议是1935年1月召开的"

    monkeypatch.setattr(app_main.ai_helper, "transcribe", fake_transcribe)
    audio = _wav_bytes()
    r = client.post(
        "/api/ai/transcribe",
        files={"file": ("voice.webm", audio, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "遵义会议是1935年1月召开的"}
    assert captured["filename"] == "voice.webm"
    assert captured["content"] == audio

    # 上游挂了 → 502 + 可读的错误信息
    def boom(filename, content, content_type=""):
        raise RuntimeError("上游 503")

    monkeypatch.setattr(app_main.ai_helper, "transcribe", boom)
    r2 = client.post(
        "/api/ai/transcribe",
        files={"file": ("voice.webm", audio, "audio/webm")},
    )
    assert r2.status_code == 502
    assert "语音识别失败" in r2.json()["detail"]


def test_transcribe_rejects_huge_audio(client, monkeypatch):
    monkeypatch.setenv("AI_ASR_URL", "https://asr.example.com/v1/audio/transcriptions")
    monkeypatch.setenv("AI_ASR_KEY", "sk-test")
    monkeypatch.setattr(app_main.ai_helper, "MAX_AUDIO_BYTES", 8, raising=False)
    r = client.post(
        "/api/ai/transcribe",
        files={"file": ("big.webm", b"x" * 100, "audio/webm")},
    )
    assert r.status_code == 400
    assert "15MB" in r.json()["detail"]


def test_transcribe_needs_login():
    from fastapi.testclient import TestClient

    c = TestClient(app_main.app)  # 不带令牌的裸客户端
    r = c.post("/api/ai/transcribe", files={"file": ("v.webm", b"x", "audio/webm")})
    assert r.status_code == 401
