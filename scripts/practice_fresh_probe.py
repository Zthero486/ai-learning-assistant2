# -*- coding: utf-8 -*-
"""回归：人已在自测页时让内嵌 AI 出题——应重拉题库直接开做，而不是弹「还没同步到题库」。

复现原 bug 的场景：先打开 /practice 等题库加载完，再在页内嵌 AI 里说出题。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_tmp" / "mobile_shots"
PORT = os.environ.get("PROBE_PORT", "8035")
BASE = f"http://127.0.0.1:{PORT}"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))


def api(path, body=None, token=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self.mid = 0

    def send(self, method, **params):
        self.mid += 1
        mid = self.mid
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def shot(self, name):
        import base64
        data = self.send("Page.captureScreenshot", format="png")
        p = OUT / f"{name}.png"
        p.write_bytes(base64.b64decode(data["data"]))
        print("  shot", p.name, p.stat().st_size // 1024, "KB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    srv = subprocess.Popen([str(ROOT / "release" / "AILearningAssistant.exe")],
                           cwd=str(ROOT / "release"),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env=dict(os.environ, APP_PORT=PORT))
    for _ in range(40):
        try:
            api("/api/health")
            break
        except Exception:
            time.sleep(1)
    login = api("/api/auth/login", {"username": "demo", "password": "demo123"})
    tok = login["token"]
    bank_before = api("/api/questions", token=tok)
    n_before = len(bank_before) if isinstance(bank_before, list) else len(bank_before.get("items", bank_before))
    print("题库存量(前):", n_before)

    br = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=9242",
                           "--user-data-dir=" + str(ROOT / "_tmp" / "chrome-prof-fresh"),
                           "--no-first-run", "--disable-gpu", "about:blank"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    for _ in range(40):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9242/json/list", timeout=2) as r:
                for t in json.loads(r.read()):
                    if t.get("type") == "page":
                        ws = t["webSocketDebuggerUrl"]
                        break
            if ws:
                break
        except Exception:
            pass
        time.sleep(0.5)
    c = CDP(ws)
    c.send("Page.enable")
    c.send("Page.navigate", url=BASE + "/login")
    time.sleep(3)
    c.js("localStorage.setItem('lp_token', %s); localStorage.setItem('lp_user', %s); localStorage.removeItem('lp_ai_chat_msgs')"
         % (json.dumps(tok), json.dumps(json.dumps(login["user"], ensure_ascii=False))))
    # 关键：先停在自测页（复现「人已在页内」）
    c.send("Page.navigate", url=BASE + "/practice")
    time.sleep(4)

    c.js("document.querySelector('.ai-inline .aii-head').click()")
    time.sleep(0.8)
    c.js("""(() => {
      const ta = document.querySelector('.ai-inline input');
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(ta, '出2道关于遵义会议的题');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    })()""")
    time.sleep(0.4)
    c.js("document.querySelector('.ai-inline button.el-button--primary').click()")

    verdict, session_q, bank_after = "", "", None
    st = {}
    for _ in range(50):
        time.sleep(2)
        st = c.js("""(() => ({
          pending: !!document.querySelector('.ai-inline .thinking'),
          warn: [...document.querySelectorAll('.el-message')]
                .some(e => e.textContent.includes('还没同步到题库')),
          session: !!document.querySelector('.session-card'),
          q: (document.querySelector('.session-card') || {}).textContent || '',
          steps: [...document.querySelectorAll('.ai-inline .aii-step')].map(e => e.textContent.trim()),
          path: location.pathname,
        }))()""")
        if st["warn"]:
            verdict = "warning"
            break
        if st["session"] and not st["pending"]:
            verdict = "session"
            session_q = st["q"][:120]
            break
    print("结果:", verdict, "| 最后状态:", json.dumps(st, ensure_ascii=False)[:300])
    c.shot("24-页内出题-直接开做")

    bank_after = api("/api/questions", token=tok)
    n_after = len(bank_after) if isinstance(bank_after, list) else len(bank_after.get("items", bank_after))
    print("题库存量(后):", n_after)

    br.terminate()
    srv.terminate()
    assert verdict == "session", f"期望直接开做，实际: {verdict}"
    assert n_after > n_before, "题库没有新增"
    print("PASS 页内出题：题库重拉 + 直接开做")


if __name__ == "__main__":
    main()
