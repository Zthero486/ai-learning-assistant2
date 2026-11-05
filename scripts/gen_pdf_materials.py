# -*- coding: utf-8 -*-
"""抓取官方文件网页全文，排版生成 PDF，作为内置史料（filetype=pdf）。

产物：backend/app/seed_data/pdfs/<文件名>.pdf + pdfs_manifest.json
seed_demo_qushi.py 会把 manifest 里的 PDF 复制进 release/data/uploads 并
按应用的解析管线提取正文入库（与用户手动上传 PDF 完全同构）。

说明：gov.cn 等官方渠道只发布网页版全文、不提供 PDF 直链，因此这里抓取
官方全文后本地排版生成 PDF；每页页脚注明来源网址与生成日期。
可重复执行：抓取失败自动跳过，已生成的 PDF 不会重做。
"""

import datetime
import html as htmllib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "backend" / "app" / "seed_data" / "pdfs"
LOG = ROOT / "_tmp" / "gen_pdf.log"
out = open(LOG, "w", encoding="utf-8", buffering=1)


def w(*a):
    out.write(" ".join(str(x) for x in a) + "\n")
    out.flush()


SOURCES = [
    {
        "file": "百年奋斗重大成就和历史经验的决议_全文.pdf",
        "title": "《中共中央关于党的百年奋斗重大成就和历史经验的决议》（全文）",
        "track": "party",
        "urls": ["https://www.gov.cn/zhengce/2021-11/16/content_5651269.htm"],
        "start": "中国共产党第十九届中央委员会第六次全体会议",
        "end": "（新华社北京11月16日电",
    },
    {
        "file": "二十大报告_全文.pdf",
        "title": "《高举中国特色社会主义伟大旗帜 为全面建设社会主义现代化国家而团结奋斗——在中国共产党第二十次全国代表大会上的报告》（全文）",
        "track": "party",
        "urls": ["https://www.gov.cn/xinwen/2022-10/25/content_5721685.htm"],
        "start": "同志们：",
        "end": "（新华社北京10月25日电",
    },
    {
        "file": "人类减贫的中国实践_白皮书全文.pdf",
        "title": "《人类减贫的中国实践》白皮书（全文）",
        "track": "prc",
        "urls": [
            "https://www.xinhuanet.com/politics/2021-04/06/c_1127295868.htm",
            "https://focus.scol.com.cn/zgsz/202104/58109862.html",
            "https://big5.humanrights.cn/2021/04/06/410f4c84185b44b5b046908a6f30a63a.html",
        ],
        "start": "人类减贫的中国实践",
        "end": "（完）",
    },
    {
        "file": "中国的全面小康_白皮书全文.pdf",
        "title": "《中国的全面小康》白皮书（全文）",
        "track": "prc",
        "urls": [
            "https://www.gov.cn/zhengce/2021-09/28/content_5639778.htm",
            "http://dangshi.people.cn/n1/2021/0928/c436975-32240875.html",
        ],
        "start": "中国的全面小康",
        "end": "（新华社北京9月28日电",
    },
    {
        "file": "共产党宣言_全文.pdf",
        "title": "《共产党宣言》（中央编译局通行中译本）",
        "track": "socialism",
        "urls": ["https://www.marxists.org/chinese/marx-engels/1848/01.htm",
                 "https://zh.wikisource.org/wiki/%E5%85%B1%E7%94%A2%E9%BB%A8%E5%AE%A3%E8%A8%80",
                 "https://zh.wikisource.org/zh-hans/%E5%85%B1%E4%BA%A7%E5%85%9A%E5%AE%A3%E8%A8%80"],
        "modes": ["off", "clash", "clash"],
        "start": "一个幽灵",
        "end": None,
    },
]


def fetch(url: str, mode: str = "env") -> str:
    """mode: env=跟随环境代理；off=强制直连；clash=走本机 7897。"""
    handlers = []
    if mode == "off":
        handlers.append(urllib.request.ProxyHandler({}))
    elif mode == "clash":
        handlers.append(urllib.request.ProxyHandler(
            {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Referer": url,
    })
    raw = opener.open(req, timeout=40).read()
    for enc in ("utf-8", "gbk", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def strip_html(html: str) -> list:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</p\s*>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", html)
    text = htmllib.unescape(text)
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", "", raw_line)
        if len(line) < 4:
            continue
        lines.append(line)
    return lines


def cut_body(lines: list, start_marker: str, end_marker) -> list:
    body, started = [], False
    for line in lines:
        if not started:
            if start_marker in line:
                started = True
                body.append(line)
            continue
        if end_marker and end_marker in line:
            body.append(line)
            break
        body.append(line)
    # 去掉导航/版权噪声
    noise = ("版权所有", "网站地图", "扫一扫在手机", "【我要纠错】", "打印本页", "责任编辑", "相关稿件")
    return [x for x in body if not any(n in x for n in noise)]


def build_pdf(path: Path, title: str, track_name: str, source_url: str, body: list) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    pdfmetrics.registerFont(TTFont("Hei", r"C:\Windows\Fonts\simhei.ttf"))
    pdfmetrics.registerFont(TTFont("Song", r"C:\Windows\Fonts\simfang.ttf") if Path(r"C:\Windows\Fonts\simfang.ttf").exists()
                            else TTFont("Song", r"C:\Windows\Fonts\simhei.ttf"))

    st_title = ParagraphStyle("t", fontName="Hei", fontSize=17, leading=26,
                              alignment=1, spaceAfter=14, wordWrap="CJK")
    st_meta = ParagraphStyle("m", fontName="Song", fontSize=9.5, leading=15,
                             alignment=1, textColor="#555555", spaceAfter=18, wordWrap="CJK")
    st_body = ParagraphStyle("b", fontName="Song", fontSize=11.5, leading=21,
                             firstLineIndent=23, wordWrap="CJK")
    st_end = ParagraphStyle("e", fontName="Song", fontSize=9.5, leading=15,
                            textColor="#777777", spaceBefore=20, wordWrap="CJK")

    def esc(s: str) -> str:
        return htmllib.escape(s)

    story = [Paragraph(esc(title), st_title),
             Paragraph(f"课程：{track_name} ｜ 官方发布文件 · 全文排版版", st_meta)]
    for para in body:
        story.append(Paragraph(esc(para), st_body))
    today = datetime.date.today().isoformat()
    story.append(Paragraph(
        f"来源：{esc(source_url)}（官方网页全文，抓取日期 {today}）。"
        f"本 PDF 供「四史」学习助手内置史料使用，正文未作删改。", st_end))

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            topMargin=64, bottomMargin=56, leftMargin=58, rightMargin=58,
                            title=title)
    doc.build(story)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for src in SOURCES:
        target = OUT_DIR / src["file"]
        if target.exists():
            w("[skip] 已存在", src["file"])
            manifest.append({"title": src["title"], "track": src["track"],
                             "file": src["file"], "source": src["urls"][0]})
            continue
        try:
            html = None
            modes = src.get("modes", ["env"] * len(src["urls"]))
            for u, m in zip(src["urls"], modes):
                try:
                    html = fetch(u, mode=m)
                    src["_ok_url"] = u
                    break
                except Exception as e:
                    w("  candidate fail", m, u[:60], repr(e)[:80])
            if not html:
                w("[fail] 所有候选源均失败", src["file"])
                continue
            lines = strip_html(html)
            body = cut_body(lines, src["start"], src["end"])
            if len(body) < 20 or sum(len(x) for x in body) < 2000:
                w("[fail] 正文太短", src["file"], "lines=", len(body))
                continue
            name = qushi_track_name(src["track"])
            build_pdf(target, src["title"], name, src["_ok_url"], body)
            manifest.append({"title": src["title"], "track": src["track"],
                             "file": src["file"], "source": src["_ok_url"]})
            w("[ok] ", src["file"], "段落数", len(body), "字数", sum(len(x) for x in body))
        except Exception as e:
            w("[fail]", src["file"], repr(e))
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    w("manifest:", len(manifest), "份")
    return 0


def qushi_track_name(track: str) -> str:
    sys.path.insert(0, str(ROOT / "backend"))
    from app import qushi
    return qushi.track_map().get(track, {}).get("name", track)


if __name__ == "__main__":
    raise SystemExit(main())
