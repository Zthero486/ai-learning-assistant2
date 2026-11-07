# -*- coding: utf-8 -*-
"""课程隔离回归（2026-11-07 用户反馈：切到改革开放史还看到党史的复习任务）。

约定：一个账号只学一门，但切换课程后，除四史时间轴（events，全局共用）外的
所有功能数据都必须严格按课程隔离——切到哪门课，就只看哪门课的资料、知识点、
题目、任务和错题。这里的用例把这条约束固化下来。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import main as app_main  # noqa: E402
from tests.conftest import AuthClient  # noqa: F401


def _seed_party(client, tmp_path, monkeypatch):
    """给当前用户造一批党史数据：任务、资料、知识点（挂在党史章节下）。"""
    # 上传目录指到本测试的临时目录，避免依赖其他用例动过的全局 UPLOAD_DIR
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_main, "UPLOAD_DIR", upload_dir)
    client.post("/api/profile/track", json={"track": "party"})
    kp = client.post(
        "/api/knowledge-points",
        json={"title": "遵义会议", "course": "党史", "node_code": "party-03-02"},
    ).json()
    task = client.post(
        "/api/tasks", json={"title": "复习遵义会议", "course": "党史", "due_date": "2026-12-01"}
    ).json()
    mat = client.post(
        "/api/materials/upload",
        data={"title": "党史资料", "course": "党史"},
        files={"file": ("m.txt", "遵义会议的内容".encode("utf-8"), "text/plain")},
    ).json()
    q = client.post(
        "/api/questions/generate",
        json={"kp_id": kp["id"], "num": 2, "types": ["简答"]},
    ).json()
    return kp, task, mat, q


def _switch(client, track):
    r = client.post("/api/profile/track", json={"track": track})
    assert r.status_code == 200, r.text


def test_switch_track_hides_other_course_data(client, tmp_path, monkeypatch):
    """切到 reform 后，party 的任务/资料/知识点/题目都必须消失。"""
    _seed_party(client, tmp_path, monkeypatch)

    # 党史视角：都能看到
    assert any("遵义会议" in t["title"] for t in client.get("/api/tasks").json())
    assert client.get("/api/materials").json()
    assert client.get("/api/knowledge-points").json()
    assert client.get("/api/questions").json()

    _switch(client, "reform")

    # 改革开放史视角：全部为空
    assert client.get("/api/tasks").json() == []
    assert client.get("/api/materials").json() == []
    assert client.get("/api/knowledge-points").json() == []
    assert client.get("/api/questions").json() == []
    assert client.get("/api/wrong-book").json() == []
    # 统计也要跟着归零（题目/错题都限本课）
    summary = client.get("/api/practice/summary").json()
    assert summary["total"] == 0 and summary["active_wrong"] == 0
    # 搜索不串课
    s = client.get("/api/search", params={"q": "遵义"}).json()
    assert not s["materials"] and not s["knowledge_points"] and not s["questions"] and not s["tasks"]

    # 切回党史，数据原样还在
    _switch(client, "party")
    assert any("遵义会议" in t["title"] for t in client.get("/api/tasks").json())
    assert client.get("/api/questions").json()


def test_tasks_created_without_course_fall_into_current_track(client):
    """手动建任务不传课程时，自动落到当前选的课程（不再进「未分类」黑洞）。"""
    client.post("/api/profile/track", json={"track": "reform"})
    client.post("/api/tasks", json={"title": "学十二届三中全会"})
    rows = client.get("/api/tasks").json()
    assert len(rows) == 1 and rows[0]["course"] == "reform"


def test_course_aliases_normalized_on_write(client):
    """中文课程名/旧写法写入时归一成 track 码，各课之间不混。"""
    client.post("/api/profile/track", json={"track": "party"})
    client.post("/api/tasks", json={"title": "党史任务", "course": "党史"})
    client.post("/api/tasks", json={"title": "party任务", "course": "party"})
    rows = client.get("/api/tasks").json()
    assert {r["course"] for r in rows} == {"party"}

    _switch(client, "prc")
    assert client.get("/api/tasks").json() == []


def test_migration_normalizes_legacy_course_values(client):
    """存量中文课程名（党史等）由启动迁移统一归一成 track 码。"""
    client.post("/api/profile/track", json={"track": "party"})
    client.post("/api/tasks", json={"title": "旧写法任务", "course": "党史"})
    # 绕过写接口直接改回旧值，模拟升级前的存量库
    conn = app_main.db()
    conn.execute("UPDATE tasks SET course='党史' WHERE title='旧写法任务'")
    conn.commit()
    conn.close()
    # 重新跑归一（init_db 里做的是同一件事）
    conn = app_main.db()
    app_main._normalize_courses(conn)
    row = conn.execute("SELECT course FROM tasks WHERE title='旧写法任务'").fetchone()
    conn.close()
    assert row["course"] == "party"


def test_kp_coarse_node_code_visible_in_track(client):
    """只打粗标签（node_code=track，不带 -xx-xx）的知识点在选课后仍可见。"""
    client.post("/api/profile/track", json={"track": "socialism"})
    client.post("/api/knowledge-points", json={"title": "巴黎公社", "course": "社会主义发展史"})
    rows = client.get("/api/knowledge-points").json()
    assert any(k["title"] == "巴黎公社" for k in rows)


def test_events_not_isolated_by_track(client):
    """四史时间轴是全局共用的，切换课程后事件依然可见。"""
    client.post("/api/profile/track", json={"track": "party"})
    r = client.post(
        "/api/events",
        json={"title": "十一届三中全会", "year": 1978, "node_code": "party-10-01"},
    )
    assert r.status_code == 200, r.text
    _switch(client, "reform")
    events = client.get("/api/events").json()
    assert any("十一届三中全会" in e["title"] for e in events)
