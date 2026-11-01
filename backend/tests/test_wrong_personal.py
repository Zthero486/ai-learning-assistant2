"""错题闭环：做错入库 → 连续答对逐步出库 → AI 按错题出同类题。

规则：MASTERY_STREAK = 2，连续答对两次才移出活跃错题库；中途答错清零重来。
"""

from tests.conftest import AuthClient


def _make_questions(c, num=2, course="秦"):
    kp = c.post("/api/knowledge-points", json={"title": "秦统一六国", "course": course}).json()
    c.post("/api/questions/generate", json={"kp_id": kp["id"], "num": num})
    return [q for q in c.get("/api/questions").json() if q["kp_id"] == kp["id"]]


def test_wrong_answer_enters_wrong_book():
    c = AuthClient()
    qs = _make_questions(c, 1)
    assert qs, "没生成题目"
    r = c.post("/api/practice/submit", json={"question_id": qs[0]["id"], "correct": False})
    assert r.status_code == 200
    items = c.get("/api/wrong-book").json()
    assert len(items) == 1
    assert items[0]["wrong_count"] == 1
    assert items[0]["correct_streak"] == 0


def test_correct_answers_gradually_remove_question():
    c = AuthClient()
    q = _make_questions(c, 1)[0]
    qid = q["id"]

    # 做错一次 → 进错题本
    c.post("/api/practice/submit", json={"question_id": qid, "correct": False})
    assert len(c.get("/api/wrong-book").json()) == 1

    # 第一次答对：计数 +1，但仍在错题本（防止蒙对就算掌握）
    r = c.post("/api/practice/submit", json={"question_id": qid, "correct": True})
    wb = r.json()["wrong_book"]
    assert wb["correct_streak"] == 1 and wb["resolved"] == 0
    assert len(c.get("/api/wrong-book").json()) == 1

    # 第二次答对：达到阈值，移出活跃错题本
    r = c.post("/api/practice/submit", json={"question_id": qid, "correct": True})
    wb = r.json()["wrong_book"]
    assert wb["correct_streak"] == 2 and wb["resolved"] == 1
    assert c.get("/api/wrong-book").json() == []
    # 记录本身保留（可追溯），只是不再出现在活跃错题本
    assert len(c.get("/api/wrong-book?only_unresolved=false").json()) == 1


def test_wrong_again_resets_streak():
    c = AuthClient()
    qid = _make_questions(c, 1)[0]["id"]
    c.post("/api/practice/submit", json={"question_id": qid, "correct": False})
    c.post("/api/practice/submit", json={"question_id": qid, "correct": True})
    # 连对 1 次后又错 → 清零，次数累加
    r = c.post("/api/practice/submit", json={"question_id": qid, "correct": False})
    wb = r.json()["wrong_book"]
    assert wb["correct_streak"] == 0
    assert wb["wrong_count"] == 2
    assert wb["resolved"] == 0


def test_personal_generate_requires_wrong_questions():
    c = AuthClient()
    r = c.post("/api/questions/generate-personal", json={"num": 3})
    assert r.status_code == 400
    assert "错题" in r.json()["detail"]


def test_personal_generate_uses_wrong_book():
    c = AuthClient()
    qs = _make_questions(c, 2)
    assert len(qs) >= 2
    for q in qs[:2]:
        c.post("/api/practice/submit", json={"question_id": q["id"], "correct": False})

    before = len(c.get("/api/questions").json())
    r = c.post("/api/questions/generate-personal", json={"num": 3})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["based_on_wrong"] == 2
    assert data["generated"] >= 1
    # 新题确实入库了
    assert len(c.get("/api/questions").json()) == before + data["generated"]


def test_personal_generate_isolated_between_users():
    a, b = AuthClient(), AuthClient()
    qs = _make_questions(a, 1)
    a.post("/api/practice/submit", json={"question_id": qs[0]["id"], "correct": False})
    # 甲的错题不能影响乙
    assert b.post("/api/questions/generate-personal", json={"num": 3}).status_code == 400
    assert a.post("/api/questions/generate-personal", json={"num": 3}).status_code == 200
