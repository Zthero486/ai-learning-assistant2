"""项目源码打包脚本：生成便于传给协作者的源码包（含 git 历史）。

与 build_portable.py 的区别：
- build_portable.py → 产出**给最终用户运行的软件**（exe）
- 本脚本           → 产出**给开发者继续开发的项目**（源码 + git 历史 + 文档）

用法（项目根目录）：
    python scripts/pack_project.py              # 生成源码包
    python scripts/pack_project.py --with-git   # 额外打包 .git 目录（保留提交历史，推荐）

排除内容：依赖、构建产物、运行数据、密钥、便携版发布目录（均可重建或含敏感信息）。
"""

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_NAME = "AI智能学习助手-项目源码包.zip"

# 目录名精确匹配排除（任意层级）
EXCLUDE_DIRS = {
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "release",  # 便携版发布目录（用 build_portable.py 重新生成）
    "build",  # PyInstaller 中间产物
    "dist",  # 前端构建产物
    "frontend_dist",  # 打包时内嵌用的前端副本
    "uploads",  # 用户上传的原始文档
}
# 文件名/后缀排除
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".spec", ".log", ".db", ".sqlite3"}
EXCLUDE_NAMES = {".env", "package-lock.json"}
EXCLUDE_GLOBS = ("AI智能学习助手-*.zip",)


def should_skip(path: Path, with_git: bool) -> bool:
    rel_parts = path.relative_to(ROOT).parts
    if not with_git and rel_parts and rel_parts[0] == ".git":
        return True
    if any(part in EXCLUDE_DIRS for part in rel_parts):
        return True
    if path.name in EXCLUDE_NAMES or path.suffix in EXCLUDE_SUFFIXES:
        return True
    return any(path.match(pattern) for pattern in EXCLUDE_GLOBS)


def main() -> None:
    parser = argparse.ArgumentParser(description="打包项目源码")
    parser.add_argument("--with-git", action="store_true", help="包含 .git 目录以保留提交历史")
    args = parser.parse_args()

    archive = ROOT / ARCHIVE_NAME
    inner = ROOT.name
    count = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(ROOT.rglob("*")):
            if path == archive or should_skip(path, args.with_git):
                continue
            rel = path.relative_to(ROOT).as_posix()
            zf.write(path, f"{inner}/{rel}")
            if path.is_file():
                count += 1

    size_mb = archive.stat().st_size / 1024 / 1024
    print(f"源码包已生成：{archive.name}")
    print(f"  大小 {size_mb:.1f} MB，包含 {count} 个文件，含 git 历史：{'是' if args.with_git else '否'}")
    print("  接收方解压后：先读 docs/交接说明.md，再按其中「环境搭建」一节启动开发环境")


if __name__ == "__main__":
    main()
