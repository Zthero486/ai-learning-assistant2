# -*- coding: utf-8 -*-
"""给演示库灌四史示例数据（演示账号学「党史」）。

只动 release/data/app.db：
1. 清掉旧的「中学历史」演示内容（node_code 为空 / course 不属于四史）；
2. 把 demo 账号设成学「党史」，灌入内置关键事件（含扩充包）；
3. 挂内置知识点（带思政课考法标记），每条配一道样例题；
4. 灌入内置四史史料，供「史料总结 / 史料答疑」演示。

内置内容统一放在 backend/app/seed_data/qushi_content.json，
随 exe 一起打包（--add-data），本脚本只是把它落进演示库。

幂等：同名知识点/题目/史料已存在则跳过。
"""

import json
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import qushi  # noqa: E402

DB = ROOT / "release" / "data" / "app.db"
TRACK_NAMES = tuple(t["name"] for t in qushi.tracks())


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_columns(conn: sqlite3.Connection) -> None:
    """演示库可能还是旧结构：这里做一遍与 main.migrate_qushi 等价的幂等补列。"""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS syllabus_nodes(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               code TEXT NOT NULL UNIQUE,
               track TEXT NOT NULL,
               level INTEGER NOT NULL,
               parent_code TEXT NOT NULL DEFAULT '',
               title TEXT NOT NULL,
               period TEXT NOT NULL DEFAULT '',
               order_no INTEGER NOT NULL DEFAULT 0)"""
    )
    plan = (
        ("users", "track", "TEXT NOT NULL DEFAULT ''"),
        ("knowledge_points", "node_code", "TEXT NOT NULL DEFAULT ''"),
        ("knowledge_points", "exam_type", "TEXT NOT NULL DEFAULT ''"),
        ("questions", "exam_type", "TEXT NOT NULL DEFAULT ''"),
        ("events", "kind", "TEXT NOT NULL DEFAULT 'event'"),
        ("events", "node_code", "TEXT NOT NULL DEFAULT ''"),
        ("wrong_book", "next_review_at", "TEXT NOT NULL DEFAULT ''"),
        ("wrong_book", "error_type", "TEXT NOT NULL DEFAULT ''"),
    )
    for table, col, decl in plan:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if cols and col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    conn.commit()


def purge_legacy(conn: sqlite3.Connection) -> list:
    """删掉旧的中学历史演示内容（node_code 为空 / course 不属于四史）。

    先从叶子表删起，避免留下指向已删题目/知识点的做题记录与错题。
    """
    log = []
    q_sub = ("SELECT q.id FROM questions q JOIN knowledge_points k ON k.id = q.kp_id "
             "WHERE COALESCE(k.node_code,'')=''")
    n = conn.execute(f"DELETE FROM practice_records WHERE question_id IN ({q_sub})").rowcount
    log.append(f"  清练习记录 {n}")
    n = conn.execute(f"DELETE FROM wrong_book WHERE question_id IN ({q_sub})").rowcount
    log.append(f"  清错题 {n}")
    n = conn.execute(f"DELETE FROM questions WHERE id IN ({q_sub})").rowcount
    log.append(f"  清题目 {n}")
    n = conn.execute("DELETE FROM knowledge_points WHERE COALESCE(node_code,'')=''").rowcount
    log.append(f"  清知识点 {n}")
    n = conn.execute("DELETE FROM events WHERE COALESCE(node_code,'')=''").rowcount
    log.append(f"  清旧事件 {n}")
    marks = ",".join("?" * len(TRACK_NAMES))
    n = conn.execute(f"DELETE FROM materials WHERE course NOT IN ({marks})", TRACK_NAMES).rowcount
    log.append(f"  清旧史料 {n}")
    n = conn.execute(
        "DELETE FROM tasks WHERE kp_id IS NOT NULL AND kp_id NOT IN (SELECT id FROM knowledge_points)"
    ).rowcount
    log.append(f"  清孤立任务 {n}")
    n = conn.execute(
        f"DELETE FROM tasks WHERE COALESCE(course,'') NOT IN ({marks})", TRACK_NAMES
    ).rowcount
    log.append(f"  清旧任务 {n}")
    conn.commit()
    return log


def resolve_node(conn: sqlite3.Connection, code: str) -> str:
    """知识点挂靠码校验：节码无效时退回章码，章码也无效则返回空串。"""
    if not code:
        return ""
    if conn.execute("SELECT 1 FROM syllabus_nodes WHERE code=?", (code,)).fetchone():
        return code
    chapter = code.rsplit("-", 1)[0]
    if chapter != code and conn.execute(
        "SELECT 1 FROM syllabus_nodes WHERE code=?", (chapter,)
    ).fetchone():
        return chapter
    return ""


def seed_pdf_materials(conn: sqlite3.Connection) -> int:
    """把内置 PDF 史料按「用户上传」同款管线入库：

    原件复制到 release/data/uploads/<uuid>.pdf，pypdf 提取正文，filetype=pdf。
    这样史料列表里就是真正的 PDF 文件，AI 引用的是提取出的全文。
    """
    from pypdf import PdfReader

    pdf_dir = ROOT / "backend" / "app" / "seed_data" / "pdfs"
    manifest_path = pdf_dir / "manifest.json"
    if not manifest_path.exists():
        return 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    uploads = ROOT / "release" / "data" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    track_names = qushi.track_map()
    added = 0
    for m in manifest:
        src = pdf_dir / m["file"]
        if not src.exists():
            continue
        have = conn.execute(
            "SELECT 1 FROM materials WHERE user_id=1 AND title=?", (m["title"],)
        ).fetchone()
        if have:
            continue
        save_name = uuid.uuid4().hex + ".pdf"
        shutil.copy2(src, uploads / save_name)
        try:
            reader = PdfReader(str(uploads / save_name))
            text = "\n".join((p.extract_text() or "").strip() for p in reader.pages)
        except Exception as e:
            (uploads / save_name).unlink(missing_ok=True)
            print(f"  [skip] {m['file']} 解析失败：{e}")
            continue
        if len(text.strip()) < 500:
            (uploads / save_name).unlink(missing_ok=True)
            print(f"  [skip] {m['file']} 提取正文过短")
            continue
        name = track_names.get(m["track"], {}).get("name", m["track"])
        conn.execute(
            "INSERT INTO materials(user_id,uuid,title,course,filename,filetype,content,created_at)"
            " VALUES(1,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, m["title"], name, save_name, "pdf", text.strip(), now()),
        )
        added += 1
    conn.commit()
    return added


def seed_materials(conn: sqlite3.Connection) -> int:
    added = 0
    for m in qushi.builtin_materials():
        name = qushi.track_map().get(m["track"], {}).get("name", m["track"])
        have = conn.execute(
            "SELECT 1 FROM materials WHERE user_id=1 AND title=?", (m["title"],)
        ).fetchone()
        if have:
            continue
        conn.execute(
            "INSERT INTO materials(user_id,uuid,title,course,filename,filetype,content,created_at)"
            " VALUES(1,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, m["title"], name, m["title"][:40] + ".txt", "txt",
             m["content"], now()),
        )
        added += 1
    conn.commit()
    return added


def seed_kps(conn: sqlite3.Connection) -> tuple:
    kp_added = q_added = skipped = 0
    for k in qushi.builtin_kps():
        code = resolve_node(conn, k["node_code"])
        if not code:
            skipped += 1
            continue
        track = code.split("-", 1)[0]
        name = qushi.track_map().get(track, {}).get("name", track)
        row = conn.execute(
            "SELECT id FROM knowledge_points WHERE user_id=1 AND title=?", (k["title"],)
        ).fetchone()
        if row:
            kid = row["id"]
        else:
            cur = conn.execute(
                "INSERT INTO knowledge_points(user_id,uuid,course,title,description,"
                "node_code,exam_type,created_at) VALUES(1,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, name, k["title"], k.get("description", ""),
                 code, k.get("exam_type", ""), now()),
            )
            kid = cur.lastrowid
            kp_added += 1
        q = k.get("question") or {}
        if not q.get("q"):
            continue
        have = conn.execute(
            "SELECT 1 FROM questions WHERE user_id=1 AND kp_id=? AND question=?", (kid, q["q"])
        ).fetchone()
        if not have:
            conn.execute(
                "INSERT INTO questions(user_id,uuid,kp_id,type,question,answer,source,exam_type,created_at)"
                " VALUES(1,?,?,?,?,?,'manual',?,?)",
                (uuid.uuid4().hex, kid, q.get("type", "简答"), q["q"], q.get("a", ""),
                 k.get("exam_type", ""), now()),
            )
            q_added += 1
    conn.commit()
    return kp_added, q_added, skipped


def seed_practice(conn: sqlite3.Connection) -> int:
    """造一组成绩记录，让「学习统计」有曲线；已有记录则跳过。"""
    have = conn.execute("SELECT COUNT(*) FROM practice_records WHERE user_id=1").fetchone()[0]
    if have:
        return 0
    qids = [r[0] for r in conn.execute(
        "SELECT q.id FROM questions q JOIN knowledge_points k ON k.id=q.kp_id "
        "WHERE q.user_id=1 AND k.node_code LIKE 'party-%' ORDER BY q.id"
    )]
    if not qids:
        return 0
    added = 0
    for i, qid in enumerate(qids[:20]):
        day = 7 - min(i // 3, 7)
        ts = (datetime.now() - timedelta(days=day, hours=2)).isoformat(timespec="seconds")
        correct = 1 if i % 4 else 0
        conn.execute(
            "INSERT INTO practice_records(user_id,question_id,user_answer,correct,created_at,uuid)"
            " VALUES(1,?,?,?,?,?)",
            (qid, "已作答" if correct else "", correct, ts, uuid.uuid4().hex),
        )
        added += 1
    conn.commit()
    return added


def seed_tasks(conn: sqlite3.Connection) -> int:
    """三个四史复习任务，演示「复习任务」页。已有任务则跳过。"""
    if conn.execute("SELECT COUNT(*) FROM tasks WHERE user_id=1").fetchone()[0]:
        return 0
    plan = [
        ("党史", "复习：遵义会议与长征的胜利",
         "把「生死攸关的转折点」讲清楚：背景（第五次反围剿失败）→ 会议内容 → 意义三层。", 2),
        ("党史", "复习：十一届三中全会",
         "思想路线、工作重心、改革开放决策三条线各写一句，注意与南方谈话的承接关系。", 4),
        ("党史", "整理：中国式现代化的答题素材",
         "五个特征各配一个史实例证（脱贫攻坚/生态文明建设/一带一路），用于材料分析题。", 7),
    ]
    added = 0
    for course, title, desc, days in plan:
        conn.execute(
            "INSERT INTO tasks(user_id,course,kp_id,title,description,due_date,status,created_at,uuid)"
            " VALUES(1,?,NULL,?,?,?,'todo',?,?)",
            (course, title, desc,
             (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d"),
             now(), uuid.uuid4().hex),
        )
        added += 1
    conn.commit()
    return added


def seed_wrong_book(conn: sqlite3.Connection) -> int:
    """挑三道题造错题样本，让「错题本 / 复习计划」有内容可演示。"""
    qids = [r[0] for r in conn.execute(
        "SELECT q.id FROM questions q JOIN knowledge_points k ON k.id=q.kp_id "
        "WHERE q.user_id=1 AND k.node_code LIKE 'party-%' ORDER BY q.id DESC LIMIT 3"
    )]
    made = 0
    for qid in qids:
        have = conn.execute(
            "SELECT 1 FROM wrong_book WHERE user_id=1 AND question_id=?", (qid,)
        ).fetchone()
        if have:
            continue
        conn.execute(
            "INSERT INTO wrong_book(user_id,question_id,wrong_count,resolved,review_marked,"
            "last_wrong_at,uuid,correct_streak,next_review_at,error_type) VALUES(1,?,?,0,0,?,?,0,?,?)",
            (qid, 2, now(), uuid.uuid4().hex,
             (datetime.now() + timedelta(days=1)).isoformat(timespec="seconds"), "concept"),
        )
        made += 1
    conn.commit()
    return made


def main() -> int:
    if not DB.exists():
        print(f"找不到演示库：{DB}")
        return 1
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    log = []

    ensure_columns(conn)
    added_nodes = qushi.ensure_syllabus(conn)
    log.append(f"syllabus_nodes 新增 {added_nodes}")

    conn.execute("UPDATE users SET track='party' WHERE id=1")
    log.append("demo(id=1) -> track=party")

    log.append("清理旧中学历史演示内容：")
    log.extend(purge_legacy(conn))

    seeded = qushi.seed_track_events(conn, 1, "party", now())
    log.append(f"党史内置事件新增 {seeded}")

    kp_added, q_added, skipped = seed_kps(conn)
    log.append(f"知识点新增 {kp_added}，题目新增 {q_added}，节点无效跳过 {skipped}")

    log.append(f"内置史料新增 {seed_materials(conn)}")
    log.append(f"PDF 史料新增 {seed_pdf_materials(conn)}")
    log.append(f"错题样本新增 {seed_wrong_book(conn)}")
    log.append(f"做题记录新增 {seed_practice(conn)}")
    log.append(f"复习任务新增 {seed_tasks(conn)}")

    for table in ("syllabus_nodes", "materials", "knowledge_points", "questions",
                  "events", "wrong_book", "practice_records", "tasks"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        log.append(f"  {table}: {n}")
    conn.execute("VACUUM")
    conn.close()

    out = ROOT / "_tmp" / "seed_demo_report.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(log), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
