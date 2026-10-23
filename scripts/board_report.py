#!/usr/bin/env python3
"""开工前跑一次：告诉你「你是谁、该干什么、代码是不是最新的」。

为什么不是直接让人看 Markdown
------------------------------
看板是给人看的，但人打开看板之前要先知道三件事：
    1. 我的代码是不是最新的？
    2. 我名下的任务有哪些？
    3. 上次我看到现在，别人改了什么？

这三件事每次都要手动敲 git 命令问，问三次就会有一次不问。
这个脚本把它们压成一条命令的输出。

用法
----
    python scripts/board_report.py                # 列出所有未完成任务
    python scripts/board_report.py --me 黄吉航     # 只看自己名下
    python scripts/board_report.py --me 黄吉航 --pull  # 先拉代码再看

退出码：0 正常；1 有阻塞任务；2 代码不是最新（提醒先 pull）
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BOARD = REPO_ROOT / "docs" / "协作看板.md"

DONE_MARK = "✅"
BLOCK_MARK = "🚫"
DOING_MARK = "🔄"


def parse_todo(text: str) -> list[dict]:
    """抽出「## 待办」表里的所有任务行。"""
    tasks: list[dict] = []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section != "待办" or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or not re.fullmatch(r"[A-Z]+\d+", cells[0]):
            continue
        card = ""
        if len(cells) > 4:
            match = re.search(r"\]\(([^)]+)\)", cells[4])
            if match:
                card = match.group(1)
        tasks.append(
            {
                "id": cells[0],
                "title": cells[1],
                "owner": cells[2],
                "status": cells[3],
                "card": card,
                "deadline": cells[5] if len(cells) > 5 else "",
            }
        )
    return tasks


def git(*args: str) -> str:
    """跑只读的 git 命令，失败返回空串（不打断报告）。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        return out.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def main() -> int:
    argv = sys.argv[1:]
    me = ""
    if "--me" in argv:
        idx = argv.index("--me")
        if idx + 1 < len(argv):
            me = argv[idx + 1]

    if "--pull" in argv:
        print("正在拉取最新代码 ...")
        print(git("pull", "--ff-only") or "（pull 无输出，可能已是最新）")
        print()

    if not BOARD.is_file():
        print(f"找不到看板：{BOARD}")
        print("多半是代码没拉全，先在这个目录执行 git pull")
        return 2

    tasks = parse_todo(BOARD.read_text(encoding="utf-8"))

    print("=" * 68)
    is_stale = False
    if not git_available():
        print("⚠️  找不到 git 命令，跳过基线检查（把 Git 加到 PATH 后可启用）")
    else:
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        head = git("log", "-1", "--format=%h %s")
        behind = git("rev-list", "--count", f"HEAD..origin/{branch}") if branch else ""
        print(f"分支 {branch or '?'}    HEAD {head or '?'}")
        if behind.isdigit() and int(behind) > 0:
            print(f"⚠️  落后远端 {behind} 个提交，先执行：git pull")
            is_stale = True
        elif behind.isdigit():
            print("✅ 已是最新")
    print("=" * 68)

    if me:
        mine = [t for t in tasks if t["owner"] == me]
    else:
        mine = tasks

    open_tasks = [t for t in mine if DONE_MARK not in t["status"]]
    done_tasks = [t for t in mine if DONE_MARK in t["status"]]

    print(f"\n【待办】{len(open_tasks)} 项" + (f"（负责人：{me}）" if me else ""))
    if not open_tasks:
        print("  没有未完成任务。看板的「已完成」区是唯一的交付凭证，没有就去问。")
    for t in open_tasks:
        flag = ""
        if BLOCK_MARK in t["status"]:
            flag = "  ← 阻塞，别硬等"
        elif DOING_MARK in t["status"]:
            flag = "  ← 你正在做"
        print(f"  {t['id']:4s} {t['status']:8s} {t['title']}{flag}")
        if t["card"]:
            print(f"       任务卡：docs/{t['card']}")
        else:
            print("       任务卡：尚未编写 —— 需求还在设计，暂时不要动手")
        if t["deadline"]:
            print(f"       截止：{t['deadline']}")

    if done_tasks:
        print(f"\n【已完成】{len(done_tasks)} 项")
        for t in done_tasks:
            print(f"  {t['id']:4s} {t['title']}")

    print("\n" + "-" * 68)
    print("下一步：挑一个「⏳ 待开始」的任务，把它改成「🔄 进行中」并单独提交一次，")
    print("       然后按任务卡执行。做完改「✅ 已完成」并在交付说明里写清改了什么。")
    print("       你改完推送，GitHub 会自动关闭对应 Issue，不用手动点。")

    if any(BLOCK_MARK in t["status"] for t in open_tasks):
        return 1
    return 2 if is_stale else 0


if __name__ == "__main__":
    sys.exit(main())
