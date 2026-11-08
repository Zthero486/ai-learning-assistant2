# -*- coding: utf-8 -*-
"""看板「史实要点掌握情况」收缩列表探针（平板视口）。

验证点：
  1. 默认渲染的 kp-row 只有 5 条
  2. 展开按钮存在，点击后渲染全部条数
  3. 收起后回到 5 条
  4. 截图留证（默认态 + 展开态）
"""
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
DEBUG_PORT = 9225
W, H, DSF = 820, 1180, 1.5
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_tmp" / "mobile_shots"
OUT.mkdir(parents=True, exist_ok=True)


def log(*a):
    print(*a, flush=True)


def api_direct(path, body=None, token=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.loads(opener.open(req, timeout=20).read())


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
    raise SystemExit("Chrome 调试端口没起来")


def main():
    tok = api_direct("/api/auth/login", {"username": "demo", "password": "demo123"})
    user = tok.get("user") or {"username": "demo", "track": "reform"}
    log("登录 ok")

    chrome = next((p for p in ms.CHROME_CANDIDATES if os.path.isfile(p)), None)
    if not chrome:
        raise SystemExit("找不到 Chrome/Edge")
    prof = ROOT / "_tmp" / "chrome-prof-dash"
    br = subprocess.Popen([
        chrome, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check",
        "--disable-gpu", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    c = None
    try:
        c = ms.CDP(find_ws(DEBUG_PORT))
        c.send("Page.enable")
        c.send("Emulation.setDeviceMetricsOverride", width=W, height=H,
               deviceScaleFactor=DSF, mobile=True)
        c.send("Emulation.setTouchEmulationEnabled", enabled=True)

        c.goto(BASE + "/login")
        c.js("localStorage.setItem('lp_token', %s);localStorage.setItem('lp_user', %s);"
             % (json.dumps(tok["token"]), json.dumps(json.dumps(user, ensure_ascii=False))))

        c.goto(BASE + "/", wait=2.5)
        rows = c.js("document.querySelectorAll('.kp-row').length")
        toggle = c.js(
            "[...document.querySelectorAll('.kp-toggle')].map(e=>e.textContent.trim())[0] || ''")
        c.shot("dashboard-collapsed")
        log(f"默认 rows={rows}, toggle=「{toggle}」")

        ok = rows == 5 and "展开" in toggle
        c.js("[...document.querySelectorAll('.kp-toggle')][0].click()")
        time.sleep(0.8)
        rows2 = c.js("document.querySelectorAll('.kp-row').length")
        toggle2 = c.js(
            "[...document.querySelectorAll('.kp-toggle')].map(e=>e.textContent.trim())[0] || ''")
        c.shot("dashboard-expanded")
        log(f"展开后 rows={rows2}, toggle=「{toggle2}」")
        ok = ok and rows2 > 5 and "收起" in toggle2
        c.js("[...document.querySelectorAll('.kp-toggle')][0].click()")
        time.sleep(0.8)
        rows3 = c.js("document.querySelectorAll('.kp-row').length")
        log(f"收起后 rows={rows3}")
        ok = ok and rows3 == 5

        log("结果:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        if c:
            try:
                c.ws.close()
            except Exception:
                pass
        br.terminate()


if __name__ == "__main__":
    sys.exit(main())
