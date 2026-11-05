"""便携绿色版打包脚本：把前端构建产物 + 后端 + Python 运行时打成单个 exe。

产物（release/ 目录）：
    AILearningAssistant.exe   双击即用，自动打开界面
    .env.example              可选配置模板（改名为 .env 填 AI key）
    使用说明.txt              给最终用户看的说明

用法（项目根目录）：
    python scripts/build_portable.py            # 完整构建
    python scripts/build_portable.py --skip-frontend   # 跳过前端构建（仅后端改动时）

前提：已安装 PyInstaller（脚本会提示 pip install pyinstaller）。
"""

import argparse
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
FRONTEND_DIST = FRONTEND / "dist"
BUNDLED_DIST = BACKEND / "frontend_dist"  # 随包分发的前端产物
RELEASE = ROOT / "release"
BUILD = ROOT / "build"
EXE_NAME = "AILearningAssistant"
VERSION = "1.0"

USAGE_TEXT = """历史学习助手 v1.0 —— 使用说明
====================================================

【怎么启动】
双击 AILearningAssistant.exe。程序会自动启动本地服务并打开浏览器界面。
首次启动约需 3~10 秒（需解压运行时），请耐心等待，不要重复双击。

【怎么退出】
关闭弹出的黑色命令行窗口即可（浏览器标签页可以直接关掉，
不影响数据，下次打开还是原来的进度）。

【数据存在哪】
本程序目录下的 data 文件夹：
    data/app.db     学习数据（资料、知识点、任务、练习、错题、统计）
    data/uploads/   导入的原始文档
整个文件夹可以整体拷贝到别的电脑，数据一起带走（便携绿色版，免安装）。

【AI 功能】
AI 让软件能真·大模型地工作：史料总结、史料答疑、根据错题个性化出题、薄弱点分析。
没有 .env 时也能用，只是会降级为本地规则引擎（资料检索式答疑 + 抽取式总结 + 统计分析）。

想开启大模型（两种方式，任选）：

方式一（推荐，免改文件）：打开左侧「AI 助手」→「配置 API Key」→
  平台预设选「阶跃星辰 StepFun」或「智谱 GLM」（两者都国内直连，不用代理）→
  粘贴 Key → 保存并生效 → 点「检测 AI 连接」看到绿色"连接成功"即可。

方式二：把 .env.example 复制为 .env（exe 同级），填写四行后重启程序。
  国内可用：AI_BASE_URL=https://api.stepfun.com/v1  AI_MODEL=step-3.5-flash

注意：阶跃要用 /v1 这条地址；/step_plan/v1 需要有效的 Step Plan 订阅，否则报 400。
只有用境外接口（如 Google Gemini）才需要代理，在「配置 API Key → 代理地址」里填
http://127.0.0.1:7897（换成你自己的端口）；提示"网络不通"多半就是代理没开。

【浏览器没自动打开怎么办】
手动打开浏览器，访问 http://127.0.0.1:8000
（若提示端口占用，程序会自动改用 8001，请查看黑窗口里显示的地址）

【常见问题】
- 杀毒软件误报：本程序由 Python 打包生成，未签名，可能被拦截；
  选择"允许运行/添加信任"即可。
- 想清空数据重新开始：关闭程序，删除 data 文件夹，重新启动程序会自动重建。
"""


def run(cmd, cwd=None, desc=""):
    print(f"[step] {desc or ' '.join(map(str, cmd))}")
    result = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str))
    if result.returncode != 0:
        sys.exit(f"失败：{desc}（退出码 {result.returncode}）")


def find_npm() -> str:
    found = shutil.which("npm")
    if found:
        return found
    import glob
    import os

    patterns = [
        r"C:\Program Files\nodejs\npm.cmd",
        os.path.expanduser(r"~/.workbuddy/binaries/node/versions/*/npm.cmd"),
    ]
    for pattern in patterns:
        for path in glob.glob(pattern):
            return path
    sys.exit("未找到 npm，请安装 Node.js 18+ 或把它加入 PATH")


def find_python() -> str:
    return sys.executable


def build_frontend() -> None:
    npm = find_npm()
    run([npm, "install", "--no-fund", "--no-audit"], cwd=FRONTEND, desc="安装前端依赖")
    run([npm, "run", "build"], cwd=FRONTEND, desc="构建前端产物")


def bundle_frontend() -> None:
    if not (FRONTEND_DIST / "index.html").is_file():
        sys.exit("未找到 frontend/dist/index.html，前端构建失败或未执行")
    if BUNDLED_DIST.exists():
        # 不用 rmtree：本机沙箱对批量删除 fail-closed 会直接杀进程。
        # rename 挪到 build 暂存区，最终由 release 打包阶段统一处理。
        stale = BUILD / f"_stale_frontend_dist_{uuid.uuid4().hex[:8]}"
        stale.parent.mkdir(parents=True, exist_ok=True)
        BUNDLED_DIST.rename(stale)
        print(f"[note] 旧 frontend_dist 已挪到 {stale.name}（可整目录手动删除）")
    shutil.copytree(FRONTEND_DIST, BUNDLED_DIST)
    print(f"[step] 前端产物已复制到 {BUNDLED_DIST.relative_to(ROOT)}")


def build_exe() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("缺少 PyInstaller，请先执行：pip install pyinstaller")

    args = [
        find_python(),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        EXE_NAME,
        "--distpath",
        str(RELEASE),
        "--workpath",
        str(BUILD / "pyinstaller"),
        "--specpath",
        str(BUILD),
        "--add-data",
        f"{BUNDLED_DIST};frontend_dist",
        "--collect-submodules",
        "uvicorn",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "PyQt5",
        str(BACKEND / "launcher.py"),
    ]
    run(args, cwd=BACKEND, desc="PyInstaller 打包后端为单文件 exe")


def assemble_release() -> None:
    (RELEASE / "使用说明.txt").write_text(USAGE_TEXT, encoding="utf-8")
    env_example = BACKEND / ".env.example"
    if env_example.exists():
        shutil.copy2(env_example, RELEASE / ".env.example")
    # 开发机上已配好的 .env 一并带上：打包后的程序读取 exe 同级的 .env，
    # 这样交付给老师/同学时 AI 开箱可用。不想分发 key 就手工删掉这个文件。
    env_file = BACKEND / ".env"
    if env_file.exists():
        shutil.copy2(env_file, RELEASE / ".env")
        print("[note] 已把 backend/.env 复制到 release/.env（含 AI Key，注意分发范围）")
    (RELEASE / "data").mkdir(exist_ok=True)

    exe = RELEASE / f"{EXE_NAME}.exe"
    if not exe.exists():
        sys.exit("打包失败：未生成 exe")
    size_mb = exe.stat().st_size / 1024 / 1024
    print("\n" + "=" * 56)
    print("打包完成")
    print("=" * 56)
    print(f"  发布目录：{RELEASE}")
    print(f"  可执行文件：{exe.name}（{size_mb:.1f} MB）")
    print("  双击 exe 即可运行；整个 release 文件夹可拷贝给他人使用")
    print("=" * 56)


def make_zip() -> None:
    """把发布目录压成一个 zip，便于通过网盘 / U 盘 / 聊天工具传给同学。"""
    import zipfile

    if not (RELEASE / f"{EXE_NAME}.exe").exists():
        sys.exit("未找到 release 中的 exe，请先完整构建一次")

    archive = RELEASE.parent / f"历史学习助手-v{VERSION}-便携版.zip"
    inner = f"历史学习助手-v{VERSION}"
    # .env 里有 AI Key，token.key 是令牌签名密钥（每台机器首次启动自建），都不进分享包
    # 注意 .env.bak / .env.20261105-183545.bak 这类备份同样含 Key，用前缀整体排除
    skip_names = {"run.log", "token.key"}
    skip_prefix = ("app.db.bak",)
    count = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(RELEASE.rglob("*")):
            if path.name in skip_names or path.name.startswith(skip_prefix):
                continue
            # 排除 .env 及其一切备份，但保留 .env.example 供接收方参考
            if path.name.startswith(".env") and path.name != ".env.example":
                continue
            rel = path.relative_to(RELEASE)
            zf.write(path, f"{inner}/{rel.as_posix()}")
            if path.is_file():
                count += 1
    size_mb = archive.stat().st_size / 1024 / 1024
    print(f"\n分享压缩包已生成：{archive.name}（{size_mb:.1f} MB，{count} 个文件）")
    print("  接收方解压后双击 exe 即可运行，无需安装任何环境")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建便携绿色版")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建（复用 frontend/dist）")
    parser.add_argument("--zip-only", action="store_true", help="不重新构建，仅重新生成分享压缩包")
    parser.add_argument("--no-zip", action="store_true", help="构建但不生成分享压缩包")
    args = parser.parse_args()

    if args.zip_only:
        make_zip()
        return

    if not args.skip_frontend:
        build_frontend()
    bundle_frontend()
    build_exe()
    assemble_release()
    if not args.no_zip:
        make_zip()


if __name__ == "__main__":
    main()
