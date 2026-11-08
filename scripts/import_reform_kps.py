# -*- coding: utf-8 -*-
"""把 scripts/reform_kps.json 里的知识点导入 demo 账号（走本地 API，幂等）。

幂等规则：同一 node_code 下已存在同名 title 就跳过。
用法：  python scripts/import_reform_kps.py [--base http://127.0.0.1:8000]
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "reform_kps.json"
BASE = "http://127.0.0.1:8000"


def log(*a):
    print(*a, flush=True)


def api(path, body=None, token="", method="POST"):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.loads(opener.open(req, timeout=20).read())


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--base":
        global BASE
        BASE = sys.argv[2]

    login = api("/api/auth/login", {"username": "demo", "password": "demo123"})
    tok = login["token"]
    user = login.get("user") or {}
    log("登录 ok，track =", user.get("track"))

    kps = json.loads(DATA.read_text(encoding="utf-8"))
    log(f"数据文件共 {len(kps)} 条")

    # 现有知识点：node_code -> set(title)，用于幂等跳过
    existing = {}
    page = api("/api/knowledge-points", token=tok, method="GET")
    for k in page if isinstance(page, list) else page.get("items", page.get("kps", [])):
        existing.setdefault(k["node_code"], set()).add(k["title"])
    log(f"账号现有知识点 {sum(len(v) for v in existing.values())} 条")

    created = skipped = failed = 0
    for kp in kps:
        if kp["title"] in existing.get(kp["node_code"], set()):
            skipped += 1
            continue
        body = {
            "title": kp["title"],
            "description": kp["description"],
            "node_code": kp["node_code"],
            "course": "reform",
        }
        try:
            api("/api/knowledge-points", body, token=tok)
            created += 1
        except Exception as e:
            failed += 1
            log(f"[FAIL] {kp['node_code']} {kp['title']}: {e}")
        time.sleep(0.04)

    log(f"完成：新建 {created}，跳过 {skipped}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
