# -*- coding: utf-8 -*-
"""深度调试：patch fetch 记录请求，点面板项后立即轮询 toast/菜单态/请求列表。"""
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
DEBUG_PORT = 9228
ROOT = Path(__file__).resolve().parent.parent


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
    chrome = next((p for p in ms.CHROME_CANDIDATES if os.path.isfile(p)), None)
    prof = ROOT / "_tmp" / "chrome-prof-mobile"
    br = subprocess.Popen([
        chrome, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={prof}", "--no-first-run", "--disable-gpu", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    c = None
    try:
        c = ms.CDP(find_ws(DEBUG_PORT))
        c.send("Page.enable")
        c.send("Emulation.setDeviceMetricsOverride", width=820, height=1180,
               deviceScaleFactor=1.5, mobile=True)
        c.goto(BASE + "/login")
        c.js("localStorage.setItem('lp_token', %s);localStorage.setItem('lp_user', %s);"
             % (json.dumps(tok["token"]), json.dumps(json.dumps(tok["user"], ensure_ascii=False))))
        c.goto(BASE + "/", wait=2.5)
        # patch fetch 记录所有请求
        c.js("""window.__reqs=[];window.__errs=[];
        const of=window.fetch;
        window.fetch=(...a)=>{window.__reqs.push(a[0]+' '+(a[1]&&a[1].method||'GET'));return of(...a).catch(e=>{window.__errs.push(String(e));throw e});};
        window.addEventListener('error',e=>window.__errs.push('ERR '+e.message));
        window.addEventListener('unhandledrejection',e=>window.__errs.push('REJ '+String(e.reason)));""")

        st = c.js("""(() => {
          const chip = document.querySelector('.track-chip');
          const r = chip.getBoundingClientRect();
          const style = getComputedStyle(chip);
          return { visible: !!(r.width&&r.height), x:r.x, y:r.y,
                   display: style.display, vis: style.visibility };
        })()""")
        print("chip:", json.dumps(st))

        c.js("document.querySelector('.track-chip').click()")
        time.sleep(0.4)
        n1 = c.js("document.querySelectorAll('.track-menu-item').length")
        print("菜单项数:", n1)

        c.js("""(() => {
          const el = [...document.querySelectorAll('.track-menu-item')]
            .find(e => e.textContent.includes('党史'));
          window.__menuOpenBefore = !!document.querySelector('.track-menu');
          el && el.click();
        })()""")
        for i in range(10):
            time.sleep(0.3)
            snap = c.js("""(() => ({
              toasts: [...document.querySelectorAll('.el-message')].map(m=>m.textContent.trim()),
              menuStillOpen: !!document.querySelector('.track-menu'),
              reqs: window.__reqs.filter(u=>u.includes('track')),
              errs: window.__errs.slice(0,5),
              track: JSON.parse(localStorage.getItem('lp_user')||'{}').track,
            }))()""")
            if snap["toasts"] or snap["reqs"] or snap["errs"] or i == 9:
                print(json.dumps(snap, ensure_ascii=False, indent=2))
                if snap["toasts"]:
                    break
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
