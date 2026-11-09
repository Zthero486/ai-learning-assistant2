"""现场演示：AI Agent 状态机（act → review → 回流 → finalize）。

默认三幕**全部离线确定性**执行——模型换成脚本化的假模型、质检员换成预设裁决，
所以不花 token、不依赖网络、每幕一秒钟，投屏演示不会翻车。
`--live` 再追加一幕真模型实跑，用来证明「不是演的」。

用法：
    python scripts/demo_state_machine.py                 # 三幕，秒级
    python scripts/demo_state_machine.py --pause          # 每幕按 Enter 继续（讲解节奏）
    python scripts/demo_state_machine.py --live           # 追加真模型一幕（需 AI key）
    python scripts/demo_state_machine.py --live -q "帮我按我的情况排三天复习计划"

演示用的数据库是临时库（系统 temp 下一个随机目录），**不会碰你的真实数据**。
"""

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

TMP = Path(tempfile.mkdtemp(prefix="sm_demo_"))

from app import ai_agent  # noqa: E402
from app import main as app_main  # noqa: E402

app_main.DB_PATH = TMP / "demo.db"  # 临时库：演示写入全落在临时目录
app_main.init_db()

BAR = "─" * 62
STATE_CN = {"act": "执行 act", "review": "审查 review", "finalize": "收尾 finalize"}
SUMMARY = []  # [(幕名, 状态迁移, 工具数, 质检数, 回流数)]


def seed_demo_data() -> None:
    """给临时库灌一点演示数据：不然统计工具全返回 0，投屏不好看。"""
    import uuid as _uuid
    conn = app_main.db()
    now = app_main.now()
    conn.execute("UPDATE users SET track='party' WHERE id=1")
    titles = ["遵义会议", "长征精神", "敌后抗战", "延安整风", "中共七大", "开国大典",
              "土地改革", "一五计划", "三大改造", "抗美援朝", "五四宪法", "八大路线"]
    kp_ids = []
    for i, t in enumerate(titles):
        cur = conn.execute(
            "INSERT INTO knowledge_points(user_id,uuid,course,title,description,created_at,"
            "node_code,exam_type) VALUES(1,?,?,?,?,?,?,?)",
            (_uuid.uuid4().hex, "党史", t, "", now,
             f"party-{(i // 4) + 1:02d}-{(i % 4) + 1:02d}", "recall"),
        )
        kp_ids.append(cur.lastrowid)
    q_ids = []
    for i in range(6):
        cur = conn.execute(
            "INSERT INTO questions(user_id,uuid,kp_id,type,question,answer,evidence,source,created_at)"
            " VALUES(1,?,?,?,?,?,?,?,?)",
            (_uuid.uuid4().hex, kp_ids[i], "单选题", f"演示题 {i + 1}？", "A", "原文", "ai", now),
        )
        q_ids.append(cur.lastrowid)
    for i in range(24):
        conn.execute(
            "INSERT INTO practice_records(user_id,uuid,question_id,user_answer,correct,created_at)"
            " VALUES(1,?,?,?,?,?)",
            (_uuid.uuid4().hex, q_ids[i % 6], "A", 1 if i % 3 else 0, now),
        )
    for qid in q_ids[:2]:
        conn.execute(
            "INSERT INTO wrong_book(user_id,uuid,question_id,wrong_count,resolved,last_wrong_at)"
            " VALUES(1,?,?,1,0,?)",
            (_uuid.uuid4().hex, qid, now),
        )
    conn.commit()
    conn.close()



def head(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m" if sys.stdout.isatty() else f"\n{title}")
    print(BAR)


def step_show(events: list, question: str) -> None:
    """把 run_events 吐的事件按人话打出来。"""
    t0 = time.perf_counter()
    tools = 0
    reviews = 0
    reflows = 0
    states = []
    for ev in events:
        t = ev.get("type")
        if t == "state":
            st = ev.get("state")
            states.append(st)
            if st == "review":
                reviews += 1
            if st == "act" and ev.get("reason"):
                reflows += 1
                print(f"  ★ 回流 → 带着质检意见回到「执行」")
                print(f"    缺口：{ev['reason']}")
            else:
                arrow = "  ▶" if st != "finalize" else "  ■"
                extra = f"（第 {ev['round']} 次）" if ev.get("round") else ""
                print(f"{arrow} {STATE_CN.get(st, st)}{extra}")
        elif t == "step" and ev.get("phase") == "end":
            tools += 1
            mark = "写" if ev.get("write") else "读"
            ok = "✓" if ev.get("ok") else "✗"
            print(f"     · {ev['tool']}（{mark}）{ok} {ev.get('summary', '')}")
    done = events[-1] if events else {}
    if done.get("type") == "done":
        print(f"\n  答复：{done.get('reply', '')[:220]}")
    print(f"  状态迁移：{' → '.join(STATE_CN.get(s, s).split()[0] for s in states)}")
    print(f"  工具 {done.get('tool_calls', tools)} 次 / 模型轮次 {done.get('rounds')} "
          f"/ 质检 {done.get('reviews', reviews)} 次 / 回流 {reflows} 次 "
          f"/ 本次耗时 {time.perf_counter() - t0:.2f}s")
    SUMMARY.append(("", " → ".join(states), done.get("tool_calls", tools),
                    done.get("reviews", reviews), reflows))


def scripted_chat(script: list):
    """script: [(kind, payload)]；kind='tools' 时 payload={'name':..,'args':{..}}。"""
    calls = []

    def fake(convo, tools=None, **kw):
        calls.append([dict(m) for m in convo])
        kind, payload = script[min(len(calls) - 1, len(script) - 1)]
        if kind == "tools":
            return {"content": "", "tool_calls": [{
                "id": f"call_{len(calls)}", "type": "function",
                "function": {"name": payload["name"],
                             "arguments": json.dumps(payload.get("args", {}), ensure_ascii=False)},
            }]}
        return {"content": payload, "tool_calls": []}

    return fake, calls


def run_scene(title: str, question: str, script: list, verdicts: list, allow_write=True) -> list:
    head(title)
    print(f"  用户：「{question}」\n")
    ctx = ai_agent.AgentContext(1, "party", app_main.db, app_main.now)
    fake, _calls = scripted_chat(script)
    orig_chat, orig_review = ai_agent.ai_helper.chat_completion, ai_agent._review_draft
    pending = list(verdicts)
    ai_agent.ai_helper.chat_completion = fake
    ai_agent._review_draft = lambda *a: pending.pop(0) if pending else {"done": True, "gap": ""}
    try:
        events = list(ai_agent.run_events(
            ctx, [{"role": "user", "content": question}], allow_write=allow_write))
    finally:
        ai_agent.ai_helper.chat_completion = orig_chat
        ai_agent._review_draft = orig_review
    step_show(events, question)
    return events


def scene_pass() -> None:
    run_scene(
        "【幕一】一次通过：act → review → finalize",
        "看看我的学习情况，我该重点补哪里？",
        [("tools", {"name": "get_my_stats"}), ("text", "你目前有 12 个知识点、做过 24 次练习，"
                                                "还有 2 道错题没过；错题集中在第三、五章，建议先补这两章的时间线。")],
        [{"done": True, "gap": ""}],
    )


def scene_reflow() -> None:
    run_scene(
        "【幕二】质检不达标 → 回流重做（状态机的核心）",
        "按我的情况排一个三天复习计划",
        [("tools", {"name": "get_my_stats"}),
         ("text", "你最近在学党史，进度还不错。"),
         ("text", "已按你的薄弱点排好三天计划：D1 第三章时间线，D2 第五章错题重做，"
                  "D3 整套自测 + 错题复盘。")],
        [{"done": False, "gap": "学生要的是三天复习计划，你只报了个学习进度，没给出可执行的安排"},
         {"done": True, "gap": ""}],
    )


def scene_memory() -> None:
    events = run_scene(
        "【幕三】把知识沉淀进记忆库（反哺之后的复习建议）",
        "记住：我大三，在准备期末，遵义会议的时间线老是记混",
        [("tools", {"name": "save_memory",
                    "args": {"kind": "weakness", "content": "遵义会议时间线常记混"}}),
         ("text", "已记住：你大三、在准备期末，薄弱点是遵义会议的时间线。"
                  "下次排计划我会优先安排这一段。")],
        [{"done": True, "gap": ""}],
    )
    conn = app_main.db()
    rows = conn.execute("SELECT kind, content FROM user_memory WHERE user_id=1").fetchall()
    conn.close()
    print(f"\n  记忆库当前 {len(rows)} 条：")
    for r in rows:
        print(f"     · [{r['kind']}] {r['content']}")
    if events and events[-1].get("type") == "done":
        SUMMARY[-1] = ("", " → ".join(["act", "review", "finalize"]),
                       events[-1].get("tool_calls", 1), events[-1].get("reviews", 1), 0)


def scene_live(question: str) -> None:
    head("【幕四】真模型实跑：同样的状态机，模型换成 StepFun")
    if not ai_agent.ai_helper.is_available():
        print("  跳过：未配置 AI key（.env 里没有 AI_API_KEY）。这一幕需要联网。")
        return
    from app import qushi
    conn = app_main.db()
    qushi.ensure_syllabus(conn)
    conn.close()
    ctx = ai_agent.AgentContext(1, "party", app_main.db, app_main.now)
    print(f"  用户：「{question}」\n")
    t0 = time.perf_counter()
    states = []
    last = time.perf_counter()
    for ev in ai_agent.run_events(ctx, [{"role": "user", "content": question}], allow_write=True):
        now_ = time.perf_counter()
        gap = now_ - last
        last = now_
        t = ev.get("type")
        if t == "state":
            st = ev.get("state")
            states.append(st)
            if st == "act" and ev.get("reason"):
                print(f"  ★ 回流（{gap:.1f}s）缺口：{ev['reason']}")
            else:
                print(f"  ▶ {STATE_CN.get(st, st)}（+{gap:.1f}s）")
        elif t == "step" and ev.get("phase") == "end":
            ok = "✓" if ev.get("ok") else "✗"
            print(f"     · {ev['tool']} {ok} {ev.get('summary', '')}")
        elif t == "error":
            print(f"  [错误] {ev.get('message')}")
        elif t == "done":
            print(f"\n  答复：{(ev.get('reply') or '')[:400]}")
            print(f"  工具 {ev.get('tool_calls')} 次 / 轮次 {ev.get('rounds')} / "
                  f"质检 {ev.get('reviews')} 次 / 总耗时 {time.perf_counter() - t0:.1f}s")
            SUMMARY.append(("", " → ".join(states), ev.get("tool_calls", 0),
                            ev.get("reviews", 0), 0))


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Agent 状态机现场演示")
    ap.add_argument("--pause", action="store_true", help="每幕结束按 Enter 再继续")
    ap.add_argument("--live", action="store_true", help="追加一幕真模型实跑（需联网 + AI key）")
    ap.add_argument("-q", "--live-question", default="党史有几章？第三章主要讲了什么？",
                    help="真模型那一幕的提问（默认是党史范围内、会触发查目录/读正文工具的题）")
    args = ap.parse_args()

    print("\n" + "═" * 62)
    print("  AI 学习助手 · Agent 状态机演示")
    print("  接收需求 → 模型自主调工具 → 独立质检 → 不达标就带着意见回流 → 达标收尾")
    print("═" * 62)
    print("  本次三幕是「脚本化模型 + 预设裁决」，不联网、不花 token，用来演示机制；")
    print(f"  --live 可追加真模型。临时库：{TMP}")
    seed_demo_data()

    acts = [("幕一 一次通过", scene_pass),
            ("幕二 不达标回流", scene_reflow),
            ("幕三 记忆沉淀", scene_memory)]
    for name, fn in acts:
        fn()
        SUMMARY[-1] = (name, *SUMMARY[-1][1:])
        if args.pause:
            input("\n  ⏎ 按 Enter 进入下一幕…")
    if args.live:
        scene_live(args.live_question)
        if SUMMARY and SUMMARY[-1][0] == "":
            SUMMARY[-1] = ("幕四 真模型", *SUMMARY[-1][1:])

    print("\n" + "═" * 62)
    print("  演示汇总")
    print(BAR)
    for name, states, tools, reviews, reflows in SUMMARY:
        short = " → ".join({"act": "act", "review": "review", "finalize": "finalize"}.get(s, s)
                           for s in states.split(" → "))
        print(f"  {name:<12} {short:<34} 工具 {tools} / 质检 {reviews} / 回流 {reflows}")
    print(BAR)
    print("  看点：幕二一定出现「★ 回流」——第一版答复被独立质检判为不合格，")
    print("        审查意见作为新一轮输入喂回模型，第二版才收尾。")
    print("        幕三说明对话结论会落进 user_memory，之后的建议会带上你的画像。")
    print("═" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
