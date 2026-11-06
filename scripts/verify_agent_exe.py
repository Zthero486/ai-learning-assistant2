"""验证打包后的 exe：AI 对话接口在冻结环境里是否可用。

启动 exe → 等健康检查 → 登录 demo → 非流式对话一次（只读）→ 结束进程。
结果写 _tmp/verify_agent_exe.txt。
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "release" / "AILearningAssistant.exe"
LOG = ROOT / "_tmp" / "verify_agent_exe.txt"
out = open(LOG, "w", encoding="utf-8", buffering=1)


def w(*a):
    out.write(" ".join(str(x) for x in a) + "\n")
    out.flush()


PORT = 8000
BASE = f"http://127.0.0.1:{PORT}"

import urllib.error  # noqa: E402


def probe_ports():
    """launcher 从 8000 起顺延找空位，这里挨个探，返回真正监听的那个。"""
    global BASE
    for p in range(8000, 8011):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{p}/api/health", timeout=2) as r:
                if r.status == 200:
                    BASE = f"http://127.0.0.1:{p}"
                    return p
        except Exception:
            continue
    return None

def get(path, tok=None, timeout=10):
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {tok}"} if tok else {})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def post(path, body, tok=None, timeout=180):
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


env = dict(os.environ)
env["APP_PORT"] = str(PORT)  # launcher 目前不吃这个变量，仅示意；端口冲突会自动顺延
proc = subprocess.Popen([str(EXE)], cwd=str(EXE.parent), stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, env=env)
w("启动 exe，pid", proc.pid)
try:
    ready = False
    for _ in range(60):
        p = probe_ports()
        if p:
            w("监听端口:", p)
            ready = True
            break
        time.sleep(1)
    if not ready:
        w("FAIL exe 未在 60s 内就绪")
        sys.exit(1)

    tok = post("/api/auth/login", {"username": "demo", "password": "demo123"})["token"]
    me = get("/api/auth/me", tok)["user"]
    w("demo track:", me.get("track"))
    if not me.get("track"):
        w("选课:", post("/api/profile/track", {"track": "party"}, tok))

    tools = get("/api/ai/tools", tok)
    w("工具数:", len(tools["tools"]), "写入工具:", sum(1 for t in tools["tools"] if t["write"]))

    # 冻结环境里 fsrs 是否真的能 import：algorithm 返回 ladder 就说明打包漏了依赖
    due = get("/api/review/due", tok)
    near = due["upcoming"][0]["srs_interval_text"] if due.get("upcoming") else "-"
    w("复习队列: 算法", due["algorithm"], "到期", due["due_count"], "最近一条", near)

    wb = get("/api/wrong-book", tok)
    w("错题排期字段:", sorted(k for k in wb[0] if k.startswith("srs_")) if wb else "错题本为空")

    d = post("/api/ai/chat", {
        "messages": [{"role": "user", "content": "这门课第三章讲什么？用两句话概括，不要调用工具"}],
        "stream": False, "allow_write": False,
    }, tok)
    w("reply:", (d.get("reply") or "")[:220].replace("\n", " "))
    w("steps:", [s["tool"] for s in d.get("steps", [])])
    ok = bool((d.get("reply") or "").strip())
    w("结果:", "PASS" if ok else "FAIL")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    out.close()
print(LOG.read_text(encoding="utf-8"))
