"""教材笔记（text_notes）：划词高亮/批注的 CRUD 与数据隔离。"""

from backend.tests.conftest import AuthClient


def test_text_notes_crud_and_filter(client: AuthClient):
    # 建两条不同节的笔记
    r = client.post(
        "/api/text-notes",
        json={
            "node_code": "party-01-01",
            "offset": 10,
            "length": 20,
            "quote": "第一节的原文片段",
            "note": "",
            "color": "yellow",
        },
    )
    assert r.status_code == 201, r.text
    n1 = r.json()
    assert n1["id"] and n1["uuid"]
    r = client.post(
        "/api/text-notes",
        json={
            "node_code": "party-02-01",
            "offset": 0,
            "length": 8,
            "quote": "第二节原文",
            "note": "这里爱考",
            "color": "green",
        },
    )
    n2 = r.json()
    assert r.status_code == 201

    # 按节过滤
    items = client.get("/api/text-notes", params={"node": "party-01-01"}).json()["items"]
    assert [x["id"] for x in items] == [n1["id"]]
    # 全量
    all_items = client.get("/api/text-notes").json()["items"]
    assert len(all_items) == 2

    # 改批注/颜色
    r = client.patch(f"/api/text-notes/{n1['id']}", json={"note": "改成批注", "color": "pink"})
    assert r.status_code == 200 and r.json()["color"] == "pink"
    # 非法颜色回落
    r = client.patch(f"/api/text-notes/{n1['id']}", json={"color": "black"})
    assert r.json()["color"] == "yellow"
    # 空 payload 400
    assert client.patch(f"/api/text-notes/{n1['id']}", json={}).status_code == 400

    # 删除
    assert client.delete(f"/api/text-notes/{n2['id']}").json()["deleted"] == 1
    assert client.get("/api/text-notes").json()["items"] == [
        client.get("/api/text-notes", params={"node": "party-01-01"}).json()["items"][0]
    ]
    # 删不存在的 404
    assert client.delete(f"/api/text-notes/{n2['id']}").status_code == 404

    # 必填校验
    assert client.post("/api/text-notes", json={"node_code": "party-01-01"}).status_code == 400
    assert client.post("/api/text-notes", json={"quote": "只有原文"}).status_code == 400


def test_text_notes_user_isolation():
    """两个用户同 node 各建各的，互不可见。"""
    c1, c2 = AuthClient(), AuthClient()
    try:
        a = c1.post(
            "/api/text-notes",
            json={
                "node_code": "prc-01-01",
                "offset": 0,
                "length": 5,
                "quote": "甲的笔记",
            },
        ).json()
        c2.post(
            "/api/text-notes",
            json={
                "node_code": "prc-01-01",
                "offset": 30,
                "length": 5,
                "quote": "乙的笔记",
            },
        )
        items = c1.get("/api/text-notes", params={"node": "prc-01-01"}).json()["items"]
        assert len(items) == 1 and items[0]["id"] == a["id"]
        # 乙不能改/删甲的
        assert c2.patch(f"/api/text-notes/{a['id']}", json={"note": "越权"}).status_code == 404
        assert c2.delete(f"/api/text-notes/{a['id']}").status_code == 404
    finally:
        c1.close()
        c2.close()


def test_text_notes_in_sync_chain():
    """text_notes 必须进同步链，否则跨机会丢笔记。"""
    from backend.app import main, sync

    assert "text_notes" in main.USER_TABLES
    assert "text_notes" in sync.CHAIN
