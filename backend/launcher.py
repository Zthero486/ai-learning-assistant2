"""便携版启动器（PyInstaller 打包入口）。

双击 exe 后的行为：
1. 端口自检：8000 被占用则自动顺延到 8001~8010，避免与开发环境冲突；
2. 启动本地服务（后端 API + 内嵌前端页面，同一端口）；
3. 自动打开默认浏览器访问界面；
4. 关闭此窗口即退出软件（数据已实时写入 exe 同级 data/ 目录）。

开发态也可直接运行本文件调试：python -m backend.launcher（需先有 frontend/dist）
"""

import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn


def pick_port(preferred: int = 8000, span: int = 10) -> int:
    """从 preferred 起找一个可用端口。

    注意：Windows 上不能设置 SO_REUSEADDR——它会让已被占用的端口被"抢绑"成功，
    导致端口自检误判、随后 uvicorn 绑定失败直接退出。这里使用默认绑定语义。
    另加一次 connect 探测，兼容 SO_REUSEADDR 已被其他程序设置的场景。
    """
    for port in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                continue  # 已有服务在监听，换下一个端口
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"端口 {preferred}~{preferred + span - 1} 均被占用，请关闭占用程序后重试。")


def wait_ready(url: str, timeout: float = 20.0) -> bool:
    """轮询健康检查，确认服务真正可用后再打开浏览器。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.3)
    return False


def main() -> None:
    port = pick_port(8000)
    base_url = f"http://127.0.0.1:{port}"

    print("=" * 56)
    print("  AI 智能学习助手  v1.0")
    print("=" * 56)
    print(f"  服务地址：{base_url}")
    print(f"  接口文档：{base_url}/docs")
    print("  数据目录：程序所在目录下的 data/ 文件夹")
    print("  提示：关闭本窗口即退出软件")
    print("=" * 56)

    # 延迟打开浏览器：等健康检查通过再打开，避免出现白页
    threading.Thread(
        target=lambda: webbrowser.open(base_url) if wait_ready(base_url) else None,
        daemon=True,
    ).start()

    from app.main import app  # 延迟导入，确保打包后资源路径已就绪

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
