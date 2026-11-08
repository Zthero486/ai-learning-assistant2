# -*- coding: utf-8 -*-
"""侧栏课程徽标快速切换探针：点徽标 → 下拉四史 → 切换 → 校验 localStorage 与服务端生效。

用法（连已运行的 8000 服务）：
    python scripts/track_switch_probe.py
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
DEBUG_PORT = 9226
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
    orig_track = (tok.get("user") or {}).get("track") or "reform"
    log("登录 ok, 原课程 =", orig_track)

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
    ok = True
    try:
        c = ms.CDP(find_ws(DEBUG_PORT))
        c.send("Page.enable")
        c.send("Runtime.enable")
        c.send("Emulation.setDeviceMetricsOverride", width=W, height=H,
               deviceScaleFactor=DSF, mobile=True)
        c.goto(BASE + "/login")
        c.js("localStorage.setItem('lp_token', %s);localStorage.setItem('lp_user', %s);"
             % (json.dumps(tok["token"]), json.dumps(json.dumps(tok["user"], ensure_ascii=False))))
        c.goto(BASE + "/", wait=2.5)

        # 1. 点课程徽标，弹出自定义四史面板
        c.js("document.querySelector('.track-chip') && document.querySelector('.track-chip').click()")
        time.sleep(0.5)
        info = c.js("""(() => {
          const items = [...document.querySelectorAll('.track-menu-item')].map(
            el => el.textContent.trim());
          return { items, chipText: document.querySelector('.track-chip')?.textContent.trim() };
        })()""")
        log("徽标:", info.get("chipText"), "面板项:", json.dumps(info.get("items"), ensure_ascii=False))
        c.shot("track-dropdown")
        if len(info.get("items") or []) < 4:
            log("[FAIL] 面板里不足四史"); ok = False

        # 2. 切到另一门课（党史；若本来就在党史则切新中国史），轮询等待生效
        target = "party" if orig_track != "party" else "prc"
        tname = {"party": "党史", "prc": "新中国史", "reform": "改革开放史", "socialism": "社会主义发展史"}
        c.js(f"""(() => {{
          const el = [...document.querySelectorAll('.track-menu-item')]
            .find(e => e.textContent.includes('{tname[target]}'));
          el && el.click();
        }})()""")
        after = None
        for _ in range(24):  # 最多 7 秒：等 POST 返回 + 整页刷新
            time.sleep(0.3)
            after = c.js("(() => JSON.parse(localStorage.getItem('lp_user')||'{}').track || '')()")
            if after == target:
                break
        log("切换后 localStorage.track =", after)
        if after != target:
            log("[FAIL] 切换未生效"); ok = False
        c.shot("track-switched")

        # 3. 切回原课程（页面已刷新，重新开面板）
        time.sleep(1.0)
        c.js("document.querySelector('.track-chip') && document.querySelector('.track-chip').click()")
        time.sleep(0.5)
        c.js(f"""(() => {{
          const el = [...document.querySelectorAll('.track-menu-item')]
            .find(e => e.textContent.includes('{tname[orig_track]}'));
          el && el.click();
        }})()""")
        back = None
        for _ in range(24):
            time.sleep(0.3)
            back = c.js("(() => JSON.parse(localStorage.getItem('lp_user')||'{}').track || '')()")
            if back == orig_track:
                break
        log("切回后 localStorage.track =", back)
        if back != orig_track:
            log("[FAIL] 没切回原课程"); ok = False

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
