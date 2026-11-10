"""现场查看数据库：用户清单、某个用户的全部数据、任意 SQL。

演示场景：老师现场注册一个账号 → 立刻在数据库里找到它。

用法：
    python scripts/inspect_db.py                     # 用户清单 + 各表行数
    python scripts/inspect_db.py --watch             # 盯住，有新注册用户立刻打印
    python scripts/inspect_db.py --user zhangsan     # 某用户的全部数据
    python scripts/inspect_db.py --sql "SELECT * FROM users"

数据库默认按顺序探测：release/data/app.db > backend/data/app.db > data/app.db，
也可以用 --db 指定。全程只读打开（mode=ro），不锁库、不改数据。
"""

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = [
    ROOT / "release" / "data" / "app.db",
    ROOT / "backend" / "data" / "app.db",
    ROOT / "data" / "app.db",
]

# 有 user_id 列的业务表（syllabus_nodes 是全局教材骨架，不属于任何用户）
PREFIX = {
    "users": ("用户", "id,username,display_name,track,created_at"),
    "materials": ("资料", "id,title,filetype,node_code,created_at"),
    "knowledge_points": ("知识点", "id,title,node_code,era,created_at"),
    "questions": ("题目", "id,type,substr(question,1,30) q,source,created_at"),
    "practice_records": (
        "答题记录",
        "id,question_id,correct,substr(user_answer,1,20) a,created_at",
    ),
    "wrong_book": ("错题", "id,question_id,wrong_count,error_type,next_review_at"),
    "tasks": ("复习任务", "id,title,status,due_date"),
    "events": ("历史事件", "id,title,year,era"),
    "text_notes": ("笔记/重点", "id,node_code,substr(quote,1,24) quote,color"),
    "user_memory": ("AI 记忆", "id,kind,substr(content,1,40) content,created_at"),
}


def pick_db(given):
    if given:
        p = Path(given)
        if not p.exists():
            sys.exit(f"[x] 数据库不存在：{p}")
        return p
    for p in CANDIDATES:
        if p.exists():
            return p
    sys.exit("[x] 找不到 app.db，用 --db 指定路径")


def connect(path):
    """只读连接：绝不会因为查看数据而锁住正在运行的软件。"""
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def tables(conn):
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def has_column(conn, table, col):
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def show_overview(conn, path):
    print(f"数据库：{path}\n")
    users = conn.execute(
        "SELECT id,username,display_name,track,created_at FROM users ORDER BY id"
    ).fetchall()
    print(f"用户（users 表，共 {len(users)} 个）")
    print("  id  用户名        昵称          课程      注册时间")
    for u in users:
        print(
            f"  {u['id']:<4}{u['username']:<14}{str(u['display_name'] or '-'):<14}"
            f"{str(u['track'] or '未选课'):<10}{u['created_at']}"
        )
    print("\n各表数据量")
    for t in tables(conn):
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        label = PREFIX.get(t, ("",))[0]
        extra = ""
        if t != "syllabus_nodes" and has_column(conn, t, "user_id"):
            rows = conn.execute(
                f"SELECT user_id, COUNT(*) c FROM {t} GROUP BY user_id ORDER BY user_id"
            ).fetchall()
            extra = "  按用户：" + " ".join(f"#{r[0]}={r[1]}" for r in rows)
        print(f"  {t:<20}{n:>6}  {label}{extra}")


def show_user(conn, name):
    u = conn.execute(
        "SELECT * FROM users WHERE username=? OR display_name=?", (name, name)
    ).fetchone()
    if not u:
        names = [r[0] for r in conn.execute("SELECT username FROM users ORDER BY id")]
        sys.exit(f"[x] 没有用户 {name!r}；现有：{', '.join(names)}")
    uid = u["id"]
    print(f"用户 #{uid}  {u['username']}（{u['display_name'] or '无昵称'}）")
    print(f"  注册时间  {u['created_at']}")
    print(f"  所选课程  {u['track'] or '未选课'}")
    print(f"  uuid      {u['uuid']}")
    pw = u["password_hash"] or ""
    print(f"  口令哈希  {pw[:32]}…（共 {len(pw)} 字符，PBKDF2-SHA256 20 万次迭代）")
    print(f"  盐        {(u['salt'] or '')[:16]}…（每用户随机 16 字节）")
    print("  → 库里只有哈希和盐，口令本身从不落库（这正是它安全的原因）\n")

    print("这个用户的业务数据")
    total = 0
    for t, (label, cols) in PREFIX.items():
        if t == "users" or not has_column(conn, t, "user_id"):
            continue
        rows = conn.execute(
            f"SELECT {cols} FROM {t} WHERE user_id=? ORDER BY id DESC LIMIT 3", (uid,)
        ).fetchall()
        n = conn.execute(
            f"SELECT COUNT(*) FROM {t} WHERE user_id=?", (uid,)
        ).fetchone()[0]
        total += n
        if not n:
            continue
        print(f"\n  [{label}] {t}  共 {n} 条，最近 3 条：")
        for r in rows:
            parts = []
            for k in r.keys():
                v = r[k]
                v = "" if v is None else str(v).replace("\n", " ")
                parts.append(f"{k}={v[:38]}")
            print("    " + "  ".join(parts))
    print(f"\n  合计 {total} 条业务数据")


def show_sql(conn, sql):
    if not sql.strip().lower().startswith("select"):
        sys.exit("[x] 只允许 SELECT：这是只读查看工具")
    try:
        cur = conn.execute(sql)
    except sqlite3.Error as e:
        sys.exit(f"[x] SQL 出错：{e}")
    rows = cur.fetchall()
    if not rows:
        print("（无结果）")
        return
    keys = rows[0].keys()
    print("  ".join(keys))
    print("-" * 60)
    for r in rows[:50]:
        print("  ".join("" if v is None else str(v)[:40] for v in r))
    if len(rows) > 50:
        print(f"... 共 {len(rows)} 行，只显示前 50 行")


def watch(conn, path):
    """盯住 users 表：有新账号注册就立刻打印它的全部信息。"""
    print(f"盯着 {path}")
    print("现在让老师在界面上注册一个账号，注册成功这里会自动打印（Ctrl+C 退出）\n")
    last = conn.execute("SELECT COALESCE(MAX(id),0) FROM users").fetchone()[0]
    print(f"当前最大用户 id = {last}，等待新注册…")
    while True:
        try:
            conn2 = connect(path)  # 每次重开连接，拿到最新提交的数据
            new = conn2.execute(
                "SELECT id,username,display_name,track,created_at FROM users WHERE id>? ORDER BY id",
                (last,),
            ).fetchall()
            for u in new:
                print("\n" + "=" * 56)
                print(
                    f"[新用户] #{u['id']}  {u['username']}（{u['display_name'] or '无昵称'}）"
                )
                print(f"  课程 {u['track'] or '未选课'}    注册于 {u['created_at']}")
                show_user(conn2, u["username"])
                print("=" * 56)
                last = u["id"]
            conn2.close()
        except sqlite3.Error as e:
            print(f"（读库失败，稍后重试：{e}）")
        time.sleep(1.5)


def main():
    ap = argparse.ArgumentParser(description="查看四史学习助手的数据库（只读）")
    ap.add_argument("--db", help="app.db 路径，默认自动探测 release/data/app.db")
    ap.add_argument("--user", help="查看某个用户（用户名或昵称）的全部数据")
    ap.add_argument("--sql", help="执行一条 SELECT 语句")
    ap.add_argument("--watch", action="store_true", help="盯着新注册用户自动打印")
    a = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    path = pick_db(a.db)
    conn = connect(path)
    try:
        if a.watch:
            watch(conn, path)
        elif a.sql:
            show_sql(conn, a.sql)
        elif a.user:
            show_user(conn, a.user)
        else:
            show_overview(conn, path)
            print(
                "\n更多：--user 用户名 看某个人的全部数据 | --watch 盯新注册 | "
                '--sql "SELECT * FROM users"'
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
