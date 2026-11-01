"""历史事件与时间轴（v1.3）。

覆盖三件事：
1. 年份渲染（公元前为负数）与排序（公元前在前）
2. 时间轴聚合（时期分段 + 跨度）
3. 用户隔离与同步导出
"""

from app.main import year_text
from tests.conftest import AuthClient


def _mk(c, **kw):
    body = {"title": "测试事件"}
    body.update(kw)
    r = c.post("/api/events", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_year_text_renders_bc_and_ad():
    assert year_text(-221) == "前221年"
    assert year_text(960) == "960年"
    assert year_text(None) == ""
    # 有 year_label 时优先用原始写法（年号纪年等）
    assert year_text(1069, "熙宁二年") == "熙宁二年"


def test_create_event_backfills_display_text(client):
    e = _mk(client, title="秦统一六国", era="秦", year=-221, people="嬴政")
    assert e["year_text"] == "前221年"
    assert e["era"] == "秦"
    assert e["uuid"], "事件必须带 uuid，否则同步会丢"


def test_events_order_is_chronological(client):
    c = AuthClient()
    _mk(c, title="C", era="近代", year=1911)
    _mk(c, title="A", era="战国", year=-356)
    _mk(c, title="B", era="秦", year=-221)
    titles = [e["title"] for e in c.get("/api/events").json()]
    assert titles == ["A", "B", "C"], titles


def test_timeline_aggregates_eras_and_span(client):
    c = AuthClient()
    _mk(c, title="秦统一", era="秦", year=-221, year_end=-206)
    _mk(c, title="商鞅变法", era="战国", year=-356)
    _mk(c, title="辛亥革命", era="清", year=1911)

    data = c.get("/api/timeline").json()
    assert data["counts"]["events"] == 3
    eras = {e["era"]: e for e in data["eras"]}
    assert set(eras) == {"秦", "战国", "清"}
    assert eras["秦"]["start"] == -221 and eras["秦"]["end"] == -206
    assert data["span"] == {"start": -356, "end": 1911}
    assert data["events"][0]["title"] == "商鞅变法"


def test_events_isolated_between_users():
    a, b = AuthClient(), AuthClient()
    _mk(a, title="甲的事件", year=1000)
    assert [e["title"] for e in b.get("/api/events").json()] == []
    assert len(a.get("/api/events").json()) == 1


def test_update_and_delete_event(client):
    e = _mk(client, title="旧标题", year=1000)
    r = client.put(f"/api/events/{e['id']}", json={"title": "新标题", "impact": "影响很大"})
    assert r.status_code == 200
    assert r.json()["title"] == "新标题"
    assert r.json()["impact"] == "影响很大"

    assert client.delete(f"/api/events/{e['id']}").status_code == 200
    assert client.get("/api/events").json() == []
    # 重复删除返回 404
    assert client.delete(f"/api/events/{e['id']}").status_code == 404


def test_events_included_in_sync_export(client):
    c = AuthClient()
    e = _mk(c, title="同步测试事件", era="唐", year=618)
    payload = c.get("/api/sync/export").json()
    assert "events" in payload
    # 导出是全库快照（跨机同步要带上所有本地账号），按 uuid 精确取自己那条
    mine = [x for x in payload["events"] if x["uuid"] == e["uuid"]]
    assert len(mine) == 1
    assert mine[0]["year"] == 618 and mine[0]["owner"]
    assert mine[0]["era"] == "唐"
