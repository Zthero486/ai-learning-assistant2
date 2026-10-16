"""AI 智能学习助手 v1 后端（朴素实现）。

v1 特意采用"能跑就行"的写法，作为期末课设重构阶段的对照基线：
- 路由 + 数据库 + 业务逻辑全部混在单个文件中（上帝模块）
- 配置硬编码为常量
- sqlite3 直连、SQL 内联在各个路由函数里
- 朴素关键词检索（无向量库、无 Embedding）

v2 重构方向（详见 docs/design.md）：分层架构 + 仓储模式 + 策略模式(AI 引擎)
+ Pydantic Settings 配置中心 + 向量检索 + SSE 流式输出。
"""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader

from . import ai_helper, apppaths

# ==================== v1 硬编码配置（v2 重构目标：统一配置中心） ====================
# 便携发布后 data/ 与 .env 均位于 exe 同级目录，整个文件夹拷贝即可换机运行
DB_PATH = apppaths.app_base_dir() / "data" / "app.db"
UPLOAD_DIR = apppaths.app_base_dir() / "data" / "uploads"
ALLOWED_EXT = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".md": "markdown",
    ".txt": "text",
    ".markdown": "markdown",
}
MAX_UPLOAD_MB = 20
CHUNK_SIZE = 500
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

app = FastAPI(title="AI 智能学习助手 API (v1)", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ==================== 数据库（v1：裸 sqlite3，每请求新连接） ====================
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS materials(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            course TEXT NOT NULL DEFAULT '未分类',
            filename TEXT NOT NULL,
            filetype TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS knowledge_points(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            course TEXT NOT NULL DEFAULT '未分类',
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course TEXT NOT NULL DEFAULT '未分类',
            kp_id INTEGER,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'todo',
            created_at TEXT NOT NULL,
            FOREIGN KEY(kp_id) REFERENCES knowledge_points(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS questions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kp_id INTEGER,
            type TEXT NOT NULL DEFAULT 'short_answer',
            question TEXT NOT NULL,
            answer TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL,
            FOREIGN KEY(kp_id) REFERENCES knowledge_points(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS practice_records(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            user_answer TEXT NOT NULL DEFAULT '',
            correct INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS wrong_book(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL UNIQUE,
            wrong_count INTEGER NOT NULL DEFAULT 1,
            resolved INTEGER NOT NULL DEFAULT 0,
            review_marked INTEGER NOT NULL DEFAULT 0,
            last_wrong_at TEXT NOT NULL,
            FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
        );
        """)
    conn.commit()
    conn.close()


init_db()


# ==================== 文档解析 ====================
def parse_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_file(path: Path, ext: str) -> str:
    if ext == "pdf":
        return parse_pdf(path)
    if ext == "docx":
        return parse_docx(path)
    return path.read_text(encoding="utf-8", errors="ignore")


# ==================== 业务辅助（v1：与路由混放） ====================
def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def material_chunks(material_id: int) -> list:
    conn = db()
    row = conn.execute("SELECT content FROM materials WHERE id=?", (material_id,)).fetchone()
    conn.close()
    if not row:
        return []
    return ai_helper.chunk_text(row["content"], CHUNK_SIZE)


def course_chunks(course: str) -> list:
    conn = db()
    rows = conn.execute("SELECT content FROM materials WHERE course=?", (course,)).fetchall()
    conn.close()
    chunks = []
    for r in rows:
        chunks.extend(ai_helper.chunk_text(r["content"], CHUNK_SIZE))
    return chunks


def build_context(chunks: list, limit: int = None) -> str:
    limit = limit or MAX_CONTEXT_CHARS
    parts, total = [], 0
    for c in chunks:
        if total + len(c) > limit:
            break
        parts.append(c)
        total += len(c)
    return "\n\n".join(parts)


# ==================== 资料管理 ====================
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ai_available": ai_helper.is_available(),
        "ai_base_url": ai_helper.get_base_url() if ai_helper.is_available() else None,
        "ai_model": ai_helper.get_model() if ai_helper.is_available() else None,
    }


@app.post("/api/materials/upload")
async def upload_material(file: UploadFile = File(...), course: str = Form("未分类")):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"不支持的文件类型 {ext}，仅支持 PDF/DOCX/MD/TXT")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"文件超过 {MAX_UPLOAD_MB}MB 限制")

    save_name = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / save_name
    save_path.write_bytes(raw)

    try:
        content = parse_file(save_path, ALLOWED_EXT[ext])
    except Exception as e:  # v1：解析失败直接删文件报错
        save_path.unlink(missing_ok=True)
        raise HTTPException(400, f"文件解析失败：{e}")
    if not content.strip():
        save_path.unlink(missing_ok=True)
        raise HTTPException(400, "解析结果为空，可能是扫描版 PDF（暂不支持 OCR）")

    conn = db()
    cur = conn.execute(
        "INSERT INTO materials(title,course,filename,filetype,content,created_at) VALUES(?,?,?,?,?,?)",
        (
            Path(file.filename).stem,
            course.strip() or "未分类",
            save_name,
            ALLOWED_EXT[ext],
            content,
            now(),
        ),
    )
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return {"id": mid, "title": Path(file.filename).stem, "course": course, "chars": len(content)}


@app.get("/api/materials")
def list_materials(course: str = None):
    conn = db()
    if course:
        rows = conn.execute(
            "SELECT id,title,course,filetype,created_at,length(content) AS chars FROM materials WHERE course=? ORDER BY id DESC",
            (course,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id,title,course,filetype,created_at,length(content) AS chars FROM materials ORDER BY id DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/materials/{mid}")
def get_material(mid: int):
    conn = db()
    row = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "资料不存在")
    return dict(row)


@app.delete("/api/materials/{mid}")
def delete_material(mid: int):
    conn = db()
    row = conn.execute("SELECT filename FROM materials WHERE id=?", (mid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "资料不存在")
    conn.execute("DELETE FROM materials WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    (UPLOAD_DIR / row["filename"]).unlink(missing_ok=True)
    return {"deleted": mid}


# ==================== 知识点 ====================
@app.post("/api/knowledge-points")
def create_kp(body: dict):
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "知识点标题不能为空")
    conn = db()
    cur = conn.execute(
        "INSERT INTO knowledge_points(material_id,course,title,description,created_at) VALUES(?,?,?,?,?)",
        (
            body.get("material_id"),
            body.get("course", "未分类"),
            title,
            body.get("description", ""),
            now(),
        ),
    )
    conn.commit()
    kid = cur.lastrowid
    conn.close()
    return {"id": kid}


@app.get("/api/knowledge-points")
def list_kps(course: str = None):
    conn = db()
    sql = """SELECT k.*, m.title AS material_title,
             (SELECT COUNT(*) FROM questions q WHERE q.kp_id=k.id) AS question_count
             FROM knowledge_points k LEFT JOIN materials m ON m.id=k.material_id"""
    params = ()
    if course:
        sql += " WHERE k.course=?"
        params = (course,)
    sql += " ORDER BY k.id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.put("/api/knowledge-points/{kid}")
def update_kp(kid: int, body: dict):
    conn = db()
    fields, params = [], []
    for col in ("title", "description", "course"):
        if col in body:
            fields.append(f"{col}=?")
            params.append(body[col])
    if not fields:
        conn.close()
        raise HTTPException(400, "没有可更新字段")
    params.append(kid)
    conn.execute(f"UPDATE knowledge_points SET {','.join(fields)} WHERE id=?", params)
    conn.commit()
    conn.close()
    return {"updated": kid}


@app.delete("/api/knowledge-points/{kid}")
def delete_kp(kid: int):
    conn = db()
    conn.execute("DELETE FROM knowledge_points WHERE id=?", (kid,))
    conn.commit()
    conn.close()
    return {"deleted": kid}


# ==================== 学习任务 ====================
@app.post("/api/tasks")
def create_task(body: dict):
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "任务标题不能为空")
    due = body.get("due_date") or None
    if due:
        try:
            datetime.fromisoformat(due)
        except ValueError:
            raise HTTPException(400, "due_date 需为 ISO 日期格式")
    conn = db()
    cur = conn.execute(
        "INSERT INTO tasks(course,kp_id,title,description,due_date,status,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            body.get("course", "未分类"),
            body.get("kp_id"),
            title,
            body.get("description", ""),
            due,
            "todo",
            now(),
        ),
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return {"id": tid}


@app.get("/api/tasks")
def list_tasks():
    conn = db()
    rows = conn.execute(
        """SELECT t.*, k.title AS kp_title,
           CASE WHEN t.due_date IS NOT NULL AND t.status!='done' AND date(t.due_date)<date('now','localtime')
                THEN 1 ELSE 0 END AS overdue
           FROM tasks t LEFT JOIN knowledge_points k ON k.id=t.kp_id ORDER BY t.id DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.patch("/api/tasks/{tid}/status")
def set_task_status(tid: int, body: dict):
    status = body.get("status")
    if status not in ("todo", "doing", "done"):
        raise HTTPException(400, "status 只能是 todo/doing/done")
    conn = db()
    cur = conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, tid))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    if not changed:
        raise HTTPException(404, "任务不存在")
    return {"updated": tid, "status": status}


@app.delete("/api/tasks/{tid}")
def delete_task(tid: int):
    conn = db()
    conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    return {"deleted": tid}


# ==================== 练习与错题 ====================
@app.post("/api/questions/generate")
def generate_questions(body: dict):
    """用 AI（或规则引擎降级）从知识点关联资料生成练习题。"""
    kid = body.get("kp_id")
    num = min(int(body.get("num", 5)), 10)
    conn = db()
    kp = conn.execute("SELECT * FROM knowledge_points WHERE id=?", (kid,)).fetchone()
    if not kp:
        conn.close()
        raise HTTPException(404, "知识点不存在")
    content = ""
    if kp["material_id"]:
        row = conn.execute(
            "SELECT content FROM materials WHERE id=?", (kp["material_id"],)
        ).fetchone()
        content = row["content"] if row else ""
    conn.close()

    if ai_helper.is_available() and content:
        try:
            raw = ai_helper.call_llm(
                "你是出题助手。根据给定资料出简答题，只输出 JSON 数组，"
                '每项 {"type":"short_answer","question":"...","answer":"..."}，'
                f"共 {num} 题，题目必须能从资料中找到答案。",
                f"知识点：{kp['title']}\n资料：\n{build_context(ai_helper.chunk_text(content, CHUNK_SIZE))}",
            )
            questions = ai_helper.parse_questions_json(raw)
        except Exception:
            questions = []
        source = "ai"
    else:
        questions = []
        source = "fallback"

    if not questions:
        questions = ai_helper.fallback_questions(kp["title"], content or kp["title"], num)
        source = "fallback"

    conn = db()
    ids = []
    for q in questions[:num]:
        cur = conn.execute(
            "INSERT INTO questions(kp_id,type,question,answer,source,created_at) VALUES(?,?,?,?,?,?)",
            (kid, q["type"], q["question"], q["answer"], source, now()),
        )
        ids.append(cur.lastrowid)
    conn.commit()
    conn.close()
    return {"generated": len(ids), "source": source}


@app.get("/api/questions")
def list_questions(kp_id: int = None):
    conn = db()
    sql = """SELECT q.*, k.title AS kp_title FROM questions q
             LEFT JOIN knowledge_points k ON k.id=q.kp_id"""
    params = ()
    if kp_id:
        sql += " WHERE q.kp_id=?"
        params = (kp_id,)
    sql += " ORDER BY q.id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/practice/submit")
def submit_practice(body: dict):
    qid = body.get("question_id")
    correct = 1 if body.get("correct") else 0
    answer = body.get("answer", "")
    conn = db()
    q = conn.execute("SELECT id FROM questions WHERE id=?", (qid,)).fetchone()
    if not q:
        conn.close()
        raise HTTPException(404, "题目不存在")
    conn.execute(
        "INSERT INTO practice_records(question_id,user_answer,correct,created_at) VALUES(?,?,?,?)",
        (qid, answer, correct, now()),
    )
    if not correct:
        conn.execute(
            """INSERT INTO wrong_book(question_id,wrong_count,last_wrong_at) VALUES(?,?,?)
               ON CONFLICT(question_id) DO UPDATE SET wrong_count=wrong_count+1,
               resolved=0, last_wrong_at=excluded.last_wrong_at""",
            (qid, 1, now()),
        )
    conn.commit()
    conn.close()
    return {"recorded": True, "correct": bool(correct)}


@app.get("/api/wrong-book")
def wrong_book(only_unresolved: bool = True):
    conn = db()
    sql = """SELECT w.*, q.question, q.answer, q.kp_id, k.title AS kp_title,
             (SELECT COUNT(*) FROM practice_records pr WHERE pr.question_id=q.id) AS attempts
             FROM wrong_book w JOIN questions q ON q.id=w.question_id
             LEFT JOIN knowledge_points k ON k.id=q.kp_id"""
    if only_unresolved:
        sql += " WHERE w.resolved=0"
    sql += " ORDER BY w.last_wrong_at DESC"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.patch("/api/wrong-book/{wid}")
def update_wrong(wid: int, body: dict):
    conn = db()
    fields, params = [], []
    if "resolved" in body:
        fields.append("resolved=?")
        params.append(1 if body["resolved"] else 0)
    if "review_marked" in body:
        fields.append("review_marked=?")
        params.append(1 if body["review_marked"] else 0)
    if not fields:
        conn.close()
        raise HTTPException(400, "没有可更新字段")
    params.append(wid)
    cur = conn.execute(f"UPDATE wrong_book SET {','.join(fields)} WHERE id=?", params)
    conn.commit()
    changed = cur.rowcount
    conn.close()
    if not changed:
        raise HTTPException(404, "错题记录不存在")
    return {"updated": wid}


# ==================== 统计 ====================
@app.get("/api/stats/overview")
def stats_overview():
    conn = db()
    per_kp = conn.execute("""SELECT k.id, k.title, k.course,
           COUNT(DISTINCT q.id) AS question_count,
           COUNT(pr.id) AS attempts,
           SUM(pr.correct) AS correct_count
           FROM knowledge_points k
           LEFT JOIN questions q ON q.kp_id=k.id
           LEFT JOIN practice_records pr ON pr.question_id=q.id
           GROUP BY k.id ORDER BY k.id""").fetchall()
    totals = conn.execute("""SELECT (SELECT COUNT(*) FROM materials) AS materials,
           (SELECT COUNT(*) FROM knowledge_points) AS kps,
           (SELECT COUNT(*) FROM tasks WHERE status!='done') AS open_tasks,
           (SELECT COUNT(*) FROM practice_records) AS attempts,
           (SELECT COUNT(*) FROM wrong_book WHERE resolved=0) AS unresolved_wrong""").fetchone()
    conn.close()

    result = []
    for r in per_kp:
        attempts, correct = r["attempts"] or 0, r["correct_count"] or 0
        acc = round(correct / attempts * 100, 1) if attempts else None
        # v1 薄弱点判定：做过题且正确率 < 60% 即标记为薄弱
        result.append(
            {
                "kp_id": r["id"],
                "title": r["title"],
                "course": r["course"],
                "attempts": attempts,
                "accuracy": acc,
                "weak": attempts >= 2 and acc is not None and acc < 60,
            }
        )
    return {"totals": dict(totals), "per_kp": result}


# ==================== AI 辅助 ====================
@app.get("/api/config/ai")
def get_ai_config():
    """查看当前 AI 配置（key 脱敏）与可选平台预设。"""
    snapshot = ai_helper.config_snapshot()
    snapshot["presets"] = ai_helper.PROVIDER_PRESETS
    return snapshot


@app.post("/api/config/ai")
def set_ai_config(body: dict):
    """在软件内配置 AI：写回 exe 同级的 .env 并即时生效，无需重启。"""
    api_key = (body.get("api_key") or "").strip()
    base_url = (body.get("base_url") or ai_helper.DEFAULT_BASE_URL).strip().rstrip("/")
    model = (body.get("model") or ai_helper.DEFAULT_MODEL).strip()

    if api_key and len(api_key) < 8:
        raise HTTPException(400, "API Key 看起来不完整（长度过短），请检查是否复制齐全")
    if not base_url.startswith("http"):
        raise HTTPException(400, "接口地址必须以 http 开头")

    try:
        ai_helper.write_env_config(api_key, base_url, model)
    except OSError as e:
        raise HTTPException(500, f"配置写入失败：{e}（请确认程序所在目录可写）")

    ai_helper.apply_runtime_config(api_key, base_url, model)
    return {
        "saved": True,
        "configured": bool(api_key),
        "env_path": str(apppaths.env_file()),
        "message": "配置已保存并生效，可直接点击「检测 AI 连接」验证",
    }


@app.post("/api/ai/test")
def ai_test():
    """AI 连通性自检：验证 .env 中的 key / 地址 / 模型三项配置是否可用。"""
    return ai_helper.test_connection()


@app.post("/api/ai/summarize")
def ai_summarize(body: dict):
    mid = body.get("material_id")
    conn = db()
    row = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "资料不存在")
    if ai_helper.is_available():
        chunks = ai_helper.chunk_text(row["content"], CHUNK_SIZE)
        try:
            text = ai_helper.call_llm(
                "你是学习助手。请用中文对以下课程资料做结构化总结："
                "先给 3~5 条要点，再给一段 100 字以内的概览。基于资料本身，不要编造。",
                build_context(chunks),
            )
            return {"mode": "ai", "summary": text}
        except httpx.HTTPError as e:
            return JSONResponse(status_code=502, content={"detail": f"AI 接口调用失败：{e}"})
    return {"mode": "fallback", "summary": ai_helper.fallback_summary(row["content"])}


@app.post("/api/ai/ask")
def ai_ask(body: dict):
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "问题不能为空")
    material_id = body.get("material_id")
    chunks = material_chunks(material_id) if material_id else []
    if not chunks:
        chunks = course_chunks(body.get("course", "未分类"))
    if not chunks:
        # 全库兜底检索
        conn = db()
        rows = conn.execute("SELECT content FROM materials").fetchall()
        conn.close()
        chunks = ai_helper.chunk_text("\n".join(r["content"] for r in rows), CHUNK_SIZE)

    if ai_helper.is_available():
        context = build_context(ai_helper.search_chunks(question, chunks, top_k=5) or chunks)
        try:
            text = ai_helper.call_llm(
                "你是学习助手。仅依据下面提供的课程资料片段回答问题；"
                "资料中没有依据时明确说明无法从资料中得出。用中文回答，条理清晰。\n\n"
                f"资料片段：\n{context}",
                f"问题：{question}",
            )
            return {"mode": "ai", "answer": text}
        except httpx.HTTPError as e:
            return JSONResponse(status_code=502, content={"detail": f"AI 接口调用失败：{e}"})
    return {"mode": "fallback", "answer": ai_helper.fallback_answer(question, chunks)}


@app.post("/api/ai/weak-analysis")
def ai_weak_analysis(body: dict):
    course = body.get("course")
    overview = stats_overview()
    weak_kps = [
        k for k in overview["per_kp"] if k["weak"] and (not course or k["course"] == course)
    ]
    if not weak_kps:
        return {
            "mode": "stats",
            "weak_kps": [],
            "advice": "当前没有检测到正确率低于 60% 的薄弱知识点（做过至少 2 题）。",
        }

    weak_titles = "、".join(k["title"] for k in weak_kps)
    if ai_helper.is_available():
        chunks = course_chunks(course or "未分类") or course_chunks(weak_kps[0]["course"])
        try:
            text = ai_helper.call_llm(
                "你是学习教练。学生以下知识点练习正确率低于 60%，请结合课程资料给出："
                "1) 每个薄弱点可能的成因；2) 针对性的复习建议与练习计划（列出具体步骤）。",
                f"薄弱知识点：{weak_titles}\n\n课程资料片段：\n{build_context(chunks) if chunks else '（无资料）'}",
            )
            return {"mode": "ai", "weak_kps": weak_kps, "advice": text}
        except httpx.HTTPError as e:
            return JSONResponse(status_code=502, content={"detail": f"AI 接口调用失败：{e}"})

    lines = [
        "【规则引擎分析（未配置 AI，模式：统计）】",
        f"检测到薄弱知识点：{weak_titles}",
        "建议：优先重做这些知识点的错题，再针对关联资料复习后完成一轮新练习。",
    ]
    return {"mode": "fallback", "weak_kps": weak_kps, "advice": "\n".join(lines)}


@app.get("/api/tasks/due-soon")
def due_soon(days: int = 3):
    """近 N 天到期的未完成任务（供看板提醒）。"""
    deadline = (datetime.now() + timedelta(days=days)).date().isoformat()
    conn = db()
    rows = conn.execute(
        """SELECT * FROM tasks WHERE status!='done' AND due_date IS NOT NULL
           AND date(due_date)<=date(?) ORDER BY due_date""",
        (deadline,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 静态资源托管（便携发布用） ====================
# 存在前端构建产物时，由后端直接托管页面，实现"双击 exe 即用、无需 Node"。
# 开发态没有 frontend/dist 时自动跳过，仍走 Vite 开发服务器（5173）。
_frontend = apppaths.frontend_dist()
if _frontend is not None:
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
