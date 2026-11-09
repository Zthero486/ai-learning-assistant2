# -*- coding: utf-8 -*-
"""把已导入 materials 里的四史教材正文，按章/节切分写入 seed_data/qushi_texts.json。

思路
----
1. 从 materials 取三本简史的正文（OCR / 直传 PDF 文本）。
2. 清掉页眉页脚噪声行（书名、"第X章 xxx" 且极短的行、纯页码行）。
3. 用「归一化后的标题核心串」在正文里顺序定位每节起点，节正文 = 本节起点 → 下一节/下一章起点。
4. 目录区会被第一次命中，所以正文起点取「第一个章标题的第二次出现」。
5. 匹配失败的节点不写（前端回落显示章正文），并在报告里列出。

用法
----
    python scripts/build_qushi_texts.py            # 生成 + 打印覆盖率
    python scripts/build_qushi_texts.py --db release/data/app.db
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "backend" / "app" / "seed_data"

# 课程 → materials.id（三本官方简史）
BOOKS = {
    "reform": 49,
    "party": 48,
    "socialism": 50,
}
BOOK_TITLE = {
    "reform": "改革开放简史",
    "party": "中国共产党简史",
    "socialism": "社会主义发展简史",
}
# 正文起点标记（目录之后、正文第一段里的独有短语），用来跳过目录区
BODY_MARKER = {
    "reform": "潮涌东方",
    "party": "在几千年的历史发展中",
    "socialism": "人类关于理想社会的构想源远流长",
}
# marker 之前还要回退多少字才覆盖到章标题（socialism 的章标题离正文首句较远）
MARKER_BACK = {"reform": 400, "party": 400, "socialism": 3000}

MAX_SECTION_CHARS = 9000  # 单节正文上限，防 OCR 串页
MIN_CHARS = 40  # 章正文下限（章导语本来就短）
MIN_SECTION_CHARS = 300  # 节正文下限：太短多半是切错了，宁可留空


def norm(s: str) -> str:
    """只保留汉字与数字，用于宽松匹配（OCR 常有标点/空格错位）。"""
    return re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", s)


def clean(text: str, title: str) -> str:
    """清掉纯版式噪声行（页码、书名、带装饰符的页眉残片）。

    注意：**保留**「第X章 标题」行——章锚点定位要用它，切出正文后再逐行剔除。
    """
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        if line == "":
            lines.append("")
            continue
        bare = norm(line)
        if bare == norm(title):
            continue
        # 含版式符号（OCR 把页眉装饰读成 < / ・）的短行
        if len(line) <= 40 and re.search(r"[<>＜＞/・|]", line):
            continue
        if re.fullmatch(r"[\d\s．.·\-—|<>《》]+", line):
            continue
        lines.append(line)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


END_PUNCT = "。！？…”』」.!?"
PARA_MIN = 45


def strip_leading_title(chunk: str, title: str) -> str:
    """OCR 常把节标题和正文首句连成一段，这里把标题前缀剥掉（UI 已显示标题）。"""
    nt = norm(title)
    if not nt:
        return chunk
    i = 0
    matched = 0
    while i < len(chunk) and matched < len(nt):
        c = chunk[i]
        if norm(c) == nt[matched]:
            matched += 1
        elif norm(c):
            return chunk
        i += 1
    if matched < len(nt):
        return chunk
    rest = chunk[i:].lstrip(" \n\u3000、，,：:")
    return rest if len(rest) >= 40 else chunk


def reflow(text: str) -> str:
    """把 OCR 竖排版式的碎行重新拼回自然段。

    规则：短行（< PARA_MIN 字）视为折行，与后续内容拼接；攒够 PARA_MIN 字
    并以句末标点结尾才断段。这样竖排版式被并成整段，横排正常段落不受影响。
    """
    paras: list[str] = []
    buf = ""
    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        buf += s
        if len(buf) >= PARA_MIN and buf[-1] in END_PUNCT:
            paras.append(buf)
            buf = ""
    if buf:
        paras.append(buf)
    return "\n\n".join(paras)


HEADER_RE = re.compile(r"^第[一二三四五六七八九十]{1,2}章")


def strip_headers(chunk: str, book: str) -> str:
    """去掉正文里夹的页眉行（「第X章 标题」独立短行）和书名行。"""
    bt = norm(book)
    kept = []
    for raw in chunk.split("\n"):
        line = raw.strip()
        bare = norm(line)
        if bare == bt:
            continue
        if line and len(bare) <= 30 and HEADER_RE.match(bare) and HEADER_RE.match(line.strip()):
            continue
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


class Body:
    """带归一化索引的正文，支持从游标开始找标题。"""

    def __init__(self, text: str):
        self.text = text
        self.flat = norm(text)
        # flat 每个字符 → 原文下标，便于把命中位置映射回原文
        self.map: list[int] = []
        for i, ch in enumerate(text):
            if re.match(r"[\u4e00-\u9fa5A-Za-z0-9]", ch):
                self.map.append(i)

    def _flat_from(self, start: int) -> int:
        s = 0
        while s < len(self.map) and self.map[s] < start:
            s += 1
        return s

    def find(self, title: str, start: int = 0) -> int:
        """返回原文下标，找不到返回 -1。start 为原文下标。"""
        needle = norm(title)
        if not needle:
            return -1
        s = self._flat_from(start)
        for size in (len(needle), 10, 8, 6):
            if size > len(needle):
                continue
            part = needle[:size]
            p = self.flat.find(part, s)
            if p >= 0:
                return self.map[p]
        return -1

    def find_in(self, title: str, lo: int, hi: int) -> int:
        """在原文区间 [lo, hi) 内找标题，取最靠近 lo 的命中。"""
        needle = norm(title)
        if not needle:
            return -1
        s = self._flat_from(lo)
        best = -1
        for size in (len(needle), 10, 8, 6):
            if size > len(needle):
                continue
            p = self.flat.find(needle[:size], s)
            if p < 0:
                continue
            pos = self.map[p]
            if pos >= hi:
                continue
            if best < 0 or pos < best:
                best = pos
        return best


CN = "一二三四五六七八九十"


def split_track(track: str, text: str, nodes: list[dict]) -> tuple[dict, list[str]]:
    """返回 ({code: content}, 失败列表)。nodes 按文档顺序：章、其下各节。"""
    body = Body(text)
    title = BOOK_TITLE[track]

    # 正文起点：优先用独有标记跳过目录区，退回「第一章标题第二次出现」
    marker = BODY_MARKER.get(track)
    marker_pos = text.find(marker) if marker else -1
    if marker_pos < 0:
        first_chapter = nodes[0]["title"]
        p1 = body.find(first_chapter, 0)
        p2 = body.find(first_chapter, p1 + 1) if p1 >= 0 else -1
        marker_pos = p2 if p2 > 0 else max(p1, 0)
    start = max(0, marker_pos - MARKER_BACK.get(track, 400))

    # 切出章列表
    chapters: list[dict] = []
    for nd in nodes:
        if nd["level"] == 1:
            chapters.append({"code": nd["code"], "title": nd["title"], "sections": []})
        elif chapters:
            chapters[-1]["sections"].append({"code": nd["code"], "title": nd["title"]})

    # 每章起点：标题命中与「第N章」锚点取更靠前者；都失败则视为缺失
    ch_start: list[int] = []
    cursor = start
    for ci, ch in enumerate(chapters, 1):
        if ci == 1 and marker_pos > 0:
            back = MARKER_BACK.get(track, 400)
            p = body.find_in(ch["title"], max(0, marker_pos - back), marker_pos + 800)
            pos = p if p > 0 else marker_pos
            ch_start.append(pos)
            cursor = pos + 1
            continue
        cn = CN[ci - 1] if ci <= len(CN) else str(ci)
        p_title = body.find(ch["title"], cursor)
        p_anchor = -1
        m = re.search(f"第{cn}章", text[cursor:])
        if m:
            p_anchor = cursor + m.start()
        cands = [p for p in (p_title, p_anchor) if p > 0]
        pos = min(cands) if cands else -1
        ch_start.append(pos)
        if pos >= 0:
            cursor = pos + 1

    failed: list[str] = []
    out: dict[str, str] = {}

    def emit(code: str, lo: int, hi: int, node_title: str = "") -> None:
        if lo < 0:
            failed.append(code)
            return
        chunk = text[lo:hi].strip()
        chunk = re.sub(r"^[一二三四五六七八九十\d]+\s*[、．.，,]?\s*", "", chunk, count=1)
        chunk = strip_headers(chunk, BOOK_TITLE[track])
        if node_title:
            chunk = strip_leading_title(chunk, node_title)
        chunk = reflow(chunk)
        if len(chunk) > MAX_SECTION_CHARS:
            cut = chunk.rfind("\n", 0, MAX_SECTION_CHARS)
            chunk = chunk[: cut if cut > 0 else MAX_SECTION_CHARS]
        min_chars = MIN_SECTION_CHARS if code.count("-") >= 2 else MIN_CHARS
        if len(chunk) >= min_chars:
            out[code] = chunk
        else:
            failed.append(code)

    for i, ch in enumerate(chapters):
        lo = ch_start[i]
        hi = ch_start[i + 1] if i + 1 < len(chapters) and ch_start[i + 1] > 0 else len(text)
        if lo < 0:
            failed.append(ch["code"])
            for s in ch["sections"]:
                failed.append(s["code"])
            continue
        # 章内顺序定位各节；跨度太离谱的命中视为误匹配，丢弃且不推进游标
        sec_pos: list[int] = []
        cur = lo
        budget = max(9000, int((hi - lo) / max(1, len(ch["sections"])) * 3))
        for s in ch["sections"]:
            p = body.find_in(s["title"], cur, hi)
            if p > 0 and cur > 0 and p - cur > budget:
                p = -1
            if p < 0:
                sec_pos.append(-1)
            else:
                sec_pos.append(p)
                cur = p + 1
        # 第二遍：顺序匹配失败（OCR 掉标题 / 页序错乱）的节，独立在章内再找一次
        for j, s in enumerate(ch["sections"]):
            if sec_pos[j] > 0:
                continue
            p = body.find_in(s["title"], lo, hi)
            if p > 0:
                sec_pos[j] = p
        # 章正文 = 章起点 → 第一节起点
        first_sec = next((p for p in sec_pos if p > 0), hi)
        emit(ch["code"], lo, first_sec, ch["title"])
        for j, s in enumerate(ch["sections"]):
            s_lo = sec_pos[j]
            # 终点取「后面第一个比起始位置更大的命中」，容忍页序错乱造成的乱序
            s_hi = next((p for p in sec_pos[j + 1 :] if p > s_lo > 0), hi)
            emit(s["code"], s_lo, s_hi, s["title"])

    return out, failed


def load_nodes(conn: sqlite3.Connection, track: str) -> list[dict]:
    rows = conn.execute(
        "SELECT code, level, title, order_no, parent_code FROM syllabus_nodes "
        "WHERE track=? ORDER BY level, order_no",
        (track,),
    ).fetchall()
    chapters = [dict(r) for r in rows if r["level"] == 1]
    result: list[dict] = []
    for ch in chapters:
        result.append({"code": ch["code"], "level": 1, "title": ch["title"]})
        for r in rows:
            if r["level"] == 2 and r["parent_code"] == ch["code"]:
                result.append({"code": r["code"], "level": 2, "title": r["title"]})
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "release" / "data" / "app.db"))
    ap.add_argument("--write", action="store_true", help="写入 qushi_texts.json")
    ap.add_argument("--apply", action="store_true", help="同时 UPDATE 进 app.db（覆盖）")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    texts: dict[str, str] = {}
    for track, mid in BOOKS.items():
        row = conn.execute("SELECT title, content FROM materials WHERE id=?", (mid,)).fetchone()
        if not row:
            print(f"[skip] {track}: materials id={mid} 不存在")
            continue
        nodes = load_nodes(conn, track)
        text = clean(row["content"], BOOK_TITLE[track])
        got, failed = split_track(track, text, nodes)
        texts.update(got)
        total = len(nodes)
        chars = sum(len(v) for v in got.values())
        print(f"[{track}] {BOOK_TITLE[track]}: {len(got)}/{total} 节点切出正文，共 {chars} 字")
        if failed:
            print("   未匹配：", ", ".join(failed[:20]) + (" ..." if len(failed) > 20 else ""))
    conn.close()

    print(f"\n合计 {len(texts)} 个节点有正文，{sum(len(v) for v in texts.values())} 字")
    if args.write:
        tgt = SEED / "qushi_texts.json"
        tgt.write_text(json.dumps(texts, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已写入 {tgt} ({tgt.stat().st_size/1024:.1f} KB)")
    if args.apply:
        for dbp in (ROOT / "release" / "data" / "app.db", ROOT / "data" / "app.db"):
            if not dbp.exists():
                continue
            c2 = sqlite3.connect(dbp)
            n = 0
            for code, text in texts.items():
                cur = c2.execute(
                    "UPDATE syllabus_nodes SET content=? WHERE code=?", (text, code)
                )
                n += cur.rowcount
            c2.commit()
            c2.close()
            print(f"已写入 {dbp}（{n} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
