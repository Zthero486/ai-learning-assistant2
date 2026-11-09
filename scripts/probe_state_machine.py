"""状态机线上探针：真模型跑一次对话，把 act→review→回流→finalize 的全过程打出来。

用法（服务需已启动）：
    python scripts/probe_state_machine.py "帮我按我的情况排一个三天的改革开放史复习计划"
    python scripts/probe_state_machine.py "改革开放史有哪几章" --no-write
    python scripts/probe_state_machine.py --user demo --password demo123 --base http://127.0.0.1:8000 "..."

为什么用它而不是看界面：界面上「质量自查」卡片只显示结果，这里能逐条看到
SSE 原始事件——状态切换、每次工具调用、质检裁决、回流时喂回模型的缺口原文。
"""

import argparse
import json
import sys

import requests

STATE_NAME = {"act": "执行", "review": "审查", "finalize": "收尾"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", help="要问 AI 的话")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="demo")
    ap.add_argument("--password", default="demo123")
    ap.add_argument("--no-write", action="store_true", help="只读模式（关闭 7 个写工具）")
    ap.add_argument("--track", default="", help="可选：先切到某门课（party/prc/reform/socialism）")
    args = ap.parse_args()

    s = requests.Session()
    s.trust_env = False  # 本机 Clash 常开着，别让系统代理把 127.0.0.1 也接走
    r = s.post(f"{args.base}/api/auth/login",
               json={"username": args.user, "password": args.password}, timeout=10)
    if r.status_code != 200:
        print(f"登录失败 {r.status_code}: {r.text[:200]}")
        return 1
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    if args.track:
        rr = s.post(f"{args.base}/api/profile/track", json={"track": args.track}, headers=headers)
        print(f"[切课] {args.track} -> {rr.status_code}")

    body = {"messages": [{"role": "user", "content": args.question}],
            "allow_write": not args.no_write, "stream": True}

    print(f"\n用户：{args.question}")
    print("─" * 60)

    states, tools, reviews, reply, reflow = [], [], [], "", []
    with s.post(f"{args.base}/api/ai/chat", json=body, headers=headers,
                stream=True, timeout=300) as resp:
        if resp.status_code != 200:
            print(f"对话失败 {resp.status_code}: {resp.text[:300]}")
            return 1
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            try:
                ev = json.loads(raw[6:])
            except json.JSONDecodeError:
                continue
            t = ev.get("type")

            if t == "state":
                st = ev.get("state")
                states.append(st)
                if st == "act" and ev.get("reason"):
                    reflow.append(ev["reason"])
                    print(f"\n★ [回流] 质检未通过，缺口：{ev['reason']}")
                    print("   → 带着这个缺口回到「执行」")
                else:
                    print(f"\n[{STATE_NAME.get(st, st)}]"
                          + (f" 第 {ev['round']} 次" if ev.get("round") else ""))

            elif t == "thinking":
                txt = (ev.get("text") or "").replace("\n", " ")
                print(f"   💭 思考：{txt[:120]}")

            elif t == "step" and ev.get("phase") == "start":
                mark = "写" if ev.get("write") else "读"
                args = ev.get("args") or {}
                brief = ", ".join(f"{k}={str(v)[:22]}" for k, v in list(args.items())[:3])
                print(f"   · 调用 {ev['tool']}（{mark}）", end="")
                if brief:
                    print(f"  [{brief[:70]}]", end="")

            elif t == "step" and ev.get("phase") == "end":
                ms = ev.get("ms")
                print(f"  {'✓' if ev.get('ok') else '✗'} {ev.get('summary', '')}"
                      + (f"  ({ms}ms)" if ms is not None else ""))
                tools.append(ev.get("tool"))

            elif t == "error":
                print(f"\n[错误] {ev.get('message')}")

            elif t == "done":
                reply = ev.get("reply") or ""
                print("\n" + "─" * 60)
                print(f"答复：{reply[:600]}")
                print("─" * 60)
                print(f"状态迁移：{' → '.join(STATE_NAME.get(x, x) for x in states)}")
                print(f"工具 {ev.get('tool_calls', len(tools))} 次 / 模型轮次 {ev.get('rounds')} "
                      f"/ 质检 {ev.get('reviews', 0)} 次 / 回流 {len(reflow)} 次"
                      + (f" / 用时 {ev['elapsed_ms'] / 1000:.1f}s" if ev.get("elapsed_ms") else ""))
                if ev.get("truncated"):
                    why = {"time": "总时长到顶", "rounds": "轮次用尽"}.get(ev.get("truncated_by"), "轮次用尽")
                    print(f"⚠ {why}，强制收尾")

    return 0


if __name__ == "__main__":
    sys.exit(main())
