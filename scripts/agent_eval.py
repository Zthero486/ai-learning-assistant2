# -*- coding: utf-8 -*-
"""Agent 端到端评测集：真模型 × 真库 × 自动判分。

这是「测试数据集」的在线部分：每个用例 = 一句真实的学生请求 + 判分器。
判分器检查工具调用序列和落库结果，不检查文风 —— 那不是功能测试的事。

用法（项目根目录）：
    python scripts/agent_eval.py                 # 跑全部用例（约 2-4 分钟）
    python scripts/agent_eval.py --case 2        # 只跑第 2 例（回归截图里的出题场景）
    python scripts/agent_eval.py --offline       # 只校验数据集本身，不花 token

报告写 _tmp/agent_eval_report.txt。
每个用例都在一次性临时库上运行，跑完即弃，不污染演示数据。
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

OUT = ROOT / "_tmp" / "agent_eval_report.txt"


# ==================== 判分器 ====================
def _steps_of(final):
    return [s["tool"] for s in final.get("steps", [])]


def _ok_steps(final, name):
    return [s for s in final.get("steps", []) if s["tool"] == name and s["ok"]]


def _count_table(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _has_reply(final):
    return len((final.get("reply") or "").strip()) >= 20


# ==================== 评测数据集 ====================
# 每例：id / 请求（学生口吻）/ allow_write / 判分器(final, ctx) -> (bool, 说明)
CASES = [
    {
        "id": 1,
        "title": "回归场景：一章出 6 组题（曾 8 连败）",
        "prompt": "带我把第一章的知识点学完，帮我生成 6 组题，覆盖第一节的每一个知识点",
        "allow_write": True,
        "check": lambda f, c: (
            len(_ok_steps(f, "create_questions")) >= 1
            and _count_table(c, "questions") >= 3,
            f"create_questions 成功 {len(_ok_steps(f, 'create_questions'))} 次，"
            f"库里 {_count_table(c, 'questions')} 题",
        ),
    },
    {
        "id": 2,
        "title": "史实问答（只读，应先检索再答）",
        "prompt": "遵义会议是什么时候开的？主要解决了什么问题？",
        "allow_write": True,
        "check": lambda f, c: (
            bool(_steps_of(f)) and _has_reply(f) and "1935" in (f.get("reply") or ""),
            f"工具 {_steps_of(f)}",
        ),
    },
    {
        "id": 3,
        "title": "整理资料入库",
        "prompt": "把井冈山革命根据地这一节的核心内容整理成一篇资料存进我的史料笔记",
        "allow_write": True,
        "check": lambda f, c: (
            len(_ok_steps(f, "create_material")) >= 1 and _count_table(c, "materials") >= 1,
            f"materials 表 {_count_table(c, 'materials')} 条",
        ),
    },
    {
        "id": 4,
        "title": "排复习任务",
        "prompt": "我下周要考第一章，帮我安排这几天每天的复习任务",
        "allow_write": True,
        "check": lambda f, c: (
            len(_ok_steps(f, "create_task")) >= 1 and _count_table(c, "tasks") >= 1,
            f"tasks 表 {_count_table(c, 'tasks')} 条",
        ),
    },
    {
        "id": 5,
        "title": "错题归因",
        "prompt": "帮我看看错题本里的题为什么老错，把错因标出来并给我改法",
        "allow_write": True,
        "check": lambda f, c: (
            "get_wrong_book" in _steps_of(f),
            f"工具 {_steps_of(f)}（库里没错题时允许只诊断不落标签）",
        ),
    },
    {
        "id": 6,
        "title": "跨课程写入必须被拒",
        "prompt": "帮我在新中国史的第一章建一条知识点：开国大典",
        "allow_write": True,
        "check": lambda f, c: (
            "create_knowledge_point" not in [s["tool"] for s in f.get("steps", []) if s["ok"]],
            f"工具 {_steps_of(f)}（create_knowledge_point 应失败或未调用）",
        ),
    },
    {
        "id": 7,
        "title": "纯聊天不乱写库",
        "prompt": "你好，你是谁？你能帮我做什么？",
        "allow_write": True,
        "check": lambda f, c: (
            all(not s["tool"].startswith("create_") for s in f.get("steps", [])) and _has_reply(f),
            f"工具 {_steps_of(f)}（允许只读工具，不允许写入）",
        ),
    },
    {
        "id": 8,
        "title": "只读模式下写入被拒",
        "prompt": "帮我建一条知识点：秋收起义",
        "allow_write": False,
        "check": lambda f, c: (
            not any(s["tool"].startswith("create_") and s["ok"] for s in f.get("steps", [])),
            f"工具 {_steps_of(f)}",
        ),
    },
    {
        "id": 9,
        "title": "时间轴补事件",
        "prompt": "帮我把「三湾改编」补进时间轴，1927年10月，江西永新",
        "allow_write": True,
        "check": lambda f, c: (
            len(_ok_steps(f, "create_event")) >= 1,
            # 内置时间轴可能已有同名事件，工具幂等返回也算成功
            f"工具 {_steps_of(f)}",
        ),
    },
    {
        "id": 10,
        "title": "模糊请求也要给结论",
        "prompt": "我下周要参加四史考试了，很慌，怎么办？",
        "allow_write": True,
        "check": lambda f, c: (
            _has_reply(f) and len(f.get("steps", [])) <= 6,
            f"工具 {_steps_of(f)}",
        ),
    },
]


# ==================== 运行器 ====================
def build_env():
    """一次性临时库：补丁 apppaths 指向临时目录 + 从 backend/.env 取真 key。"""
    tmp = Path(tempfile.mkdtemp(prefix="agent_eval_"))
    (tmp / "data").mkdir()
    env = dict(os.environ)
    env["AI_DISABLE_BUILTIN"] = "1"
    env["AI_ASR_URL"] = ""
    for k in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL", "AI_PROXY"):
        env.pop(k, None)
    # key 来自 backend/.env（评测机的开发配置）；路径环境全部指向临时目录
    env_file = ROOT / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL", "AI_PROXY") and v.strip():
                    env[k.strip()] = v.strip()
    return tmp, env


def prepare_db(tmp, env):
    """新库：灌 demo 用户 + 一篇资料，让检索/出题有米下锅。

    必须先打补丁再导入 main —— DB_PATH/UPLOAD_DIR 是 import 时算好的常量。
    """
    os.environ.update(env)
    from app import apppaths

    apppaths.app_base_dir = lambda: tmp          # 数据目录 → 临时目录
    apppaths.env_file = lambda: tmp / ".env"     # 不存在 → 不会误读开发库的 .env
    import app.main as main  # noqa: E402  首次导入即初始化临时库（init_db 自带 demo 账号）

    conn = main.db()
    conn.execute("UPDATE users SET track='party' WHERE id=1")
    conn.commit()
    conn.close()

    from fastapi.testclient import TestClient

    tc = TestClient(main.app)
    tok = tc.post("/api/auth/login", json={"username": "demo", "password": "demo123"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    tc.post("/api/profile/track", json={"track": "party"}, headers=h)
    tc.post(
        "/api/materials/upload",
        headers=h,
        files={"file": ("背景.txt", (
            "第一章 中国共产党的创建与投身大革命的洪流。"
            "1919年五四运动标志新民主主义革命开端。1921年7月中共一大在上海召开，"
            "宣告中国共产党成立。1922年中共二大提出反帝反封建的民主革命纲领。"
            "1923年京汉铁路工人大罢工。1924年1月国民党一大召开，第一次国共合作正式形成，"
            "1925年五卅运动掀起大革命高潮。1926年北伐战争开始。"
            "1927年蒋介石发动四一二反革命政变，大革命失败。"
        ).encode("utf-8"), "text/plain")},
    )
    return main, tc, h


def run_case(main, tc, h, case):
    from app import ai_agent

    uid = tc.get("/api/auth/me", headers=h).json()["user"]["id"]
    ctx = ai_agent.AgentContext(uid, "party", main.db, main.now)
    t0 = time.time()
    final = ai_agent.run(ctx, [{"role": "user", "content": case["prompt"]}],
                         allow_write=case["allow_write"])
    conn = main.db()
    try:
        ok, why = case["check"](final, conn)
    finally:
        conn.close()
    return {
        "id": case["id"], "title": case["title"], "ok": bool(ok), "why": why,
        "tools": _steps_of(final), "rounds": final.get("rounds"),
        "tool_calls": final.get("tool_calls"), "secs": round(time.time() - t0, 1),
        "reply_head": ((final.get("reply") or "")[:100]).replace("\n", " "),
        "error": final.get("error"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=int, help="只跑指定 id 的用例")
    ap.add_argument("--offline", action="store_true", help="只校验数据集，不调真模型")
    args = ap.parse_args()

    if args.offline:
        print(f"数据集共 {len(CASES)} 例：")
        for c in CASES:
            assert callable(c["check"]) and c["prompt"] and c["title"]
            print(f"  [{c['id']:>2}] {'写' if c['allow_write'] else '读'} {c['title']}")
        print("数据集校验通过")
        return

    tmp, env = build_env()
    if not env.get("AI_API_KEY"):
        print("缺少 AI_API_KEY：评测必须真模型（backend/.env 里要有 key）")
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit(2)
    lines = []
    try:
        main, tc, h = prepare_db(tmp, env)
        cases = [c for c in CASES if (args.case is None or c["id"] == args.case)]
        passed = 0
        for c in cases:
            try:
                r = run_case(main, tc, h, c)
            except Exception as e:  # 单例崩不拖垮整场
                r = {"id": c["id"], "title": c["title"], "ok": False,
                     "why": f"评测器异常：{type(e).__name__}: {e}"}
            passed += r["ok"]
            mark = "PASS" if r["ok"] else "FAIL"
            line = (f"[{mark}] #{r['id']} {r['title']}  ({r.get('secs','?')}s, "
                    f"轮次{r.get('rounds')}, 调用{r.get('tool_calls')})\n"
                    f"       工具: {r.get('tools')}\n       判据: {r['why']}")
            if r.get("error"):
                line += f"\n       error: {r['error']}"
            lines.append(line)
            print(line)
        summary = f"\n通过 {passed}/{len(cases)}；报告已写 {OUT}"
        lines.append(summary)
        print(summary)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(
            f"Agent 评测报告  {datetime.now():%Y-%m-%d %H:%M}\n" + "\n".join(lines) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
