# -*- coding: utf-8 -*-
"""任务页截图：验证卡片化改造（勾选完成、排序、去复习链接、合并重复按钮）。"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mobile_shots as ms  # noqa: E402

BASE = "http://127.0.0.1:8000"
DEBUG_PORT = 9233
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_tmp" / "mobile_shots"
OUT.mkdir(parents=True, exist_ok=True)


def api_direct(path, body=None, token=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    return json.loads(urllib.request.build_opener(
        urllib.request.ProxyHandler({})).open(req, timeout=20).read())


def find_ws(port):
    for _ in range(40):
        try:
            raw = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                f"http://127.0.0.1:{port}/json", timeout=2).read()
            for t in json.loads(raw):
                if t.get("type") == "page":
                    return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit("no ws")


def main():
    tok = api_direct("/api/auth/login", {"username": "demo", "password": "demo123"})
    user = tok.get("user") or {}
    chrome = next((p for p in ms.CHROME_CANDIDATES if os.path.isfile(p)), None)
    br = subprocess.Popen([
        chrome, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={ROOT / '_tmp' / 'chrome-prof-mobile'}", "--no-first-run",
        "--disable-gpu", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    c = None
    try:
        c = ms.CDP(find_ws(DEBUG_PORT))
        c.send("Page.enable")
        c.send("Emulation.setDeviceMetricsOverride", width=820, height=1180,
               deviceScaleFactor=1.5, mobile=True)
        c.goto(BASE + "/login")
        c.js("localStorage.setItem('lp_token', %s);localStorage.setItem('lp_user', %s);"
             % (json.dumps(tok["token"]), json.dumps(json.dumps(user, ensure_ascii=False))))
        c.goto(BASE + "/tasks", wait=3)
        info = c.js("""(() => ({
            cards: [...document.querySelectorAll('.task')].length,
            ticks: [...document.querySelectorAll('.tick')].length,
            dupBtn: !!document.querySelector('.el-button--warning'),
            links: [...document.querySelectorAll('.kp-link')].map(a => a.innerText.trim()).slice(0, 3),
            firstTitle: document.querySelector('.task .name')?.innerText?.slice(0, 40) || '',
        }))()""")
        print(json.dumps(info, ensure_ascii=False, indent=1))
        # 点第一个勾选圈，验证打卡流转
        c.js("document.querySelector('.tick').click()")
        time.sleep(1.2)
        after = c.js("""(() => ({
            doneNow: !!document.querySelector('.task.done'),
            dupBtn: !!document.querySelector('.el-button--warning'),
        }))()""")
        print(json.dumps(after, ensure_ascii=False, indent=1))
        # 撤销打卡，恢复原状
        c.js("document.querySelector('.task.done .tick')?.click() || document.querySelector('.tick').click()")
        time.sleep(1)
        c.shot("tasks-cards")
        return 0
    finally:
        if c:
            try:
                c.ws.close()
            except Exception:
                pass
        br.terminate()


if __name__ == "__main__":
    sys.exit(main())
