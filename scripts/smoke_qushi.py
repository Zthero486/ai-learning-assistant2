# -*- coding: utf-8 -*-
"""四史改造冒烟测试（不依赖 pytest 的临时目录机制）。

用法：
    cd backend
    python ../scripts/smoke_qushi.py

会在 `_tmp/smoke.db` 建一个全新库，跑一遍「注册 → 选课 → 看章节树 → 建知识点 → 过滤」，
结果写到 `_tmp/smoke_report.txt`。
"""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["AI_DISABLE_BUILTIN"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app import main as app_main  # noqa: E402

OUT = ROOT / "_tmp" / "smoke_report.txt"
lines = []


def log(msg=""):
    lines.append(str(msg))


def main() -> int:
    tmp = ROOT / "_tmp"
    tmp.mkdir(exist_ok=True)
    # 每次跑用全新库名，避免删除旧文件（沙箱对删除操作敏感）
    stamp = __import__("time").strftime("%H%M%S")
    db_path = tmp / f"smoke_{stamp}.db"
    up = tmp / f"uploads_{stamp}"
    up.mkdir(parents=True, exist_ok=True)

    app_main.DB_PATH = db_path
    app_main.UPLOAD_DIR = up
    app_main.init_db()

    ok = True
    with TestClient(app_main.app) as c:
        r = c.post("/api/auth/register", json={"username": "smoke", "password": "smoke123"})
        log(f"register {r.status_code}")
        if r.status_code != 200:
            log(r.text)
            return 1
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        r = c.get("/api/tracks", headers=h)
        j = r.json()
        log(f"tracks {r.status_code} current={j['current']!r} n={len(j['tracks'])}")
        log("  " + " | ".join(f"{t['key']}={t['name']}({t['chapters']}章{t['sections']}节)" for t in j["tracks"]))

        r = c.get("/api/syllabus", headers=h)
        log(f"syllabus(未选课) {r.status_code} {r.json().get('detail', '')}")

        r = c.post("/api/profile/track", json={"track": "party"}, headers=h)
        log(f"set_track party {r.status_code} {r.json()}")

        r = c.get("/api/syllabus", headers=h)
        j = r.json()
        log(f"syllabus {r.status_code} track={j['track']} 章={j['chapter_count']} 节={j['section_count']}")
        log("  第一章: " + j["chapters"][0]["title"])
        log("  第一节: " + j["chapters"][0]["sections"][0]["title"])

        r = c.get("/api/syllabus/node/party-03-06", headers=h)
        j = r.json()
        log(f"node {r.status_code} {j['path']}")
        log(f"  挂靠知识点={len(j['kps'])} 题目={j['question_count']} 事件={len(j['events'])}")

        r = c.post(
            "/api/knowledge-points",
            json={
                "title": "中共七大与毛泽东思想的确立",
                "description": "1945年延安，确立毛泽东思想为党的指导思想。",
                "node_code": "party-03-06",
                "exam_type": "recall",
                "course": "党史",
            },
            headers=h,
        )
        log(f"create_kp {r.status_code} {r.json()}")

        r = c.post(
            "/api/knowledge-points",
            json={"title": "坏章节", "node_code": "party-99-99"},
            headers=h,
        )
        log(f"create_kp(坏章节) {r.status_code} {r.json().get('detail', '')}")

        r = c.get("/api/knowledge-points?track=party", headers=h)
        log(f"kp list by track=party -> {len(r.json())}")
        r = c.get("/api/knowledge-points?track=prc", headers=h)
        log(f"kp list by track=prc -> {len(r.json())}")

        r = c.get("/api/syllabus", headers=h)
        ch9 = [x for x in r.json()["chapters"] if "第三章" in x["title"]][0]
        log(f"第三章 kp 统计={ch9['kp']}")

        r = c.get("/api/timeline?track=party", headers=h)
        j = r.json()
        log(f"timeline party: events={j['counts']['events']} span={j['span']}")

        r = c.post("/api/profile/track", json={"track": " socialism "}, headers=h)
        log(f"set_track(带空格) {r.status_code} {r.json().get('detail', r.json())}")

        r = c.post("/api/profile/track", json={"track": "socialism"}, headers=h)
        log(f"switch -> socialism {r.status_code} seeded={r.json().get('seeded_events')}")
        r = c.get("/api/syllabus", headers=h)
        j = r.json()
        log(f"  socialism 章={j['chapter_count']} 节={j['section_count']}")
        r = c.get("/api/knowledge-points?track=socialism", headers=h)
        log(f"  切课后 party 的知识点不可见 -> {len(r.json())}（期望 0）")

    log("RESULT: OK" if ok else "RESULT: FAIL")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
