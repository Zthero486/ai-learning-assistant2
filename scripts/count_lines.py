"""工作量度量脚本：按作者统计 git 提交量（行数 / 提交数 / 文件数 / 模块分布）。

用法（在项目根目录执行）：
    python scripts/count_lines.py                 # 打印 Markdown 表格
    python scripts/count_lines.py --write         # 同时写入 docs/工作量统计.md

设计说明：
- 数据源为 git 仓库历史（--numstat），客观、可复核，不依赖人工填报；
- 二进制/生成文件（dist、lock 文件等）默认排除，避免虚增工作量；
- 输出按作者聚合，并给出前后端/文档的模块分布，用于绩效分配说明。
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# 排除的路径前缀/文件名（生成物、依赖锁文件等，不计入工作量）
EXCLUDE_PATTERNS = (
    "frontend/dist/",
    "frontend/node_modules/",
    "frontend/package-lock.json",
    "data/",
)
# 模块归属规则（按路径前缀归类，用于展示分工分布）
MODULE_RULES = (
    ("backend/", "后端"),
    ("frontend/", "前端"),
    ("docs/", "文档"),
    ("scripts/", "脚本/工具"),
    (".github/", "CI/协作配置"),
)


def find_git() -> str:
    """定位 git 可执行文件（兼容未把 git 加入 PATH 的环境）。"""
    found = shutil.which("git")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Git\cmd\git.exe"),
        os.path.expanduser(r"~/.workbuddy/binaries/PortableGit/versions/*/cmd/git.exe"),
    ]
    for pattern in candidates:
        for path in glob.glob(pattern):
            if Path(path).exists():
                return path
    sys.exit("未找到 git，请先安装 Git 或把 git.exe 加入 PATH")


GIT_EXE = find_git()


def git(*args: str) -> str:
    result = subprocess.run(
        [GIT_EXE, *args], capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    if result.returncode != 0:
        sys.exit(f"git {' '.join(args)} 执行失败：{result.stderr.strip()}")
    return result.stdout


def classify(path: str) -> str:
    for prefix, name in MODULE_RULES:
        if path.startswith(prefix):
            return name
    return "根目录/其他"


def excluded(path: str) -> bool:
    return any(p in path for p in EXCLUDE_PATTERNS)


def collect() -> tuple:
    """解析 git log --numstat，返回 (按作者统计, 明细行数)。"""
    log = git("log", "--numstat", "--date=short", "--pretty=format:__C__\x1f%an\x1f%ae\x1f%ad")
    authors = defaultdict(
        lambda: {
            "commits": 0,
            "added": 0,
            "deleted": 0,
            "files": set(),
            "modules": defaultdict(int),
        }
    )
    current = None

    for raw in log.splitlines():
        if raw.startswith("__C__\x1f"):
            _, name, email, date = raw.split("\x1f")
            current = (name, email)
            authors[current]["commits"] += 1
            continue
        if not raw.strip() or current is None:
            continue
        parts = raw.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if excluded(path):
            continue
        rec = authors[current]
        rec["added"] += int(added) if added.isdigit() else 0
        rec["deleted"] += int(deleted) if deleted.isdigit() else 0
        rec["files"].add(path)
        rec["modules"][classify(path)] += int(added) if added.isdigit() else 0
    return authors


def render_markdown(authors: dict) -> str:
    if not authors:
        return "（暂无提交数据）\n"
    order = sorted(authors.items(), key=lambda kv: kv[1]["added"], reverse=True)
    total_added = sum(r["added"] for _, r in order) or 1

    lines = [
        "# 工作量统计（由 `scripts/count_lines.py` 自动生成）",
        "",
        "> 数据来源：git 提交历史（--numstat），排除依赖、构建产物与运行数据。",
        "",
        "## 1. 总体占比",
        "",
        "| 成员 | 提交数 | 新增行 | 删除行 | 涉及文件 | 代码占比 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for (name, email), rec in order:
        share = rec["added"] / total_added * 100
        lines.append(
            f"| {name} | {rec['commits']} | {rec['added']} | {rec['deleted']} | "
            f"{len(rec['files'])} | {share:.1f}% |"
        )
    lines += [
        "",
        "## 2. 模块分工分布（按新增行）",
        "",
        "| 成员 | " + " | ".join(name for _, name in MODULE_RULES) + " | 其他 |",
        "| --- |" + " ---: |" * (len(MODULE_RULES) + 1),
    ]
    for (name, _), rec in order:
        cells = [str(rec["modules"].get(mod, 0)) for _, mod in MODULE_RULES]
        cells.append(str(rec["modules"].get("根目录/其他", 0)))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="按作者统计 git 工作量")
    parser.add_argument("--write", action="store_true", help="写入 docs/工作量统计.md")
    args = parser.parse_args()

    authors = collect()
    md = render_markdown(authors)
    print(md)

    if args.write:
        out = Path(__file__).resolve().parent.parent / "docs" / "工作量统计.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"已写入：{out}")


if __name__ == "__main__":
    main()
