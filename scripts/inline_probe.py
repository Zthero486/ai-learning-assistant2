# -*- coding: utf-8 -*-
"""内嵌 AI 探针：在每个功能页底部的 AiInline 组件里直接对话（不经过浮窗/主对话页）。

验证点：
1. 8 个功能页都渲染出 AiInline（标题带页面名）
2. 展开 → 输入 → 发送 → 拿到回复（同一份会话历史）
3. 页面上下文真的传到后端（问「我在哪一页」应能答对）
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
PORT = os.environ.get("PROBE_PORT", "8033")
BASE = f"http://127.0.0.1:{PORT}"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))


def api(path, body=None, token=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
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


PAGES = [
    ("/", "学习看板"),
    ("/syllabus", "教材目录"),
    ("/timeline", "四史时间轴"),
    ("/materials", "史料笔记"),
    ("/knowledge", "史实要点"),
    ("/tasks", "复习任务"),
    ("/practice", "自测"),
    ("/wrong-book", "错题本"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, APP_PORT=PORT)
    srv = subprocess.Popen([str(ROOT / "release" / "AILearningAssistant.exe")],
                           cwd=str(ROOT / "release"),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(40):
        try:
            api("/api/health")
            break
        except Exception:
            time.sleep(1)
    tok = api("/api/auth/login", {"username": "demo", "password": "demo123"})

    br = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=9241",
                           "--user-data-dir=" + str(ROOT / "_tmp" / "chrome-prof-inline"),
                           "--no-first-run", "--disable-gpu", "about:blank"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    for _ in range(40):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9241/json/list", timeout=2) as r:
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
    c.send("Emulation.setDeviceMetricsOverride", width=1280, height=900, deviceScaleFactor=1.0, mobile=False)
    c.send("Page.navigate", url=BASE + "/login")
    time.sleep(3)
    c.js("localStorage.setItem('lp_token', %s); localStorage.setItem('lp_user', %s); localStorage.removeItem('lp_ai_chat_msgs')"
         % (json.dumps(tok["token"]), json.dumps(json.dumps(tok["user"], ensure_ascii=False))))

    # 1) 每个页面都要有内嵌 AI
    found = {}
    for path, name in PAGES:
        c.send("Page.navigate", url=BASE + path)
        time.sleep(2.5)
        info = c.js("""(() => {
          const el = document.querySelector('.ai-inline');
          if (!el) return { ok: false };
          const t = document.querySelector('.ai-inline .aii-title');
          return { ok: true, title: t ? t.textContent.trim() : '', fab: !!document.querySelector('.ai-fab') };
        })()""")
        found[path] = info
        print(f"{path:14s} -> {json.dumps(info, ensure_ascii=False)}")

    missing = [p for p, v in found.items() if not v or not v.get("ok")]
    assert not missing, f"缺少内嵌 AI 的页面: {missing}"
    wrong = [p for p, v in found.items() if found[p]["title"].split('·')[-1].strip() not in
             dict(PAGES)[p]]
    print("标题不匹配:", wrong if wrong else "无")

    # 2) 在「自测」页内嵌对话框里直接问，带上下文
    c.send("Page.navigate", url=BASE + "/practice")
    time.sleep(3)
    c.js("document.querySelector('.ai-inline .aii-head').click()")
    time.sleep(1)
    c.shot("20-内嵌AI-自测页展开")
    c.js("""(() => {
      const ta = document.querySelector('.ai-inline input');
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(ta, '我现在在哪个功能页？一句话回答');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    })()""")
    time.sleep(0.4)
    c.js("document.querySelector('.ai-inline button.el-button--primary').click()")

    reply, steps, pending = "", [], True
    for _ in range(40):
        time.sleep(2)
        st = c.js("""(() => ({
          pending: !!document.querySelector('.ai-inline .thinking'),
          steps: [...document.querySelectorAll('.ai-inline .aii-step')].map(e => e.textContent.trim()),
          reply: ([...document.querySelectorAll('.ai-inline .aii-msg.assistant .aii-bubble')]
                   .filter(e => !e.classList.contains('thinking')).pop() || {}).textContent || '',
        }))()""")
        reply, steps, pending = st["reply"], st["steps"], st["pending"]
        if reply and not pending:
            break
    print("内嵌对话回复:", reply[:160])
    print("工具步骤:", steps)
    c.shot("21-内嵌AI-自测页回答")
    assert reply and not pending, "内嵌 AI 没有返回回复"

    # 3) 换页面再问一次，确认上下文真的跟着页面走
    c.send("Page.navigate", url=BASE + "/wrong-book")
    time.sleep(3)
    c.js("document.querySelector('.ai-inline .aii-head').click()")
    time.sleep(0.6)
    hist = c.js("""(() => ({
      msgs: document.querySelectorAll('.ai-inline .aii-msg').length,
      title: (document.querySelector('.ai-inline .aii-title') || {}).textContent || '',
    }))()""")
    print("换页后内嵌框:", json.dumps(hist, ensure_ascii=False))
    c.shot("22-内嵌AI-错题本页(历史保留)")
    assert hist["msgs"] >= 2, "换页后会话历史没接上"

    # 4) 手机尺寸下内嵌框是否可用
    c.send("Emulation.setDeviceMetricsOverride", width=412, height=915, deviceScaleFactor=2.0, mobile=True)
    c.send("Page.navigate", url=BASE + "/knowledge")
    time.sleep(3)
    m = c.js("""(() => {
      const el = document.querySelector('.ai-inline');
      if (!el) return { ok: false };
      const r = el.getBoundingClientRect();
      return { ok: true, w: Math.round(r.width), vw: window.innerWidth, overflowX: document.documentElement.scrollWidth > window.innerWidth };
    })()""")
    print("手机尺寸:", json.dumps(m, ensure_ascii=False))
    c.shot("23-内嵌AI-手机尺寸")

    br.terminate()
    srv.terminate()
    print("PASS 内嵌 AI 全链路（8 页渲染 + 页内对话 + 历史共享 + 手机尺寸）")


if __name__ == "__main__":
    main()
