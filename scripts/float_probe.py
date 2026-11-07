# -*- coding: utf-8 -*-
"""浮动 AI 探针：在非 /ai 页面验证 FAB 与浮窗（点击、拖动、手机全屏）。"""
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
BASE = "http://127.0.0.1:8031"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 探针全部访问本机地址：禁用环境代理（系统代理开着时 urllib 会被劫持成 502）
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))


def api(path, body=None, token=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
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
    env = dict(os.environ, APP_HOST="0.0.0.0", APP_PORT="8031", PYTHONUNBUFFERED="1")
    log = open(ROOT / "_tmp" / "float_probe_srv.log", "w", encoding="utf-8", buffering=1)
    srv = subprocess.Popen([str(ROOT / "release" / "AILearningAssistant.exe")],
                           cwd=str(ROOT / "release"), stdout=log, stderr=subprocess.STDOUT, env=env)
    br = None
    try:
        for _ in range(60):
            try:
                api("/api/health")
                break
            except Exception:
                time.sleep(1)
        tok = api("/api/auth/login", {"username": "demo", "password": "demo123"})

        br = subprocess.Popen(
            [CHROME, "--headless=new", "--remote-debugging-port=9225",
             "--user-data-dir=" + str(ROOT / "_tmp" / "chrome-prof-float"),
             "--no-first-run", "--disable-gpu", "--force-device-scale-factor=1.5",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9225/json/list", timeout=2) as r:
                    for t in json.loads(r.read()):
                        if t.get("type") == "page":
                            ws_url = t["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        c = CDP(ws_url)
        c.send("Page.enable")
        c.send("Emulation.setDeviceMetricsOverride", width=1180, height=780,
               deviceScaleFactor=1.5, mobile=False)
        c.send("Page.navigate", url=BASE + "/login")
        time.sleep(3)
        c.js("localStorage.setItem('lp_token', %s); localStorage.setItem('lp_user', %s)"
             % (json.dumps(tok["token"]), json.dumps(json.dumps(tok["user"], ensure_ascii=False))))
        c.send("Page.navigate", url=BASE + "/wrong-book")
        time.sleep(3)

        checks = c.js("""(() => ({
            fab: !!document.querySelector('.ai-fab'),
            page: location.pathname,
        }))()""")
        print("FAB 存在:", checks)

        c.js("document.querySelector('.ai-fab').click()")
        time.sleep(2.5)
        panel = c.js("""(() => {
            const p = document.querySelector('.ai-float');
            const chat = document.querySelector('.ai-float .chat-wrap');
            return { panel: !!p, chatInside: !!chat,
                     rect: p ? p.getBoundingClientRect().toJSON() : null };
        })()""")
        print("浮窗:", json.dumps({k: v for k, v in panel.items() if k != 'rect'}, ensure_ascii=False))
        c.shot("10-浮窗AI-错题本页")

        # 拖到左上角
        r = panel["rect"]
        c.js(f"""(() => {{
            const head = document.querySelector('.float-head');
            const rect = head.getBoundingClientRect();
            const opts = {{bubbles: true, cancelable: true}};
            head.dispatchEvent(new PointerEvent('pointerdown', {{...opts, clientX: rect.x + 60, clientY: rect.y + 12, pointerId: 1}}));
            head.dispatchEvent(new PointerEvent('pointermove', {{...opts, clientX: 60, clientY: 30, pointerId: 1}}));
            head.dispatchEvent(new PointerEvent('pointerup', {{...opts, clientX: 60, clientY: 30, pointerId: 1}}));
            const p = document.querySelector('.ai-float').getBoundingClientRect();
            return {{x: p.x, y: p.y}};
        }})()""")
        time.sleep(0.5)
        moved = c.js("document.querySelector('.ai-float').getBoundingClientRect().x")
        print("拖动后 x:", moved)
        c.shot("11-浮窗AI-拖动后")

        # 手机视图：全屏层
        c.send("Emulation.setDeviceMetricsOverride", width=390, height=844,
               deviceScaleFactor=2, mobile=True)
        c.send("Emulation.setTouchEmulationEnabled", enabled=True)
        time.sleep(1)
        c.js("document.querySelector('.float-close')?.click()")
        time.sleep(0.6)
        fab2 = c.js("!!document.querySelector('.ai-fab')")
        print("手机端 FAB 回来:", fab2)
        c.js("document.querySelector('.ai-fab')?.click()")
        time.sleep(2)
        c.shot("12-浮窗AI-手机全屏")
        print("PASS 浮窗探针完成")
    finally:
        if br:
            br.terminate()
        srv.terminate()
        log.close()


if __name__ == "__main__":
    sys.exit(main())
