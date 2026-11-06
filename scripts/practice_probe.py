# -*- coding: utf-8 -*-
"""自测页探针：组卷 → 一次一题（选项/自评）→ 结算，全流程截图验证。

前置：release/AILearningAssistant.exe 已打包。
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
    log = open(ROOT / "_tmp" / "practice_probe_srv.log", "w", encoding="utf-8", buffering=1)
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
        nq = len(api("/api/questions", token=tok["token"]))
        print(f"题库存量: {nq}")

        br = subprocess.Popen(
            [CHROME, "--headless=new", "--remote-debugging-port=9227",
             "--user-data-dir=" + str(ROOT / "_tmp" / "chrome-prof-practice"),
             "--no-first-run", "--disable-gpu", "--force-device-scale-factor=1.5",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9227/json/list", timeout=2) as r:
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
        c.send("Page.navigate", url=BASE + "/practice")
        time.sleep(3)

        s1 = c.js("""(() => ({
            setup: !!document.querySelector('.today-box'),
            stats: [...document.querySelectorAll('.stat b')].map(e => e.textContent),
            startBtn: [...document.querySelectorAll('button')].some(b => b.textContent.includes('开始这一轮')),
        }))()""")
        print("组卷卡:", json.dumps(s1, ensure_ascii=False))
        c.shot("14-自测-组卷卡")

        c.js("[...document.querySelectorAll('button')].find(b => b.textContent.includes('开始这一轮')).click()")
        time.sleep(1.5)

        steps = []
        for i in range(45):  # 每题约 3 次迭代（作答→自评→下一题），默认 10 题一轮要 30+
            st = c.js("""(() => {
                const opts = [...document.querySelectorAll('.opt-btn')];
                const ta = document.querySelector('.q-stage textarea');
                return {
                    result: !!document.querySelector('.result-hero'),
                    question: (document.querySelector('.q-text') || {}).textContent || '',
                    nOpts: opts.length,
                    hasInput: !!ta,
                    judged: !!document.querySelector('.verdict'),
                    pending: !!document.querySelector('.self-judge'),
                    nextBtn: [...document.querySelectorAll('.next-row button')].some(b => b.textContent.includes('下一题') || b.textContent.includes('成绩')),
                };
            })()""")
            if st["result"]:
                break
            steps.append(st)
            print(f"  [{i}]", json.dumps(st, ensure_ascii=False)[:180])
            if not st["judged"] and not st["pending"]:
                if st["nOpts"] >= 3:
                    c.js("document.querySelectorAll('.opt-btn')[1].click()")  # 故意选非答案项也行
                elif st["hasInput"]:
                    c.js("""(() => {
                        const ta = document.querySelector('.q-stage textarea');
                        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                        setter.call(ta, '1921年');
                        ta.dispatchEvent(new Event('input', {bubbles: true}));
                    })()""")
                    c.js("[...document.querySelectorAll('button')].find(b => b.textContent.includes('对照参考答案')).click()")
                time.sleep(1.2)
                continue
            if st["pending"]:
                c.js("[...document.querySelectorAll('button')].find(b => b.textContent.includes('答对了')).click()")
                time.sleep(1.2)
                continue
            if st["judged"] and st["nextBtn"]:
                if i == 1:
                    c.shot("15-自测-判分反馈")
                c.js("[...document.querySelectorAll('.next-row button')].find(b => b.textContent.includes('下一题') || b.textContent.includes('成绩')).click()")
                time.sleep(1.2)
        time.sleep(1)
        s3 = c.js("""(() => ({
            result: !!document.querySelector('.result-hero'),
            rate: (document.querySelector('.ring-num') || {}).textContent || '',
            wrongs: document.querySelectorAll('.wrong-item').length,
        }))()""")
        print("结算页:", json.dumps(s3, ensure_ascii=False))
        c.shot("16-自测-结算页")

        ok = s1["setup"] and s1["startBtn"] and len(steps) >= 2 and s3["result"] and s3["rate"]
        print("PASS 自测全流程" if ok else "FAIL 自测全流程")
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
