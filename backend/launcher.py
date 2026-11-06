"""便携版启动器（PyInstaller 打包入口）。

双击 exe 后的行为：
1. 端口自检：8000 被占用则自动顺延到 8001~8010，避免与开发环境冲突；
2. 启动本地服务（后端 API + 内嵌前端页面，同一端口）；
3. 自动打开默认浏览器访问界面；
4. 关闭此窗口即退出软件（数据已实时写入 exe 同级 data/ 目录）。

开发态也可直接运行本文件调试：python -m backend.launcher（需先有 frontend/dist）
"""

import os
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn


def app_base_dir() -> Path:
    """可写数据目录：打包态为 exe 所在目录，开发态为项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def seed_database() -> None:
    """首次启动时，把随包附带的演示库 data/app.db.seed 复制成 data/app.db。

    只复制、绝不覆盖：之后升级版本时，哪怕整个 zip 解压覆盖旧目录，
    只要 data/app.db 已存在就不会被动到 —— 学生自己的练习/错题不会丢。
    """
    data_dir = app_base_dir() / "data"
    db = data_dir / "app.db"
    seed = data_dir / "app.db.seed"
    if db.exists() or not seed.is_file():
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed, db)


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


def lan_addresses(port: int) -> list:
    """本机所有局域网 IPv4 -> http://ip:port，供手机同 WiFi 扫码访问。"""
    urls = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        infos = []
    seen = set()
    for info in infos:
        ip = info[4][0]
        if ip in seen or ip.startswith("127.") or ip.startswith("169.254."):
            continue
        seen.add(ip)
        urls.append(f"http://{ip}:{port}")
    return urls


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
    # APP_HOST 默认只听本机（127.0.0.1，安全）；手机/平板要用时：
    #   - 便携版：给 exe 加参数 `AILearningAssistant.exe --lan`，或设环境变量 APP_HOST=0.0.0.0
    #   - 公网部署（Docker/云服务器）：必须 0.0.0.0，由反代/容器网络收口
    host = os.environ.get("APP_HOST", "").strip() or ("0.0.0.0" if "--lan" in sys.argv else "127.0.0.1")
    try:
        preferred = int(os.environ.get("APP_PORT", "8000"))
    except ValueError:
        preferred = 8000

    seed_database()
    port = pick_port(preferred)
    base_url = f"http://127.0.0.1:{port}"

    print("=" * 56)
    print("  「四史」学习助手  v1.0")
    print("  党史 / 新中国史 / 改革开放史 / 社会主义发展史")
    print("=" * 56)
    print(f"  本机访问：{base_url}")
    print(f"  接口文档：{base_url}/docs")
    if host == "0.0.0.0":
        addrs = lan_addresses(port)
        print("  手机/平板（同一 WiFi 下用浏览器打开）：")
        for u in addrs[:4]:
            print(f"    {u}")
        print("  提示：首次使用 Windows 防火墙可能弹窗，勾选「专用网络」允许。")
        print("  安全提醒：局域网内任何人都能打开此页面，公共 WiFi 下慎用 --lan。")
    print("  数据目录：程序所在目录下的 data/ 文件夹")
    print("  提示：关闭本窗口即退出软件")
    print("=" * 56)

    # 延迟打开浏览器：等健康检查通过再打开，避免出现白页
    if host != "0.0.0.0":
        threading.Thread(
            target=lambda: webbrowser.open(base_url) if wait_ready(base_url) else None,
            daemon=True,
        ).start()
    else:
        # 监听公网/局域网时不在服务器上弹浏览器（可能在无桌面的机器上）
        threading.Thread(
            target=lambda: webbrowser.open(base_url)
            if wait_ready(base_url) and os.environ.get("APP_OPEN_BROWSER") == "1"
            else None,
            daemon=True,
        ).start()

    from app.main import app  # 延迟导入，确保打包后资源路径已就绪

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
