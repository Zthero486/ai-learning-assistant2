# -*- coding: utf-8 -*-
"""错题间隔复习：FSRS 排期（移植自 py-fsrs）+ 缺包时的天数阶梯降级。

两条底线：
1. 排期算法可以换，**表结构和接口返回不能变**（前端、同步、导出都依赖）。
2. 没装 fsrs 时功能必须还在，只是退回 1/2/4/7/15 天阶梯。
"""

import json
import uuid as uuid_mod
from datetime import datetime, timedelta

import pytest
from app import main as app_main
from app import srs
from tests.conftest import AuthClient

HAS_FSRS = srs.AVAILABLE


def _row(**kw):
    base = {
        "wrong_count": 1,
        "correct_streak": 0,
        "resolved": 0,
        "next_review_at": "",
        "last_wrong_at": "",
        "srs": "",
    }
    base.update(kw)
    return base


def _one_question(c) -> int:
    kp = c.post("/api/knowledge-points", json={"title": "遵义会议", "course": "党史"}).json()
    c.post("/api/questions/generate", json={"kp_id": kp["id"], "num": 1})
    return [q for q in c.get("/api/questions").json() if q["kp_id"] == kp["id"]][0]["id"]


# ==================== 纯算法层 ====================
@pytest.mark.skipif(not HAS_FSRS, reason="未安装 fsrs，走降级分支")
def test_wrong_then_correct_grows_interval():
    """答错排到明天，连对之后间隔必须变长（这就是 FSRS 的全部意义）。"""
    now = datetime.now()
    plan1 = srs.review(_row(), correct=False, at=now)
    assert plan1["algorithm"] == "fsrs"
    assert plan1["srs"], "卡片状态必须序列化，否则下次没得算"
    assert 0.9 <= plan1["interval_days"] <= 1.1

    row = _row(srs=plan1["srs"], next_review_at=plan1["next_review_at"])
    plan2 = srs.review(row, correct=True, at=now + timedelta(days=1))
    assert plan2["interval_days"] > plan1["interval_days"]

    row2 = _row(srs=plan2["srs"])
    plan3 = srs.review(row2, correct=True, at=now + timedelta(days=3))
    assert plan3["interval_days"] > plan2["interval_days"]
    # 稳定度是单调抬升的，难度不会因为答对而变高
    assert plan3["stability"] >= plan2["stability"]
    assert plan3["difficulty"] <= plan2["difficulty"] + 0.01


@pytest.mark.skipif(not HAS_FSRS, reason="未安装 fsrs")
def test_legacy_row_keeps_its_due_date():
    """升级前的老错题：没有 srs JSON，但 next_review_at 不能丢。"""
    legacy = _row(next_review_at=(datetime.now() + timedelta(days=5)).isoformat(timespec="seconds"))
    card = srs.row_to_card(legacy)
    assert card is not None
    assert abs((srs._to_local_naive(card.due) - datetime.now()).days - 5) <= 1


def test_ladder_falls_back_without_fsrs(monkeypatch):
    """fsrs 不可用 → 老阶梯（1/2/4/7/15 天）照常工作。"""
    monkeypatch.setattr(srs, "scheduler", lambda: None)
    plan = srs.review(_row(wrong_count=3), correct=False)
    assert plan["algorithm"] == "ladder"
    assert plan["srs"] == ""
    assert plan["interval_days"] == 4.0  # 第 3 次错 → 阶梯第 3 档
    # 库里存的是截到秒的时间串，跨零头用四舍五入，别用 timedelta.days
    days = round((srs.parse_iso(plan["next_review_at"]) - datetime.now()).total_seconds() / 86400)
    assert days == 4


def test_describe_and_due_state():
    assert srs.describe(1.0) == "1 天"
    assert srs.describe(0.02).endswith("分钟")
    assert srs.describe(0.5) == "12 小时"
    assert srs.describe_interval("") == ""
    tomorrow = (datetime.now() + timedelta(days=1)).isoformat(timespec="seconds")
    assert srs.describe_interval(tomorrow) == "明天复习"
    yesterday = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
    assert srs.describe_interval(yesterday).startswith("已逾期")
    assert srs.due_state("") == (True, 0)  # 没排期 = 立刻可复习
    assert srs.due_state(yesterday)[0] is True
    assert srs.due_state(tomorrow)[0] is False


def test_card_meta_tolerates_garbage():
    """脏 JSON 不能让错题本列表崩。"""
    assert srs.card_meta("not-a-json") == {
        "stability": None,
        "difficulty": None,
        "retrievability": None,
    }
    assert srs.card_meta("")["stability"] is None


# ==================== 接口层 ====================
def test_submit_returns_schedule_and_persists_state():
    c = AuthClient()
    qid = _one_question(c)
    r = c.post("/api/practice/submit", json={"question_id": qid, "correct": False})
    assert r.status_code == 200, r.text
    body = r.json()
    sched = body["schedule"]
    assert sched["algorithm"] in ("fsrs", "ladder")
    assert sched["next_review_at"]
    assert sched["interval_text"]
    # 数据库里确实存了卡片状态（同步时才能把排期带到另一台机器）
    conn = app_main.db()
    row = conn.execute(
        "SELECT srs, next_review_at FROM wrong_book WHERE question_id=? AND user_id=?",
        (qid, c.user_id),
    ).fetchone()
    conn.close()
    assert row["next_review_at"] == sched["next_review_at"]
    if HAS_FSRS:
        assert json.loads(row["srs"])["last_review"]


def test_wrong_book_rows_carry_schedule_fields():
    c = AuthClient()
    qid = _one_question(c)
    c.post("/api/practice/submit", json={"question_id": qid, "correct": False})
    item = c.get("/api/wrong-book").json()[0]
    for key in ("srs_due", "srs_days_until", "srs_interval_text", "srs_stability"):
        assert key in item


def test_review_due_queue_orders_by_schedule():
    c = AuthClient()
    qids = []
    kp = c.post("/api/knowledge-points", json={"title": "井冈山", "course": "党史"}).json()
    c.post("/api/questions/generate", json={"kp_id": kp["id"], "num": 3})
    qids = [q["id"] for q in c.get("/api/questions").json() if q["kp_id"] == kp["id"]]
    assert len(qids) >= 2
    for qid in qids[:2]:
        c.post("/api/practice/submit", json={"question_id": qid, "correct": False})

    # 刚做错的两道排在明天 → 今天不催，只列「最近要复习的」
    data = c.get("/api/review/due").json()
    assert data["due_count"] == 0
    assert len(data["upcoming"]) == 2
    assert data["algorithm"] in ("fsrs", "ladder")

    # 手工把其中一条挪到过去 → 立刻进入今日队列
    conn = app_main.db()
    past = (datetime.now() - timedelta(days=3)).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE wrong_book SET next_review_at=? WHERE question_id=? AND user_id=?",
        (past, qids[0], c.user_id),
    )
    conn.commit()
    conn.close()
    data = c.get("/api/review/due").json()
    assert data["due_count"] == 1
    assert data["items"][0]["question_id"] == qids[0]
    assert data["items"][0]["srs_days_until"] < 0


def test_review_due_isolated_between_users():
    a, b = AuthClient(), AuthClient()
    qid = _one_question(a)
    a.post("/api/practice/submit", json={"question_id": qid, "correct": False})
    conn = app_main.db()
    conn.execute(
        "UPDATE wrong_book SET next_review_at=? WHERE question_id=?",
        ((datetime.now() - timedelta(days=1)).isoformat(timespec="seconds"), qid),
    )
    conn.commit()
    conn.close()
    assert a.get("/api/review/due").json()["due_count"] == 1
    assert b.get("/api/review/due").json()["due_count"] == 0


def test_sync_export_includes_srs_state():
    """同步必须带上 srs 字段 —— 少了它，换台电脑复习计划就重置了。"""
    from app.sync import build_export

    c = AuthClient()
    qid = _one_question(c)
    c.post("/api/practice/submit", json={"question_id": qid, "correct": False})
    conn = app_main.db()
    payload = build_export(conn)
    conn.close()
    mine = [r for r in payload["wrong_book"] if r["question_uuid"]]
    assert mine, "导出里应该有错题记录"
    assert "srs" in mine[0]


def test_mastery_streak_still_removes_card():
    """FSRS 之外保留原来的「连对 2 次出库」规则，行为对用户可见。"""
    c = AuthClient()
    qid = _one_question(c)
    c.post("/api/practice/submit", json={"question_id": qid, "correct": False})
    c.post("/api/practice/submit", json={"question_id": qid, "correct": True})
    r = c.post("/api/practice/submit", json={"question_id": qid, "correct": True})
    wb = r.json()["wrong_book"]
    assert wb["correct_streak"] == 2
    assert wb["resolved"] == 1
    assert c.get("/api/wrong-book").json() == []
    assert c.get("/api/review/due").json()["due_count"] == 0


def test_srs_column_survives_uuid_migration():
    """新增列必须幂等：反复 init 不报错、不丢数据。"""
    conn = app_main.db()
    uid = "t" + uuid_mod.uuid4().hex[:8]
    conn.execute(
        "INSERT INTO users(uuid,username,password_hash,salt,display_name,created_at)"
        " VALUES(?,?,?,?,?,?)",
        (uuid_mod.uuid4().hex, uid, "x", "y", "", "2026-11-06T00:00:00"),
    )
    conn.commit()
    conn.close()
    app_main.migrate_qushi(app_main.db())
    cols = {r[1] for r in app_main.db().execute("PRAGMA table_info(wrong_book)")}
    assert "srs" in cols
