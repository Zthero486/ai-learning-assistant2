"""一键切换软件的 AI 模型通道（写 .env + 运行中实例即时生效 + 连通性自测）。

用法：
    python scripts/switch_ai.py zhipu --key 你的key
    python scripts/switch_ai.py stepfun --key xx --model step-3.5-flash
    python scripts/switch_ai.py --show            # 只看当前配置

预设取自 backend/app/ai_helper.PROVIDER_PRESETS，不重复维护一份。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import requests  # noqa: E402

from app.ai_helper import PROVIDER_PRESETS  # noqa: E402


def rewrite_env(path, values):
    """把 KEY=VALUE 写进 .env，保留注释与其它行；不存在则追加。"""
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    seen = set()
    out = []
    for ln in lines:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", ln)
        if m and m.group(1) in values:
            out.append("%s=%s" % (m.group(1), values[m.group(1)]))
            seen.add(m.group(1))
        else:
            out.append(ln)
    for k, v in values.items():
        if k not in seen:
            out.append("%s=%s" % (k, v))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out).rstrip() + "\n")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("provider", nargs="?", help="预设名：%s" % ", ".join(PROVIDER_PRESETS))
    ap.add_argument("--key")
    ap.add_argument("--model")
    ap.add_argument("--base")
    ap.add_argument("--host", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="demo")
    ap.add_argument("--passwd", default="demo123")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()

    s = requests.Session()
    s.trust_env = False
    tok = s.post(a.host + "/api/auth/login",
                 json={"username": a.user, "password": a.passwd}, timeout=15).json().get("token")
    if not tok:
        print("[x] 登录失败，检查 --user/--passwd 或服务是否在跑")
        return 1
    h = {"Authorization": "Bearer " + tok}

    if a.show or not a.provider:
        cfg = s.get(a.host + "/api/config/ai", headers=h, timeout=15).json()
        print("当前: source=%s model=%s base=%s" % (cfg.get("source"), cfg.get("model"), cfg.get("base_url")))
        print("预设: " + ", ".join(PROVIDER_PRESETS))
        return 0

    if a.provider not in PROVIDER_PRESETS:
        print("[x] 未知预设 %s，可选：%s" % (a.provider, ", ".join(PROVIDER_PRESETS)))
        return 1
    preset = PROVIDER_PRESETS[a.provider]
    base = (a.base or preset["base_url"]).rstrip("/")
    model = a.model or preset["model"]

    if a.provider != "stepfun" and not a.key:
        print("[x] 这个通道需要 --key")
        return 1

    body = {"api_key": a.key or "", "base_url": base, "model": model}
    r = s.post(a.host + "/api/config/ai", json=body, headers=h, timeout=30)
    print("配置写入: %s %s" % (r.status_code, r.text[:200]))
    r.raise_for_status()

    # 开发态 backend/.env 一并镜像，避免下次打包又回到旧通道
    dev = os.path.join(ROOT, "backend", ".env")
    if os.path.exists(dev):
        vals = {"AI_BASE_URL": base, "AI_MODEL": model}
        if a.key:
            vals["AI_API_KEY"] = a.key
        rewrite_env(dev, vals)
        print("已同步: %s" % dev)

    t = s.post(a.host + "/api/ai/test", headers=h, timeout=60)
    print("连通测试: %s %s" % (t.status_code, t.text[:300]))
    hl = s.get(a.host + "/api/health", timeout=10).json()
    print("health: ai_source=%s ai_model=%s" % (hl.get("ai_source"), hl.get("ai_model")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
