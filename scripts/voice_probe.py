# -*- coding: utf-8 -*-
"""语音按钮探针：无麦克风环境下验证前端的两级降级与报错文案。"""
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
    log = open(ROOT / "_tmp" / "voice_probe_srv.log", "w", encoding="utf-8", buffering=1)
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
            [CHROME, "--headless=new", "--remote-debugging-port=9224",
             "--user-data-dir=" + str(ROOT / "_tmp" / "chrome-prof-voice"),
             "--no-first-run", "--disable-gpu", "--use-fake-ui-for-media-stream",
             "--use-fake-device-for-media-stream", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9224/json/list", timeout=2) as r:
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
        c.send("Emulation.setDeviceMetricsOverride", width=900, height=760,
               deviceScaleFactor=1.5, mobile=False)
        c.send("Page.navigate", url=BASE + "/login")
        time.sleep(3)
        c.js("localStorage.setItem('lp_token', %s); localStorage.setItem('lp_user', %s)"
             % (json.dumps(tok["token"]), json.dumps(json.dumps(tok["user"], ensure_ascii=False))))
        c.send("Page.navigate", url=BASE + "/ai")
        time.sleep(3.5)

        checks = c.js("""(() => ({
            speechApi: !!(window.SpeechRecognition || window.webkitSpeechRecognition),
            mediaDevices: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
            micBtn: !!document.querySelector('.mic-btn'),
            secure: window.isSecureContext,
        }))()""")
        print("环境探测:", json.dumps(checks, ensure_ascii=False))

        c.js("document.querySelector('.mic-btn').click()")
        time.sleep(3)
        tip = c.js("document.querySelector('.voice-tip')?.textContent || ''")
        print("点击麦克风后提示:", (tip or "(无)").strip())
        c.shot("08-语音输入-桌面")

        # 手机视图再来一张
        c.send("Emulation.setDeviceMetricsOverride", width=390, height=844,
               deviceScaleFactor=2, mobile=True)
        c.send("Emulation.setTouchEmulationEnabled", enabled=True)
        time.sleep(0.8)
        c.shot("09-语音输入-手机")
        print("PASS 探针完成")
    finally:
        if br:
            br.terminate()
        srv.terminate()
        log.close()


if __name__ == "__main__":
    sys.exit(main())
