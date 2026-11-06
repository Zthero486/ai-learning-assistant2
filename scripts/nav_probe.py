# -*- coding: utf-8 -*-
"""联动跳转探针：真实发一句「切到史料笔记」，验证 AI navigate 工具带动前端路由切换。

前置：release/AILearningAssistant.exe 已打包（本探针直接跑它）。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from float_probe import CDP, ROOT, api  # noqa: E402

BASE = "http://127.0.0.1:8031"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main():
    env = dict(os.environ, APP_HOST="0.0.0.0", APP_PORT="8031", PYTHONUNBUFFERED="1")
    log = open(ROOT / "_tmp" / "nav_probe_srv.log", "w", encoding="utf-8", buffering=1)
    srv = subprocess.Popen([str(ROOT / "release" / "AILearningAssistant.exe")],
                           cwd=str(ROOT / "release"), stdout=log, stderr=subprocess.STDOUT, env=env)
    br = None
    ok = False
    try:
        for _ in range(60):
            try:
                api("/api/health")
                break
            except Exception:
                time.sleep(1)
        tok = api("/api/auth/login", {"username": "demo", "password": "demo123"})

        br = subprocess.Popen(
            [CHROME, "--headless=new", "--remote-debugging-port=9226",
             "--user-data-dir=" + str(ROOT / "_tmp" / "chrome-prof-nav"),
             "--no-first-run", "--disable-gpu", "--force-device-scale-factor=1.5",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9226/json/list", timeout=2) as r:
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
        # 故意从错题本出发：AI 说「切到史料笔记」后路径应变成 /materials
        c.send("Page.navigate", url=BASE + "/wrong-book")
        time.sleep(3)

        c.js("document.querySelector('.ai-fab').click()")
        time.sleep(2)
        c.js("""(() => {
            const ta = document.querySelector('.ai-float textarea');
            const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
            setter.call(ta, '切到史料笔记');
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        })()""")
        time.sleep(0.5)
        c.js("document.querySelector('.ai-float .foot-actions button.el-button--primary').click()")
        print("已发送：切到史料笔记（等 AI 回合结束…）")

        final = None
        for _ in range(40):  # 最多 40 s
            time.sleep(2)
            st = c.js("""(() => ({
                path: location.pathname,
                busy: !!document.querySelector('.ai-float .thinking'),
                steps: [...document.querySelectorAll('.ai-float .step-name')].map(e => e.textContent),
            }))()""")
            print("  轮询:", json.dumps(st, ensure_ascii=False))
            if st["path"] == "/materials" and not st["busy"]:
                final = st
                break
            if not st["busy"] and st["path"] != "/materials" and _ > 12:
                final = st
                break
        ok = final is not None and final["path"] == "/materials"
        print("最终路径:", final["path"] if final else "?", "步骤:", final["steps"] if final else "?")
        print("PASS 联动跳转生效" if ok else "FAIL 联动跳转未生效")
        c.shot("13-联动跳转-史料笔记")
    finally:
        try:
            if br:
                br.terminate()
        except Exception:
            pass
        try:
            srv.terminate()
        except Exception:
            pass
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
