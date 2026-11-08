# -*- coding: utf-8 -*-
"""移动端史料页探针：复用 mobile_shots 的 CDP 客户端，检查上传控件在手机视口下的渲染。

验证点：
  1. input[type=file] 存在，accept 里含 .pdf 与 application/pdf
  2. 「导入到」课程下拉存在（新版加了 el-select）
  3. 按钮可点、页面无白屏
  4. 截图留证

用法（连已运行的 8000 服务）：
    python scripts/materials_mobile_probe.py
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
DEBUG_PORT = 9224
W, H, DSF = 820, 1180, 1.5  # 联想小新平板横屏
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
            targets = json.loads(raw)
            for t in targets:
                if t.get("type") == "page":
                    return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit("Chrome 调试端口没起来")


def main():
    tok = api_direct("/api/auth/login", {"username": "demo", "password": "demo123"})
    user = tok.get("user") or {"username": "demo", "track": "reform"}
    log("登录 ok, track =", user.get("track"))

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
        ws = find_ws(DEBUG_PORT)
        c = ms.CDP(ws)
        c.send("Page.enable")
        c.send("Runtime.enable")
        c.send("Emulation.setDeviceMetricsOverride", width=W, height=H,
               deviceScaleFactor=DSF, mobile=True)
        c.send("Emulation.setTouchEmulationEnabled", enabled=True)

        # 先打开一次以建立 origin，再写 localStorage
        c.goto(BASE + "/login")
        c.js("localStorage.setItem('lp_token', %s);localStorage.setItem('lp_user', %s);"
             % (json.dumps(tok["token"]), json.dumps(json.dumps(user, ensure_ascii=False))))

        c.goto(BASE + "/materials", wait=2.5)
        c.shot("materials-tablet")

        info = c.js("""(() => {
          const inp = document.querySelector('.el-upload input[type=file]');
          const btns = [...document.querySelectorAll('button')].map(b => b.textContent.trim());
          const sel = document.querySelector('.el-select');
          return {
            hasInput: !!inp,
            accept: inp ? inp.getAttribute('accept') : null,
            hasSelect: !!sel,
            hasImportBtn: btns.some(t => t.includes('导入史料')),
            bodyLen: document.body.innerText.length,
            title: document.title
          };
        })()""")
        log("DOM 检查:", json.dumps(info, ensure_ascii=False, indent=2))

        ok = True
        if not info.get("hasInput"):
            log("[FAIL] 没找到文件输入框"); ok = False
        acc = info.get("accept") or ""
        if ".pdf" not in acc or "application/pdf" not in acc:
            log("[FAIL] accept 缺少 pdf 相关类型:", acc); ok = False
        if not info.get("hasSelect"):
            log("[FAIL] 没有课程下拉"); ok = False
        if not info.get("hasImportBtn"):
            log("[FAIL] 没有导入按钮"); ok = False
        if (info.get("bodyLen") or 0) < 50:
            log("[FAIL] 页面疑似白屏"); ok = False

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
