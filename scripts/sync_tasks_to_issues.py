#!/usr/bin/env python3
"""把 docs/协作看板.md 的待办同步成 GitHub Issue，自动 @ 负责人。

为什么需要这个脚本
------------------
口头转述的问题不是"说不清楚"，而是"必须有人在中间传一次"。
只要中间有人，就会漏、会晚、会变形。

这个脚本把「看板里写了一行」直接变成「GitHub 给对方发一条通知」：

    你改看板 → git push → Actions 跑本脚本 → 建 Issue 并 @ 对方
                                            → 对方手机/邮箱收到通知
    对方改状态为 ✅ → push → Actions 跑本脚本 → Issue 自动关闭

幂等设计
--------
每个任务在 Issue 正文里埋一个 HTML 注释标记 `<!-- task-sync:T1 -->`。
重跑只更新、不重复建。GitHub 渲染时注释不可见，对读者无干扰。

用法
----
    # Actions 里（GITHUB_TOKEN 由 workflow 注入）
    python scripts/sync_tasks_to_issues.py

    # 本地试跑，只看不改
    python scripts/sync_tasks_to_issues.py --dry-run

    # 本地真跑，需要 Personal Access Token（scope: repo）
    set GITHUB_TOKEN=ghp_xxx
    set GITHUB_REPOSITORY=qianxingzhigui/ai-learning-assistant2
    python scripts/sync_tasks_to_issues.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BOARD = REPO_ROOT / "docs" / "协作看板.md"

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"

# 看板里的中文姓名 → GitHub 账号。新增成员在这里加一行即可。
MEMBER_GITHUB = {
    "黄吉航": "Zthero486",
    "韦俊鑫": "qianxingzhigui",
}

# 只给这些人建 Issue：自己的任务自己清楚，给自己发通知只是噪音。
NOTIFY_GITHUB = {"Zthero486"}

LABEL_NAME = "任务分派"
LABEL_COLOR = "1D76DB"
LABEL_DESC = "由 docs/协作看板.md 自动同步，请勿手工改标题"

MARKER_TPL = "<!-- task-sync:{tid} -->"
DONE_MARK = "✅"


# ==================== 看板解析 ====================


def parse_board(text: str) -> list[dict]:
    """从看板的「## 待办」小节里抽出任务行。

    只在「## 待办」标题下扫描，避免误把「已完成」表或成员对照表当成任务。
    """
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
        if len(cells) < 4:
            continue

        tid = cells[0]
        # 表头 `#`、分隔行 `---`、备注行都会被这个正则挡掉
        if not re.fullmatch(r"[A-Z]+\d+", tid):
            continue

        card = ""
        if len(cells) > 4:
            match = re.search(r"\]\(([^)]+)\)", cells[4])
            if match:
                card = match.group(1)

        tasks.append(
            {
                "id": tid,
                "title": cells[1],
                "owner": cells[2],
                "status": cells[3],
                "card": card,
                "deadline": cells[5] if len(cells) > 5 else "",
            }
        )
    return tasks


def read_card(card_rel: str) -> str:
    """读取任务卡全文。卡片链接是相对 docs/ 的路径。"""
    if not card_rel:
        return ""
    path = BOARD.parent / card_rel
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    # Issue 正文上限 65536 字符，留足余量给模板部分
    if len(text) > 40000:
        text = text[:40000] + "\n\n> （任务卡过长，此处截断，完整内容见仓库文件）"
    return text


# ==================== GitHub API ====================


def api(method: str, path: str, token: str, payload: dict | None = None):
    """极简 REST 封装。返回 (status, body)。"""
    url = API_ROOT + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", API_VERSION)
    req.add_header("User-Agent", "board-task-sync")
    if data is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        return 0, f"网络错误：{exc.reason}"


def ensure_label(repo: str, token: str) -> None:
    status, _ = api("GET", f"/repos/{repo}/labels/{urllib.parse.quote(LABEL_NAME)}", token)
    if status == 200:
        return
    api(
        "POST",
        f"/repos/{repo}/labels",
        token,
        {"name": LABEL_NAME, "color": LABEL_COLOR, "description": LABEL_DESC},
    )


def list_existing(repo: str, token: str) -> dict[str, dict]:
    """返回 {任务编号: issue}，按正文里的 marker 索引。"""
    found: dict[str, dict] = {}
    page = 1
    while page <= 10:
        status, data = api(
            "GET",
            f"/repos/{repo}/issues?state=all&per_page=100&page={page}&labels="
            + urllib.parse.quote(LABEL_NAME),
            token,
        )
        if status != 200 or not isinstance(data, list):
            break
        for issue in data:
            body = issue.get("body") or ""
            match = re.search(r"<!--\s*task-sync:([A-Z]+\d+)\s*-->", body)
            if match:
                found[match.group(1)] = issue
        if len(data) < 100:
            break
        page += 1
    return found


# ==================== 正文组装 ====================


def build_body(task: dict, owner_gh: str) -> str:
    parts = [
        MARKER_TPL.format(tid=task["id"]),
        f"@{owner_gh} 看板上给你派了一个任务：**{task['id']} {task['title']}**",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 编号 | {task['id']} |",
        f"| 负责人 | {task['owner']}（@{owner_gh}） |",
        f"| 状态 | {task['status']} |",
        f"| 截止 | {task['deadline'] or '未指定'} |",
        f"| 任务卡 | `docs/{task['card']}` |" if task["card"] else "| 任务卡 | 尚未编写 |",
        "",
    ]

    card_text = read_card(task["card"]) if task["card"] else ""
    if card_text:
        parts += [
            "<details>",
            "<summary>点开看任务卡全文（不用 clone 也能读）</summary>",
            "",
            card_text,
            "",
            "</details>",
            "",
        ]
    else:
        parts += [
            "> ⚠️ 这一行还没有任务卡，说明需求还在设计，**暂时不要动手**。",
            "> 动手前没有任务卡，就等于没有验收标准。",
            "",
        ]

    parts += [
        "---",
        "",
        "**怎么更新状态**：改 `docs/协作看板.md` 里这一行的状态列，然后提交推送。",
        "你把它改成 `✅ 已完成`，这个 Issue 会自动关闭，不需要手动点 Close。",
    ]
    return "\n".join(parts)


def build_title(task: dict) -> str:
    prefix = "✅ " if DONE_MARK in task["status"] else ""
    return f"{prefix}[{task['id']}] {task['title']}"


# ==================== 主流程 ====================


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or ""

    if not BOARD.is_file():
        print(f"[skip] 找不到看板：{BOARD}")
        return 0

    tasks = parse_board(BOARD.read_text(encoding="utf-8"))
    targets = [t for t in tasks if MEMBER_GITHUB.get(t["owner"]) in NOTIFY_GITHUB]

    print(f"看板解析到 {len(tasks)} 行任务，其中需要通知 {len(targets)} 行")
    for t in targets:
        print(f"  {t['id']:4s} {t['status']:8s} {t['title']}")

    if dry_run:
        print("\n[dry-run] 不调用 API，正文预览如下：\n")
        if targets:
            sample = targets[0]
            print(build_body(sample, MEMBER_GITHUB[sample["owner"]]))
        return 0

    if not token or not repo:
        print("[skip] 缺少 GITHUB_TOKEN 或 GITHUB_REPOSITORY，跳过同步")
        return 0

    ensure_label(repo, token)
    existing = list_existing(repo, token)
    print(f"仓库里已有 {len(existing)} 个自动同步的 Issue")

    created = updated = closed = unchanged = failed = 0

    for task in targets:
        owner_gh = MEMBER_GITHUB[task["owner"]]
        issue = existing.get(task["id"])
        is_done = DONE_MARK in task["status"]
        body = build_body(task, owner_gh)
        title = build_title(task)

        try:
            if is_done:
                if issue and issue["state"] == "open":
                    status, _ = api(
                        "PATCH",
                        f"/repos/{repo}/issues/{issue['number']}",
                        token,
                        {"state": "closed", "title": title, "body": body},
                    )
                    print(f"  [{task['id']}] 关闭 Issue #{issue['number']} -> {status}")
                    closed += 1
                else:
                    print(f"  [{task['id']}] 已完成，无需处理")
                    unchanged += 1
                continue

            if issue is None:
                payload = {
                    "title": title,
                    "body": body,
                    "labels": [LABEL_NAME],
                    "assignees": [owner_gh],
                }
                status, data = api("POST", f"/repos/{repo}/issues", token, payload)
                if status == 422:
                    # 公开仓库里对方没有写权限时 assign 会失败，退化为只 @ 不 assign。
                    # @mention 同样会触发通知，不影响接力。
                    payload.pop("assignees")
                    status, data = api("POST", f"/repos/{repo}/issues", token, payload)
                if status in (200, 201):
                    print(f"  [{task['id']}] 新建 Issue #{data['number']} -> {data['html_url']}")
                    created += 1
                else:
                    print(f"  [{task['id']}] 新建失败 {status}: {str(data)[:200]}")
                    failed += 1
                continue

            if issue["title"] == title and (issue.get("body") or "") == body:
                print(f"  [{task['id']}] 无变化，跳过")
                unchanged += 1
                continue

            payload = {"title": title, "body": body}
            if issue["state"] == "closed":
                payload["state"] = "open"
            status, _ = api("PATCH", f"/repos/{repo}/issues/{issue['number']}", token, payload)
            print(f"  [{task['id']}] 更新 Issue #{issue['number']} -> {status}")
            updated += 1

        except Exception as exc:  # 单个任务失败不应中断其余任务
            print(f"  [{task['id']}] 异常：{type(exc).__name__}: {exc}")
            failed += 1

    print(
        f"\n完成：新建 {created} / 更新 {updated} / 关闭 {closed} / 无变化 {unchanged} / 失败 {failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
