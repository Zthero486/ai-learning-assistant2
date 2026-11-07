# -*- coding: utf-8 -*-
"""AI 出题→自动开做 端到端探针：浮窗里说出题，验证自动跳自测页并直接开始作答。

前置：release/AILearningAssistant.exe 已打包（含最新前端 + AI prompt 规则 12）。
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
    log = open(ROOT / "_tmp" / "ai_practice_probe_srv.log", "w", encoding="utf-8", buffering=1)
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
        h = {"Authorization": "Bearer " + tok["token"]}
        n0 = len(api("/api/questions", token=tok["token"]))
        print(f"题库存量(前): {n0}")

        br = subprocess.Popen(
            [CHROME, "--headless=new", "--remote-debugging-port=9228",
             "--user-data-dir=" + str(ROOT / "_tmp" / "chrome-prof-aipractice"),
             "--no-first-run", "--disable-gpu", "--force-device-scale-factor=1.5",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9228/json/list", timeout=2) as r:
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
        c.send("Emulation.setDeviceMetricsOverride", width=1180, height=860,
               deviceScaleFactor=1.5, mobile=False)
        c.send("Page.navigate", url=BASE + "/login")
        time.sleep(3)
        c.js("localStorage.setItem('lp_token', %s); localStorage.setItem('lp_user', %s)"
             % (json.dumps(tok["token"]), json.dumps(json.dumps(tok["user"], ensure_ascii=False))))
        c.send("Page.navigate", url=BASE + "/dashboard")
        time.sleep(3)

        # 在浮动 AI 里说出题指令
        c.js("document.querySelector('.ai-fab').click()")
        time.sleep(2)
        c.js("""(() => {
            const ta = document.querySelector('.ai-float textarea');
            const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
            setter.call(ta, '围绕遵义会议给我出 3 道单选题，出完直接带我去做');
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        })()""")
        c.js("document.querySelector('.ai-float .foot-actions button.el-button--primary').click()")
        print("已发出题指令，等 AI 出题并自动跳转…")

        # 轮询：跳到 /practice 且自动进入做题会话（.q-stage 出现）
        st = None
        for _ in range(60):  # 最多 120 s（出题要真模型几轮）
            time.sleep(2)
            st = c.js("""(() => ({
                path: location.pathname,
                busy: !!document.querySelector('.ai-float .thinking'),
                session: !!document.querySelector('.q-stage'),
                question: (document.querySelector('.q-text') || {}).textContent || '',
                nOpts: document.querySelectorAll('.opt-btn').length,
                hasInput: !!document.querySelector('.q-stage textarea'),
            }))()""")
            if st["session"] and st["question"]:
                break
        print("跳转结果:", json.dumps(st, ensure_ascii=False))
        ok = bool(st and st["path"] == "/practice" and st["session"] and st["question"])
        c.shot("17-AI出题-自动开做")
        if not ok:
            print("FAIL 未自动进入做题会话")
            sys.exit(1)

        # 做第一题：选择题点第一项；主观题自评「答错了」制造一条错题数据
        if st["nOpts"] >= 3:
            c.js("document.querySelectorAll('.opt-btn')[0].click()")
            time.sleep(2.5)
        else:
            c.js("""(() => {
                const ta = document.querySelector('.q-stage textarea');
                const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                setter.call(ta, '不知道');
                ta.dispatchEvent(new Event('input', {bubbles: true}));
            })()""")
            time.sleep(0.5)
            c.js("[...document.querySelectorAll('button')].find(b => b.textContent.includes('对照参考答案')).click()")
            time.sleep(1)
            c.js("[...document.querySelectorAll('button')].find(b => b.textContent.includes('答错了')).click()")
            time.sleep(2)
        s = c.js("""(() => ({
            verdict: !!document.querySelector('.verdict'),
            sched: (document.querySelector('.v-sched') || {}).textContent || '',
        }))()""")
        print("判分反馈:", json.dumps(s, ensure_ascii=False))
        c.shot("18-AI出题-作答判分")

        # 数据落库验证：题库应有 3 道新题，practice_records 应有作答
        time.sleep(1)
        n1 = len(api("/api/questions", token=tok["token"]))
        summ = api("/api/practice/summary", token=tok["token"])
        print(f"题库存量(后): {n1}（+{n1 - n0}）  今日已练: {summ['today_total']} 正确: {summ['today_correct']}")
        ok = ok and (n1 - n0) >= 1 and summ["today_total"] >= 1
        print("PASS AI 出题→自动开做→数据落库 全链路" if ok else "FAIL 数据未落库")
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
