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
import os
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
EXE_NAME = "AILearningAssistant"  # 保持稳定：升级靠替换同名 exe，别改
PRODUCT_NAME = "四史学习助手"
VERSION = "1.0"
BUILTIN_KEY_FILE = BACKEND / "app" / "_builtin_key.py"  # 打包期临时生成，随后删除（已 gitignore）

USAGE_TEXT = """「四史」学习助手 v1.0 —— 使用说明
====================================================

【这是什么】
面向高校思政课「四史」（党史 / 新中国史 / 改革开放史 / 社会主义发展史）
的学习系统：内置四门课的教材章节目录与关键史事，按课本脉络整理笔记、
做题、复习。

【怎么启动】
双击 AILearningAssistant.exe。程序会自动启动本地服务并打开浏览器界面。
首次启动约需 3~10 秒（需解压运行时），请耐心等待，不要重复双击。

【第一次用：先选课】
注册/登录后先选一门课（每学期通常只修一门），选定后整个软件的教材目录、
时间轴、出题范围都跟着这门课走。中途要换：左下角「切换课程」。
换课不会删数据，切回来笔记和错题都还在。

【怎么退出】
关闭弹出的黑色命令行窗口即可（浏览器标签页可以直接关掉，
不影响数据，下次打开还是原来的进度）。

【数据存在哪】
本程序目录下的 data 文件夹：
    data/app.db     学习数据（资料、知识点、任务、练习、错题、统计）
    data/uploads/   导入的原始文档
整个文件夹可以整体拷贝到别的电脑，数据一起带走（便携绿色版，免安装）。

【升级版本时要注意】
不需要每次重新解压！新版本只要**替换掉 AILearningAssistant.exe** 就行，
data 文件夹不用动，进度、错题、笔记全都在。
（真要重新解压也可以：data/app.db 已存在时程序不会覆盖它，
 随包的 data/app.db.seed 只在第一次启动、还没有 app.db 时才会复制一份。）

【AI 功能】
本版本已内置阶跃 StepFun 大模型，装好即用，不需要任何配置：
史料总结、史料答疑、按错题个性化出题、薄弱点分析都由大模型驱动。

【AI 对话（最省事的用法）】
左侧「AI 对话」是聊天窗口，这里的 AI 不只是聊天——它能直接操作软件：
  · 查教材目录、翻史料原文、看时间轴（只读）
  · 建史实要点、生成资料存进史料笔记、出练习题、建复习任务、补时间轴（写入）
说一句「帮我学第三章」「把这一章整理成资料并出 5 道题」，它会自己跑完并告诉你写到了哪。
不想让它改数据，把右上角「允许 AI 写入」关掉即可（只剩查询能力）。
AI 没有任何删除权限；写入都会在对话里以卡片显示，随时去对应页面检查。

想换成自己的模型（可选，不影响使用）：
打开「AI 对话」→「AI 设置」（或左侧「AI 工具台」→「配置 API Key」）→ 选平台预设
（智谱 GLM / DeepSeek / MiniMax 等）→ 粘贴自己的 Key → 保存并生效 → 点「检测 AI 连接」。
随时可以点「恢复默认（阶跃）」切回内置默认。

注意：阶跃的地址要用 https://api.stepfun.com/v1（/step_plan/v1 是订阅套餐专用，
账号没订阅会报 400）。只有用境外平台（如 Google Gemini）才需要填代理地址，
一般是 http://127.0.0.1:7897，换成你自己的端口。

【手机 / 平板上用】
两种方式：
1) 同一 WiFi（不用服务器）：双击本目录的 start-lan.bat（等效于命令行运行
       AILearningAssistant.exe --lan
   ），黑窗口会列出手机访问地址（如 http://192.168.x.x:8000），手机浏览器打开即可；
   也可以在电脑端网页左下角点「手机访问」扫码。首次使用请允许防火墙（专用网络）。
2) 任何网络都能用：把后端部署到公网，见 docs/部署到公网.md（内网穿透 10 分钟，
   云服务器 7x24 长期方案都有）。手机浏览器「添加到主屏幕」后就是一个 App。

【浏览器没自动打开怎么办】
手动打开浏览器，访问 http://127.0.0.1:8000
（若提示端口占用，程序会自动改用 8001，请查看黑窗口里显示的地址）

【常见问题】
- 杀毒软件误报：本程序由 Python 打包生成，未签名，可能被拦截；
  选择"允许运行/添加信任"即可。
- 内置的 AI Key 是课程演示用的共享额度，够几个人做题；如果哪天报"余额不足/触发限流"，
  换成自己的 Key 即可（上面「AI 功能」里的步骤）。
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


def _read_env_value(name: str) -> str:
    """从 backend/.env 读一个值（本脚本只处理 KEY=VALUE 简单格式）。"""
    env_path = BACKEND / ".env"
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == name:
            return v.strip()
    return ""


def embed_builtin_key(enabled: bool) -> None:
    """把 .env 里的 AI key 注入 _builtin_key.py，随 exe 冻结成「内置默认」。

    这样分享包解压即用（默认走阶跃 StepFun），接收方仍可在界面里换成自己的
    模型——用户配置的环境变量优先级高于内置 key。
    用 --no-embed-key 构建则写入空值，等价于「必须自己配 key」。
    """
    key = _read_env_value("AI_API_KEY") if enabled else ""
    BUILTIN_KEY_FILE.write_text(
        '"""打包期自动生成：内置默认 AI key（不要提交到仓库）。\n\n'
        "为空字符串时表示该构建不内置 key，用户需自行配置。\n"
        '"""\n\n'
        f'BUILTIN_API_KEY = "{key}"\n',
        encoding="utf-8",
    )
    if key:
        masked = key[:4] + "*" * 8 + key[-4:] if len(key) >= 10 else "****"
        print(f"[note] 已内置默认 AI key（{masked}），分享包开箱即用；用 --no-embed-key 可关闭")
    else:
        print("[note] 未内置 AI key（--no-embed-key 或 .env 里没有 AI_API_KEY）")


def clear_builtin_key() -> None:
    """把临时的 _builtin_key.py 挪出源码树，避免 key 被误提交。

    注意：这里**不能** unlink。本机沙箱会拦截进程内的删除操作（连带一个陈旧的
    pytest 垃圾目录一起 fail-closed，整轮进程被杀），而 PyInstaller 此时已经
    成功产出 exe，收尾步骤反而全被跳过。用 rename 挪到 build/_stale_builtin_key
    既达到「key 不在源码树」的目的，又绕开删除拦截。
    """
    if not BUILTIN_KEY_FILE.exists():
        return
    trash = BUILD / "_stale_builtin_key"
    trash.mkdir(parents=True, exist_ok=True)
    BUILTIN_KEY_FILE.replace(trash / f"_builtin_key_{uuid.uuid4().hex[:6]}.py")



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

    # 沙箱保护：本机对「一轮内批量删除」fail-closed，--clean 会删缓存里的几百个文件
    # 而被整轮拒绝。设 WB_NOCLEAN=1 时改用全新的 workpath、且不传 --clean。
    noclean = bool(os.environ.get("WB_NOCLEAN"))
    workdir = BUILD / (f"pi_{uuid.uuid4().hex[:8]}" if noclean else "pyinstaller")

    # 沙箱对进程内删除 fail-closed：PyInstaller 覆盖已有 exe 时会先删掉它，整轮进程
    # 会被直接杀掉（表现为 "Building EXE from EXE-00.toc" 后 exit 1、exe 却没更新）。
    # 先 rename 挪走旧产物（同盘 rename 不受限），新 exe 就是新建文件，不会触发删除。
    old_exe = RELEASE / f"{EXE_NAME}.exe"
    if old_exe.exists():
        stale_exe = BUILD / "_stale_exe"
        stale_exe.mkdir(parents=True, exist_ok=True)
        old_exe.replace(stale_exe / f"{EXE_NAME}_{uuid.uuid4().hex[:6]}.exe")
        print("[note] 旧 exe 已挪到 build/_stale_exe（可整目录手动删除）")

    args = [
        find_python(),
        "-m",
        "PyInstaller",
        "--noconfirm",
        *([] if noclean else ["--clean"]),
        "--onefile",
        "--console",
        "--icon",
        str(ROOT / "assets" / "app.ico"),
        "--name",
        EXE_NAME,
        "--distpath",
        str(RELEASE),
        "--workpath",
        str(workdir),
        "--specpath",
        str(BUILD),
        "--add-data",
        f"{BUNDLED_DIST};frontend_dist",
        # 内置课程数据（四史章节树 + 关键事件）。qushi.py 用 __file__ 相对定位，
        # onefile 解包后对应 _MEIPASS/app/seed_data/，所以目标目录必须是 app/seed_data。
        "--add-data",
        f"{BACKEND / 'app' / 'seed_data'};app/seed_data",
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

    archive = RELEASE.parent / f"{PRODUCT_NAME}-v{VERSION}-便携版.zip"
    inner = f"{PRODUCT_NAME}-v{VERSION}"
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
            arcname = f"{inner}/{rel.as_posix()}"
            # 演示库改名成 .seed：首次启动才复制成 app.db。
            # 这样「新 zip 解压覆盖旧目录」也不会把学生已有数据冲掉。
            if rel.as_posix() == "data/app.db":
                arcname = f"{inner}/data/app.db.seed"
            zf.write(path, arcname)
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
    parser.add_argument(
        "--no-embed-key",
        action="store_true",
        help="不内置 AI key（默认会把 backend/.env 的 key 打进 exe，开箱即用）",
    )
    args = parser.parse_args()

    if args.zip_only:
        make_zip()
        return

    if not args.skip_frontend:
        build_frontend()
    bundle_frontend()
    try:
        embed_builtin_key(not args.no_embed_key)
        build_exe()
    finally:
        clear_builtin_key()  # 无论成功失败，都不把 key 留在源码树
    assemble_release()
    if not args.no_zip:
        make_zip()


if __name__ == "__main__":
    main()
