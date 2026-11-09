# -*- coding: utf-8 -*-
"""教材正文探针：验证教材目录页能显示教材原文（不是只有知识点）。

用法（连已运行的 8000 服务）：
    python scripts/syllabus_text_probe.py
    python scripts/syllabus_text_probe.py --node reform-01-01   # 指定先点开某节
"""
import argparse
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
DEBUG_PORT = 9231
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", default="")
    args = ap.parse_args()

    tok = api_direct("/api/auth/login", {"username": "demo", "password": "demo123"})
    me = api_direct("/api/auth/me", token=tok["token"])
    track = (me.get("user") or me).get("track") or "reform"
    user = {"username": "demo", "track": track}
    log("登录 ok，课程 =", track)

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

        c.goto(BASE + "/syllabus", wait=3.0)
        c.shot("syllabus-text-chapter")

        # 点到「本章正文」后面的第一节，验证节级正文
        c.js("""(() => {
          const rows = [...document.querySelectorAll('.section')];
          const target = rows.find(r => !r.classList.contains('chapter-text'));
          if (target) target.click();
        })()""")
        time.sleep(1.2)
        c.shot("syllabus-text-section")

        info = c.js("""(() => {
          const body = document.querySelector('.text-body');
          const ps = body ? [...body.querySelectorAll('p')] : [];
          return {
            path: document.querySelector('.node-path')?.textContent.trim(),
            hasTextBody: !!body,
            visible: body ? body.offsetParent !== null : false,
            paraCount: ps.length,
            chars: body ? body.innerText.length : 0,
            first: ps[0] ? ps[0].textContent.trim().slice(0, 80) : '',
            fontPx: body ? getComputedStyle(body).fontSize : '',
            headLine: document.querySelector('.text-head')?.innerText.replace(/\\s+/g, ' ').trim(),
          };
        })()""")
        log(json.dumps(info, ensure_ascii=False, indent=2))

        ok = bool(info.get("hasTextBody")) and (info.get("paraCount") or 0) >= 2 and (info.get("chars") or 0) > 500
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
