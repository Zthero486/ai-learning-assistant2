# -*- coding: utf-8 -*-
"""教材目录页探针：验证改革开放史各节知识点在页面上可见，并截图留证。

用法（连已运行的 8000 服务）：
    python scripts/syllabus_probe.py
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
    user = {"username": "demo", "track": "reform"}
    log("登录 ok")

    chrome = next((p for p in ms.CHROME_CANDIDATES if os.path.isfile(p)), None)
    if not chrome:
        raise SystemExit("找不到 Chrome/Edge")
    prof = ROOT / "_tmp" / "chrome-prof-mobile"
    br = subprocess.Popen([
        chrome, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check",
        "--disable-gpu", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    c = None
    try:
        c = ms.CDP(find_ws(DEBUG_PORT))
        c.send("Page.enable")
        c.send("Runtime.enable")
        c.send("Emulation.setDeviceMetricsOverride", width=W, height=H,
               deviceScaleFactor=DSF, mobile=True)

        c.goto(BASE + "/login")
        c.js("localStorage.setItem('lp_token', %s);localStorage.setItem('lp_user', %s);"
             % (json.dumps(tok["token"]), json.dumps(json.dumps(user, ensure_ascii=False))))

        c.goto(BASE + "/syllabus", wait=2.5)
        # 展开第一章、点第一节
        c.js("document.querySelector('.chapter-head') && document.querySelector('.chapter-head').click()")
        time.sleep(0.6)
        c.js("document.querySelector('.section') && document.querySelector('.section').click()")
        time.sleep(1.0)
        c.shot("syllabus-kp")

        info = c.js("""(() => {
          const kps = [...document.querySelectorAll('.kp-item')].map(el => ({
            t: el.querySelector('.kp-title')?.textContent.trim().slice(0, 40),
            d: (el.querySelector('.kp-desc')?.textContent || '').trim().length,
          }));
          return {
            path: document.querySelector('.node-path')?.textContent.trim(),
            kpCount: kps.length,
            kps,
            bodyLen: document.body.innerText.length,
          };
        })()""")
        log(json.dumps(info, ensure_ascii=False, indent=2))

        ok = (info.get("kpCount") or 0) >= 1 and all(k["d"] > 50 for k in info["kps"])
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
