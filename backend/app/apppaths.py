"""运行时路径解析：同时兼容"开发态"与"PyInstaller 打包后的便携态"。

设计目标（便携发布）：
- 打包后双击 exe 即运行，不依赖本机 Python/Node；
- 数据（数据库、上传资料、.env）放在 exe 同级目录，整个文件夹拷走即可换机使用；
- 前端构建产物作为只读资源随包分发，不写回磁盘。

v1 说明：路径解析集中在本模块，是打包需求引入的最小改动；
统一配置中心属于 v2 重构范围（见 docs/ 设计文档）。
"""

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包后的可执行文件中。"""
    return bool(getattr(sys, "frozen", False))


def app_base_dir() -> Path:
    """可写数据目录：开发态为项目根目录，打包态为 exe 所在目录（便携）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def bundle_dir() -> Path:
    """只读资源目录：打包态为解包临时目录，开发态为项目根目录。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_base_dir()))
    return Path(__file__).resolve().parent.parent.parent


def frontend_dist() -> Path | None:
    """定位前端构建产物 frontend/dist；找不到返回 None（开发态走 Vite 代理）。"""
    candidates = [
        os.environ.get("APP_FRONTEND_DIR", ""),
        str(bundle_dir() / "frontend_dist"),
        str(app_base_dir() / "frontend" / "dist"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if (path / "index.html").is_file():
            return path
    return None


def env_file() -> Path:
    """配置文件 .env 位置：优先 exe 同级（便携），其次 backend/.env（开发态）。"""
    if is_frozen():
        return app_base_dir() / ".env"
    return Path(__file__).resolve().parent.parent / ".env"
