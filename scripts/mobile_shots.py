"""手机视图截屏：用本机 Chrome 的 DevTools 协议模拟 390×844 手机，抓真实界面。

为什么不用 Playwright：本项目只在自己机器上跑，Edge/Chrome 现成有，
用一个 websocket 就能驱动，不必再下一个 100+ MB 的浏览器内核。

用法（项目根目录）：
    python scripts/mobile_shots.py                 # 自动起 exe、截图、收工
    python scripts/mobile_shots.py --port 8031     # 指定端口

产物：_tmp/mobile_shots/*.png
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "release" / "AILearningAssistant.exe"
OUT = ROOT / "_tmp" / "mobile_shots"
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
DEBUG_PORT = 9223
W, H, DSF = 390, 844, 2  # iPhone 14 尺寸


def log(*a):
    print(*a, flush=True)


def free_port(prefer: int) -> int:
    import socket

    for p in range(prefer, prefer + 20):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise SystemExit("没有空闲端口")


class CDP:
    """极简 DevTools 协议客户端：够发命令、等事件就行。"""

    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.mid = 0

    def send(self, method: str, **params):
        self.mid += 1
        mid = self.mid
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr: str):
        r = self.send(
            "Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True
        )
        return r.get("result", {}).get("value")

    def goto(self, url: str, wait: float = 1.6):
        self.send("Page.navigate", url=url)
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(0.25)
            try:
                if self.js("document.readyState") == "complete":
                    break
            except Exception:
                continue
        time.sleep(wait)  # 给 SPA 发接口、渲染留时间

    def shot(self, name: str):
        data = self.send("Page.captureScreenshot", format="png", captureBeyondViewport=False)
        path = OUT / f"{name}.png"
        path.write_bytes(base64.b64decode(data["data"]))
        log("  截图", path.name, f"{path.stat().st_size // 1024} KB")
        return path


def api(base: str, path: str, body=None, token=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8031)
    ap.add_argument("--exe", default=str(EXE))
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port(args.port)
    base = f"http://127.0.0.1:{port}"

    chrome = next((p for p in CHROME_CANDIDATES if os.path.isfile(p)), None)
    if not chrome:
        raise SystemExit("找不到 Chrome / Edge")

    env = dict(os.environ, APP_HOST="0.0.0.0", APP_PORT=str(port), PYTHONUNBUFFERED="1")
    srv_log = open(ROOT / "_tmp" / "shots_server.log", "w", encoding="utf-8", buffering=1)
    srv = subprocess.Popen([args.exe], cwd=str(Path(args.exe).parent),
                           stdout=srv_log, stderr=subprocess.STDOUT, env=env)
    prof = ROOT / "_tmp" / "chrome-prof-shots"
    br = None
    try:
        ready = False
        for _ in range(60):
            try:
                h = api(base, "/api/health")
                log("服务就绪:", h.get("status"), "AI:", h.get("ai_source"))
                ready = True
                break
            except Exception:
                time.sleep(1)
        if not ready:
            raise SystemExit("服务 60s 未就绪，看 _tmp/shots_server.log")

        tok = api(base, "/api/auth/login", {"username": "demo", "password": "demo123"})
        user = tok["user"]
        lan = api(base, "/api/lan", token=tok["token"])

        br = subprocess.Popen(
            [chrome, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
             f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check",
             "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/list", timeout=2) as r:
                    for t in json.loads(r.read()):
                        if t.get("type") == "page":
                            ws_url = t["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not ws_url:
            raise SystemExit("连不上 Chrome 调试端口")

        c = CDP(ws_url)
        c.send("Page.enable")
        c.send("Runtime.enable")
        c.send("Emulation.setDeviceMetricsOverride", width=W, height=H,
               deviceScaleFactor=DSF, mobile=True)
        c.send("Emulation.setTouchEmulationEnabled", enabled=True)

        log("登录页")
        c.goto(f"{base}/login")
        c.shot("01-登录")

        # 直接把令牌塞进 localStorage，省掉模拟点输入框（和真实登录后的状态一模一样）
        c.js(
            "localStorage.setItem('lp_token', %s);"
            "localStorage.setItem('lp_user', %s);"
            % (json.dumps(tok["token"]), json.dumps(json.dumps(user, ensure_ascii=False)))
        )

        log("首页")
        c.goto(f"{base}/")
        c.shot("02-首页")

        log("错题本")
        c.goto(f"{base}/wrong-book")
        c.shot("03-错题本")
        c.js(
            "[...document.querySelectorAll('.el-radio-button__inner')]"
            ".find(e => e.textContent.includes('今日复习'))?.click()"
        )
        time.sleep(1.2)
        c.shot("04-今日复习")

        log("教材目录")
        c.goto(f"{base}/syllabus")
        c.shot("05-教材目录")

        log("AI 对话")
        c.goto(f"{base}/ai", wait=2.0)
        c.shot("06-AI对话")

        # 手机顶栏 → 抽屉导航 → 手机访问弹窗（二维码）
        log("手机访问二维码")
        c.goto(f"{base}/")
        c.js("document.querySelector('.mobile-bar .burger')?.click()")
        time.sleep(0.8)
        c.js("document.querySelector('.phone-hint')?.click()")
        time.sleep(1.5)
        c.shot("07-手机访问二维码")

        print("\n局域网地址:", lan)
        print("产物目录:", OUT)
    finally:
        if br:
            br.terminate()
        srv.terminate()
        srv_log.close()


if __name__ == "__main__":
    sys.exit(main())
