"""把题库导出成 Markdown 文件，方便人工通读查错。

用法：
    python scripts/export_questions.py                # 导出 release/data/app.db 的全部题目
    python scripts/export_questions.py --db data/app.db --out 题库-开发库.md

导出内容按知识点分组，带 id（方便回报「#189 这题错了」）、题型、来源、答案；
机器能查出来的问题（选择题没选项、答案为空等）会在行内用 ⚠ 标出。
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def has_options(text: str) -> bool:
    return re.search(r"(^|[^A-Za-z0-9])A\s*[.、．)）：:]", text or "") is not None


def issues(row) -> list:
    t, q, a = row["type"] or "", row["question"] or "", row["answer"] or ""
    out = []
    if not q.strip():
        out.append("题干为空")
    if not a.strip():
        out.append("答案为空")
    if "单选" in t or "多选" in t:
        if not has_options(q):
            out.append("标了选择题但题干没有 A/B/C 选项（作答会退化成手动输入）")
        if not re.match(r"^[A-D]", a.strip()):
            out.append("答案不以字母开头")
    elif has_options(q):
        out.append("题干带选项但题型不是选择")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "release" / "data" / "app.db"))
    ap.add_argument("--out", default=str(ROOT / "题库导出.md"))
    ap.add_argument("--only-bad", action="store_true", help="只导出带可疑标记的题")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT q.id, q.type, q.question, q.answer, q.source, q.kp_id,
                  k.title AS kp_title, k.node_code
           FROM questions q LEFT JOIN knowledge_points k ON k.id = q.kp_id
           ORDER BY q.id"""
    ).fetchall()

    # 按知识点聚合，无知识点的归「未挂知识点」
    groups: dict = {}
    for r in rows:
        key = r["kp_title"] or "（未挂知识点）"
        groups.setdefault(key, []).append(r)

    n_bad = 0
    lines = [
        f"# 题库导出（{len(rows)} 题）",
        "",
        f"- 来源库：`{args.db}`",
        "- ⚠ = 机器查出的问题，不一定是错，但建议人工核对",
        "- 回报错误时直接说「#编号 这题错了」即可",
        "",
    ]
    for kp, items in sorted(groups.items(), key=lambda kv: min(i["id"] for i in kv[1])):
        lines.append(f"## {kp}（{len(items)} 题）")
        lines.append("")
        for r in items:
            bad = issues(r)
            mark = ("⚠ " + "；".join(bad)) if bad else ""
            n_bad += bool(bad)
            if args.only_bad and not bad:
                continue
            lines.append(f"### #{r['id']} [{r['type'] or '未标型'}] {r['source'] or ''}")
            lines.append("")
            lines.append(r["question"] or "（空）")
            lines.append("")
            lines.append(f"**答案**：{r['answer'] or '（空）'}")
            if mark:
                lines.append("")
                lines.append(f"> ⚠ {mark}")
            lines.append("")
    lines.insert(4, f"- 共 {n_bad} 题带 ⚠ 标记" if n_bad else "- 未发现机器可查的问题")
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"已导出 {len(rows)} 题（{n_bad} 题带⚠）-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
