#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy 会话自救工具（wb_session_doctor）

用途：WorkBuddy 侧边栏里的对话「消失」了，先查清楚到底是哪一种消失，再按提示恢复。

三种「消失」，处理方式完全不同：
  1) 被归档        -> 任务还在，只是不在列表里，去 UI 的「数据管理」找回来即可，脚本只负责告诉你哪些被归档
  2) 被删除/软删   -> 数据库里 deleted_at 有值，但对话正文 .jsonl 还在，可以 --fix-deleted 复活
  3) 索引丢失      -> 正文 .jsonl 还在，但 sessions 表里没有这一行，可以 --fix-orphan 重建索引

存储位置（Windows）：
  C:\\Users\\<你>\\.workbuddy\\workbuddy.db              <- sessions 表，侧边栏列表就是从这渲染的
  C:\\Users\\<你>\\.workbuddy\\projects\\<目录slug>\\*.jsonl <- 对话正文，一行一条消息

用法：
  python wb_session_doctor.py                  # 只读诊断，什么都不改（默认）
  python wb_session_doctor.py --dump out       # 把所有对话正文导出成可读 md，最保险的一步
  python wb_session_doctor.py --fix-deleted    # 复活被软删的会话（会先备份数据库）
  python wb_session_doctor.py --fix-orphan     # 给孤立 .jsonl 补回 sessions 行（会先备份）

写操作前请完全退出 WorkBuddy（托盘图标也要退），否则数据库会被锁住。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

IS_WIN = os.name == "nt"


def setup_stdout() -> None:
    """Windows 控制台默认 GBK，中文会炸，尽量切成 utf-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- 基础定位

def normalize_path(raw: str) -> str:
    """把 Git Bash 风格的 /c/Users/... 还原成 C:/Users/...，避免建到 C:\\c\\ 下面。"""
    m = re.match(r"^/([a-zA-Z])/(.*)$", raw.replace("\\", "/"))
    if IS_WIN and m:
        return f"{m.group(1).upper()}:/{m.group(2)}"
    return raw


def workbuddy_home(explicit: str | None = None) -> Path:
    if explicit:
        return Path(normalize_path(explicit)).expanduser()
    if IS_WIN:
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".workbuddy"
    return Path.home() / ".workbuddy"


def to_uri(p: Path) -> str:
    return "file:" + str(p).replace("\\", "/") + "?mode=ro"


def open_ro(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(to_uri(db), uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def fmt_ts(ms: int | None) -> str:
    if not ms:
        return "-"
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ms)


def safe_title(row) -> str:
    return (row["custom_title"] or row["title"] or "(无标题)").strip()


# ---------------------------------------------------------------- 读 jsonl

def extract_text(obj: dict) -> str:
    """把一条 jsonl 记录里的文本捞出来，兼容 str / 多段 content。"""
    content = obj.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for seg in content:
            if isinstance(seg, dict):
                t = seg.get("text")
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(seg, str):
                parts.append(seg)
        return "\n".join(parts)
    return ""


def strip_reminders(text: str) -> str:
    """去掉 <system-reminder> / <user_info> 这类注入块，只留人写的话。"""
    if not text:
        return ""
    text = re.sub(r"<system-reminder[\s\S]*?</system-reminder>", " ", text)
    text = re.sub(r"<[^>]{1,60}>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def read_jsonl(path: Path) -> dict:
    """扫一遍 jsonl，得到标题、工作目录、消息数、时间范围。"""
    info = {
        "path": str(path),
        "lines": 0,
        "msgs": 0,
        "title": None,
        "cwd": None,
        "first_ts": None,
        "last_ts": None,
        "size": path.stat().st_size if path.exists() else 0,
    }
    if not path.exists():
        return info
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            info["lines"] += 1
            try:
                obj = json.loads(line)
            except Exception:
                continue
            ts = obj.get("timestamp")
            if isinstance(ts, (int, float)):
                info["first_ts"] = info["first_ts"] or int(ts)
                info["last_ts"] = int(ts)
            role = obj.get("role")
            if role in ("user", "assistant"):
                info["msgs"] += 1
            raw = extract_text(obj)
            if info["cwd"] is None and raw:
                m = re.search(r"Workspace Folder:\s*([^\r\n<]+)", raw)
                if m:
                    info["cwd"] = m.group(1).strip()
            if info["title"] is None and role == "user":
                clean = strip_reminders(raw)
                if clean:
                    info["title"] = clean[:44]
    return info


def scan_projects(home: Path) -> dict:
    """扫 projects/<slug>/*.jsonl，返回 {session_id: info}。"""
    found: dict[str, dict] = {}
    root = home / "projects"
    if not root.is_dir():
        return found
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        for f in d.glob("*.jsonl"):
            if f.name.endswith(".file-rollback.ndjson"):
                continue
            sid = f.stem
            info = read_jsonl(f)
            info["slug"] = d.name
            found[sid] = info
    return found


# ---------------------------------------------------------------- 诊断

def diagnose(home: Path, db: Path, projects: dict) -> dict:
    con = open_ro(db)
    rows = con.execute("select * from sessions").fetchall()
    users: dict[str, int] = {}
    cwds: dict[str, int] = {}
    buckets = {"alive": [], "deleted": [], "archived_like": []}
    known: set[str] = set()

    for r in rows:
        known.add(r["id"])
        users[r["user_id"]] = users.get(r["user_id"], 0) + 1
        cwds[r["cwd"]] = cwds.get(r["cwd"], 0) + 1
        item = {
            "id": r["id"],
            "title": safe_title(r),
            "cwd": r["cwd"],
            "status": r["status"],
            "deleted_at": r["deleted_at"],
            "updated": r["updated_at"],
            "has_jsonl": r["id"] in projects,
            "msgs": projects.get(r["id"], {}).get("msgs", 0),
        }
        if r["deleted_at"]:
            buckets["deleted"].append(item)
        elif r["status"] in ("Archived", "archived"):
            buckets["archived_like"].append(item)
        else:
            buckets["alive"].append(item)

    orphans = [
        {"id": sid, **info}
        for sid, info in projects.items()
        if sid not in known
    ]
    con.close()
    return {
        "db": str(db),
        "db_size": db.stat().st_size if db.exists() else 0,
        "total": len(rows),
        "users": users,
        "cwds": cwds,
        "buckets": buckets,
        "orphans": orphans,
        "project_files": len(projects),
    }


def print_report(rep: dict) -> None:
    print("=" * 68)
    print("WorkBuddy 会话诊断")
    print("=" * 68)
    print(f"数据库      : {rep['db']}  ({rep['db_size'] / 1024:.0f} KB)")
    print(f"索引会话数  : {rep['total']}")
    print(f"正文文件数  : {rep['project_files']} 个 .jsonl")
    print()

    print("【账号】数据库里出现过的 user_id：")
    for uid, n in sorted(rep["users"].items(), key=lambda x: -x[1]):
        print(f"  {uid}  ->  {n} 个会话")
    if len(rep["users"]) > 1:
        print("  ⚠ 出现多个账号，说明换过登录。旧会话可能挂在另一个账号名下。")
    print()

    print("【工作空间】会话按 cwd 分组：")
    for cwd, n in sorted(rep["cwds"].items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {cwd}")
    print()

    alive = rep["buckets"]["alive"]
    deleted = rep["buckets"]["deleted"]
    arch = rep["buckets"]["archived_like"]
    orph = rep["orphans"]

    print(f"【正常可见】{len(alive)} 个")
    for it in sorted(alive, key=lambda x: -(x["updated"] or 0))[:8]:
        flag = "" if it["has_jsonl"] else "  ⚠正文缺失"
        print(f"  {fmt_ts(it['updated'])}  {it['msgs']:4d}条  {it['title'][:34]}{flag}")
    if len(alive) > 8:
        print(f"  ... 还有 {len(alive) - 8} 个")
    print()

    print(f"【已软删除】{len(deleted)} 个（正文通常还在，可 --fix-deleted 复活）")
    for it in deleted:
        flag = "正文在" if it["has_jsonl"] else "正文已丢"
        print(f"  {fmt_ts(it['updated'])}  {it['msgs']:4d}条  {it['title'][:34]}  [{flag}]")
    print()

    if arch:
        print(f"【状态为归档】{len(arch)} 个（UI：设置 > 数据管理 > 已归档任务）")
        for it in arch:
            print(f"  {fmt_ts(it['updated'])}  {it['title'][:40]}")
        print()

    print(f"【孤立正文】{len(orph)} 个（.jsonl 在，但索引里没有 -> 可 --fix-orphan 补回）")
    for it in sorted(orph, key=lambda x: -(x["last_ts"] or 0))[:15]:
        print(
            f"  {fmt_ts(it['last_ts'])}  {it['msgs']:4d}条  "
            f"{(it['title'] or '(无标题)')[:32]}"
        )
    if len(orph) > 15:
        print(f"  ... 还有 {len(orph) - 15} 个")
    print()

    print("=" * 68)
    print("怎么读这份报告：")
    print("  · 正常可见 = 0，但孤立正文很多  -> 索引丢了，跑 --fix-orphan")
    print("  · 已软删除有内容                 -> 跑 --fix-deleted")
    print("  · 都为空、孤立正文也是 0         -> 本地数据真没了，只能靠云端/换账号找回")
    print("  · user_id 有多个                 -> 先切回原账号登录再看")
    print("=" * 68)


# ---------------------------------------------------------------- 导出

def dump_all(home: Path, projects: dict, outdir: Path) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    con = None
    db = home / "workbuddy.db"
    titles: dict[str, str] = {}
    if db.exists():
        con = open_ro(db)
        for r in con.execute("select id, title, custom_title from sessions"):
            titles[r["id"]] = safe_title(r)
        con.close()

    n = 0
    for sid, info in projects.items():
        lines = [f"# {titles.get(sid) or info['title'] or sid}", ""]
        lines.append(f"- 会话 ID：`{sid}`")
        lines.append(f"- 时间：{fmt_ts(info['first_ts'])} ~ {fmt_ts(info['last_ts'])}")
        lines.append(f"- 消息数：{info['msgs']}")
        lines.append("")
        lines.append("---")
        lines.append("")
        with open(info["path"], "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                role = obj.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = strip_reminders(extract_text(obj))
                if not text:
                    continue
                who = "你" if role == "user" else "WorkBuddy"
                lines.append(f"**{who}**（{fmt_ts(obj.get('timestamp'))}）")
                lines.append("")
                lines.append(text[:4000])
                lines.append("")
        name = re.sub(r'[\\/:*?"<>|]+', "_", (titles.get(sid) or info["title"] or sid))[:50]
        target = outdir / f"{fmt_ts(info['last_ts'])[:10]}_{name}_{sid[:8]}.md"
        target.write_text("\n".join(lines), encoding="utf-8")
        n += 1
    return n


# ---------------------------------------------------------------- 修复

def backup_db(db: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = db.with_name(f"workbuddy.db.bak-{stamp}")
    shutil.copy2(db, bak)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db) + suffix)
        if side.exists():
            shutil.copy2(side, Path(str(bak) + suffix))
    return bak


def ensure_closed(db: Path) -> bool:
    """试着拿写锁，拿不到说明 WorkBuddy 还开着。"""
    try:
        con = sqlite3.connect(str(db), timeout=3)
        con.execute("begin immediate")
        con.rollback()
        con.close()
        return True
    except sqlite3.OperationalError as exc:
        print(f"[×] 数据库被占用：{exc}")
        print("    请完全退出 WorkBuddy（含托盘图标）后重试。")
        return False


def fix_deleted(home: Path, db: Path, projects: dict) -> int:
    if not ensure_closed(db):
        return 0
    bak = backup_db(db)
    print(f"[√] 已备份数据库 -> {bak.name}")
    con = sqlite3.connect(str(db), timeout=5)
    rows = con.execute(
        "select id, title, custom_title from sessions where deleted_at is not null"
    ).fetchall()
    restored = 0
    for sid, title, custom in rows:
        if sid not in projects:
            print(f"    - 跳过 {sid[:8]}（正文已不存在，恢复也是空壳）")
            continue
        con.execute("update sessions set deleted_at = null where id = ?", (sid,))
        restored += 1
        print(f"    + {sid[:8]}  {custom or title or ''}")
    con.commit()
    con.close()
    print(f"[√] 复活 {restored} 个会话，重启 WorkBuddy 即可在列表看到。")
    return restored


def fix_orphan(home: Path, db: Path, projects: dict, known: set[str]) -> int:
    if not ensure_closed(db):
        return 0
    con = sqlite3.connect(str(db), timeout=5)
    user = con.execute(
        "select user_id from sessions group by user_id order by count(*) desc limit 1"
    ).fetchone()
    if not user:
        print("[×] sessions 表是空的，没有可参照的 user_id，无法自动补索引。")
        print("    建议先登录 WorkBuddy 建一个任务，再回来跑这一步。")
        con.close()
        return 0
    uid = user[0]
    bak = backup_db(db)
    print(f"[√] 已备份数据库 -> {bak.name}")

    added = 0
    for sid, info in projects.items():
        if sid in known:
            continue
        cwd = info.get("cwd") or ""
        if not cwd:
            print(f"    - 跳过 {sid[:8]}（读不出工作目录）")
            continue
        now = int(time.time() * 1000)
        con.execute(
            """insert or replace into sessions
               (id, cwd, user_id, title, status, created_at, updated_at,
                last_activity_at, deleted_at, is_playground)
               values (?, ?, ?, ?, 'completed', ?, ?, ?, null, 0)""",
            (
                sid,
                cwd,
                uid,
                (info.get("title") or "恢复的会话")[:200],
                info.get("first_ts") or now,
                info.get("last_ts") or now,
                info.get("last_ts") or now,
            ),
        )
        added += 1
        print(f"    + {sid[:8]}  {(info.get('title') or '')[:38]}  -> {cwd}")
    con.commit()
    con.close()
    print(f"[√] 补回 {added} 个会话索引，重启 WorkBuddy 后会在对应工作空间分组下出现。")
    return added


# ---------------------------------------------------------------- 入口

def main() -> int:
    setup_stdout()
    ap = argparse.ArgumentParser(description="WorkBuddy 会话自救工具")
    ap.add_argument("--home", help="手动指定 .workbuddy 目录（默认 %USERPROFILE%\\.workbuddy）")
    ap.add_argument("--dump", metavar="DIR", help="把所有对话正文导出为 md 文件")
    ap.add_argument("--fix-deleted", action="store_true", help="复活被软删除的会话")
    ap.add_argument("--fix-orphan", action="store_true", help="为孤立 jsonl 补回索引")
    args = ap.parse_args()

    home = workbuddy_home(args.home)
    db = home / "workbuddy.db"

    print(f"扫描目录：{home}")
    if not home.is_dir():
        print(f"[×] 找不到 {home}")
        print("    WorkBuddy 可能从未在这台机器上登录过，或者数据被清理了。")
        return 2
    if not db.exists():
        print(f"[×] 找不到 {db}")
        print("    只剩 projects 正文文件的话，可以先跑 --dump 把内容抢救成 md。")
    projects = scan_projects(home)
    print(f"发现正文文件：{len(projects)} 个")
    print()

    if args.dump:
        n = dump_all(home, projects, Path(args.dump))
        print(f"[√] 已导出 {n} 个会话到 {args.dump}")
        return 0

    if not db.exists():
        return 2

    rep = diagnose(home, db, projects)
    print_report(rep)

    if args.fix_deleted:
        print()
        fix_deleted(home, db, projects)
    if args.fix_orphan:
        known = set()
        con = open_ro(db)
        for r in con.execute("select id from sessions"):
            known.add(r["id"])
        con.close()
        print()
        fix_orphan(home, db, projects, known)

    if not args.fix_deleted and not args.fix_orphan:
        print()
        print("以上为只读诊断，没有改动任何数据。")
        print("建议顺序：先 --dump 导出一份，再 --fix-deleted / --fix-orphan。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
