# -*- coding: utf-8 -*-
"""扫描版教材 PDF → Windows 内置 OCR（WinRT，zh-Hans）→ 写入 materials 表。

背景：三本四史简史里改革开放、社会主义发展两本是无文字层的扫描件，
pypdf/pymupdf 都提不出一个字。这里用 pymupdf 渲染 + Windows.Media.Ocr，
单页约 0.3s（rapidocr 要 4.5s 且已吃满多核），731 页几分钟跑完。

用法：
    python scripts/ocr_textbook.py --pdf "G:/google_download/课件/xxx.pdf" \
        --course reform --title "改革开放简史（2021版）" --out G:/wbdata/cache/ocr_reform.txt
"""
import argparse
import asyncio
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import pymupdf
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapDecoder
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

RELEASE_DB = Path(__file__).resolve().parent.parent / "release" / "data" / "app.db"

CJK = r"\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"
# WinRT 会在每个「词」之间塞空格；中文场景要把汉字/中文标点之间的空格吃掉
CJK_GAP = re.compile(rf"(?<=[{CJK}])\s+(?=[{CJK}])")
# 行首是章节标记时另起一段
HEAD = re.compile(r"^(第[一二三四五六七八九十百]+[章节目部]|[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\d+\s*[.、])")
PAGE_NO = re.compile(r"^[\s\-—–·]*\d{1,4}[\s\-—–·]*$")


def clean_line(s: str) -> str:
    s = s.replace("\u00a0", " ").strip()
    s = CJK_GAP.sub("", s)
    # 标点前多余空格
    s = re.sub(rf"\s+([，。、；：？！）》”’])", r"\1", s)
    s = re.sub(rf"([（《“‘])\s+", r"\1", s)
    return s.strip()


def assemble(lines) -> str:
    """把 OCR 行拼成段落：句末标点断段，章节标题单独成段，页码丢弃。"""
    paras, buf = [], []

    def flush():
        if buf:
            t = "".join(buf).strip()
            if t:
                paras.append(t)
            buf.clear()

    for raw in lines:
        s = clean_line(raw)
        if not s or PAGE_NO.match(s):
            continue
        if HEAD.match(s):
            flush()
            paras.append(s)
            continue
        buf.append(s)
        if re.search(r"[。！？…”』」]$", s):
            flush()
    flush()
    return "\n\n".join(paras)


def make_engine():
    for tag in ("zh-Hans-CN", "zh-Hans", "zh-CN"):
        try:
            e = OcrEngine.try_create_from_language(Language(tag))
            if e:
                return e
        except Exception:
            pass
    return OcrEngine.try_create_from_user_profile_languages()


async def _png_to_bitmap(png: bytes):
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(png)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    return await decoder.get_software_bitmap_async()


def ocr_page(engine, loop, png: bytes) -> str:
    bmp = loop.run_until_complete(_png_to_bitmap(png))
    res = loop.run_until_complete(engine.recognize_async(bmp))
    return "\n".join(l.text for l in res.lines)


def log(*a):
    print(*a, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--course", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--db", default=str(RELEASE_DB))
    ap.add_argument("--out", default="")
    ap.add_argument("--pages", default="", help="只跑部分页，如 40,41 或 40-45")
    args = ap.parse_args()

    engine = make_engine()
    if not engine:
        log("没有可用的 Windows OCR 引擎（缺中文 OCR 语言包）")
        return 2
    log("OCR 引擎:", engine.recognizer_language.language_tag)

    doc = pymupdf.open(args.pdf)
    n = doc.page_count
    idx = list(range(n))
    if args.pages:
        if "-" in args.pages and "," not in args.pages:
            a, b = args.pages.split("-")
            idx = list(range(int(a), int(b) + 1))
        else:
            idx = [int(x) for x in args.pages.split(",")]
    log(f"共 {n} 页，本次处理 {len(idx)} 页，dpi={args.dpi}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    texts = []
    t0 = time.time()
    for k, i in enumerate(idx, 1):
        png = doc[i].get_pixmap(dpi=args.dpi).tobytes("png")
        try:
            txt = ocr_page(engine, loop, png)
        except Exception as e:
            log(f"  p{i} OCR 失败: {e}")
            txt = ""
        texts.append((i, txt))
        if k % 25 == 0 or k == len(idx):
            el = time.time() - t0
            log(f"  {k}/{len(idx)} 页  {el:.0f}s  均 {el/k:.2f}s/页")
    doc.close()

    body = "\n\n".join(assemble(t.split("\n")) for _, t in texts if t.strip())
    log(f"OCR 完成：{len(body)} 字（{time.time()-t0:.0f}s）")
    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        log("纯文本已写出", args.out)

    if args.pages:
        log("（--pages 只做了抽样，不写库）")
        return 0
    if not body.strip():
        log("结果为空，放弃写库")
        return 1

    conn = sqlite3.connect(args.db, timeout=15)
    conn.execute("PRAGMA busy_timeout=15000")
    exist = conn.execute("SELECT id, length(content) FROM materials WHERE title=?", (args.title,)).fetchone()
    if exist:
        conn.execute("UPDATE materials SET content=?, course=?, filetype='pdf' WHERE id=?",
                     (body, args.course, exist[0]))
        conn.commit()
        log(f"已更新 id={exist[0]}：{exist[1]} 字 → {len(body)} 字，course={args.course}")
    else:
        cur = conn.execute(
            "INSERT INTO materials(user_id,uuid,title,course,filename,filetype,content,node_code,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (1, uuid.uuid4().hex, args.title, args.course, os.path.basename(args.pdf),
             "pdf_ocr", body, "", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        log(f"已写入 id={cur.lastrowid}：{len(body)} 字，course={args.course}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
