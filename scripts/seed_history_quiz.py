# -*- coding: utf-8 -*-
"""重建 demo 账号的历史演示数据（史料 + 要点 + 题目 + 错题）。

用法::

    python scripts/seed_history_quiz.py --user demo [--db release/data/app.db]

会先清空该用户的 materials / knowledge_points / questions / practice_records /
wrong_book / tasks（**不动 events 时间轴**），再按历史学科口径重建。
"""

import argparse
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import apppaths  # noqa: E402

WIPE = ("wrong_book", "practice_records", "questions", "tasks", "knowledge_points", "materials")

# 史料：(标题, 时期, 正文)
NOTES = [
    (
        "《史记·秦始皇本纪》节选",
        "秦",
        "二十六年，秦初并天下，令丞相、御史曰：「异日韩王纳地效玺，请为藩臣，已而倍约……"
        "寡人以眇眇之身，兴兵诛暴乱，赖宗庙之灵，六王咸伏其辜，天下大定。今名号不更，"
        "无以称成功，传后世。其议帝号。」丞相绾、御史大夫劫、廷尉斯等皆曰：「今陛下兴义兵，"
        "诛残贼，平定天下，海内为郡县，法令由一统，自上古以来未尝有，五帝所不及。」"
        "王曰：「去『泰』，著『皇』，采上古『帝』位号，号曰『皇帝』。」",
    ),
    (
        "鸦片战争前的中英贸易与禁烟（史料摘录）",
        "清",
        "材料一：乾隆五十八年（1793），英使马戛尔尼来华，要求扩大通商口岸、割让海岛，"
        "清廷以「天朝物产丰盈，无所不有，原不藉外夷货物以通有无」复之。\n"
        "材料二：18 世纪后期起，英国向中国大量输入鸦片。1838 年输入达四万余箱，"
        "白银外流，银贵钱贱。\n"
        "材料三：林则徐上道光帝：「若犹泄泄视之，是使数十年后，中原几无可以御敌之兵，"
        "且无可以充饷之银。」\n"
        "材料四：1839 年 6 月，虎门销烟，收缴鸦片二百三十七万余斤，尽数销毁。",
    ),
    (
        "中外历史纲要（上）·第一单元要点",
        "先秦秦汉",
        "一、中华文明的起源：旧石器（元谋人、北京人）；新石器（仰韶彩陶、河姆渡稻作、"
        "龙山黑陶、良渚玉器与大型水利）。早期国家特征：王位世袭、神权与王权结合、"
        "血缘与政治结合（宗法）、权力尚未高度集中。\n"
        "二、春秋战国的社会变革：铁犁牛耕推广，井田制瓦解，土地私有确立；分封制、宗法制破坏，"
        "各国变法，郡县制出现；百家争鸣——儒（仁与礼）、道（道与无为）、法（集权与法治）、"
        "墨（兼爱非攻）。\n"
        "三、秦汉统一多民族国家：秦创皇帝制、三公九卿、郡县制，统一文字货币度量衡；"
        "汉初黄老无为、郡国并行，武帝推恩令、设刺史、盐铁官营、尊崇儒术、张骞通西域。",
    ),
]

# 要点：(标题, 时期, 起始年, 简述)
KPS = [
    ("秦朝的中央集权制度", "秦", -221, "皇帝制度、三公九卿、郡县制；废分封、书同文、车同轨、统一度量衡"),
    ("汉武帝的大一统", "汉", -134, "推恩令削弱诸侯、设刺史监察、盐铁官营、尊崇儒术、北击匈奴、通西域"),
    ("科举制的创立与影响", "隋", 605, "隋炀帝始设进士科，以考试取士，打破门阀对仕途的垄断"),
    ("安史之乱与唐朝衰亡", "唐", 755, "节度使拥兵自重、中央军备空虚；历八年，唐由盛转衰，藩镇割据"),
    ("王安石变法", "北宋", 1069, "青苗、募役、方田均税、保甲诸法；富国强兵但执行扰民、党争激化"),
    ("鸦片战争与《南京条约》", "清", 1840, "英国走私鸦片与禁烟冲突；战败签约，割香港岛、五口通商、协定关税"),
]

# 题目：(要点序号, 题型, 题干, 参考答案, 错几次)  错几次>0 表示这条进错题本
QUESTIONS = [
    (
        0,
        "名词解释",
        "解释「郡县制」，并说明它与分封制的根本区别。",
        "郡县制是秦朝在全国推行的中央集权地方行政制度：郡守、县令由皇帝直接任免、不得世袭，"
        "只领俸禄不享封土。与分封制相比，分封制下诸侯世袭领地、拥有军政自主权，"
        "郡县制则把地方权力收归中央，是官僚政治取代贵族政治的标志。",
        2,
    ),
    (
        0,
        "史料解读",
        "《史记》载「海内为郡县，法令由一统，自上古以来未尝有」。这段话反映了什么？"
        "作者的立场是什么？该史料有何价值？",
        "反映了秦统一后推行郡县制、法令统一的政治现实，以及时人对这一空前局面的肯定评价。"
        "作者立场是汉初士人对秦制的追述与认同。史料价值：出自正史，属二手文献，"
        "可用于研究秦代制度，但需注意其成书于汉代、带有汉人视角。",
        1,
    ),
    (
        1,
        "因果分析",
        "汉初「郡国并行」带来了什么问题？汉武帝如何解决？",
        "问题：诸侯王势力坐大，威胁中央（七国之乱）。措施：颁布推恩令使诸侯封地越分越小；"
        "设刺史监察地方；盐铁官营、统一铸币削弱诸侯经济基础；尊崇儒术统一思想。",
        0,
    ),
    (
        1,
        "名词解释",
        "解释「推恩令」。",
        "汉武帝时允许诸侯王把封地分给子弟、建立侯国的法令。表面施恩，实则使王国越分越小，"
        "诸侯势力被逐步削弱，中央集权加强。",
        0,
    ),
    (
        2,
        "因果分析",
        "科举制的创立对门阀政治产生了什么影响？",
        "科举以考试成绩而非门第取士，使庶族地主得以入仕，打破了门阀对仕途的垄断，"
        "扩大了统治基础，也推动了社会流动与文化教育发展。",
        1,
    ),
    (
        2,
        "时间排序",
        "按时间先后排列：①科举制创立 ②商鞅变法 ③秦统一六国 ④安史之乱",
        "②③①④（商鞅变法前356—前338 → 秦统一前221 → 科举制605 → 安史之乱755）",
        0,
    ),
    (
        3,
        "因果分析",
        "安史之乱爆发的原因及其对唐朝的影响。",
        "原因：节度使拥兵自重、中央军备空虚；玄宗后期怠政、用人失当；社会矛盾积累。"
        "影响：北方经济残破，藩镇割据、宦官专权、边患加剧，唐由盛转衰。",
        2,
    ),
    (
        3,
        "论述",
        "有人说「安史之乱是唐朝制度缺陷的必然结果」。结合史实加以评述。",
        "制度缺陷：募兵制下节度使集军权、财权、行政权于一身；中央禁军虚弱；"
        "监察与制衡失效。史实：安禄山兼领三镇、拥兵十五万；乱起后两京陷落。"
        "评述：制度缺陷是根本原因，但玄宗怠政与用人失误是直接诱因，"
        "评价需区分根本原因与偶然因素。",
        0,
    ),
    (
        4,
        "名词解释",
        "解释「青苗法」，并说明王安石推行它的目的。",
        "青苗法：政府在青黄不接时向农民贷款贷谷，收获后加息偿还。目的：限制高利贷盘剥、"
        "增加政府收入。实际执行中因强制摊派而扰民，成为变法争议焦点之一。",
        1,
    ),
    (
        4,
        "论述",
        "评价王安石变法的成败。",
        "成效：增加财政收入、充实军备，一定程度上缓解三冗两积。"
        "局限：执行中用人不当、强制摊派扰民；触动大地主大官僚利益，党争激化；"
        "神宗死后新法多被废。结论：是一次有价值的富国强兵尝试，但未能解决北宋根本矛盾。",
        0,
    ),
    (
        5,
        "史料解读",
        "据「天朝物产丰盈，无所不有，原不藉外夷货物以通有无」，分析清廷的对外观念及其后果。",
        "反映清朝以天朝上国自居、视对外贸易为可有可无的朝贡行为，本质是自给自足经济下的"
        "闭关自守心态。后果：中外正常贸易受阻，中国对世界大势缺乏了解，"
        "成为近代落后挨打的重要原因。",
        2,
    ),
    (
        5,
        "名词解释",
        "《南京条约》的主要内容及其影响。",
        "内容：割香港岛、赔款两千一百万银元、开放广州厦门福州宁波上海五口通商、协定关税。"
        "影响：中国主权遭到破坏，开始沦为半殖民地半封建社会，是中国近代史的开端。",
        0,
    ),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="demo")
    ap.add_argument("--db", default="", help="数据库路径，默认用程序数据目录")
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else apppaths.app_base_dir() / "data" / "app.db"
    if not db_path.exists():
        sys.exit(f"数据库不存在：{db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM users WHERE username=?", (args.user,)).fetchone()
    if not row:
        sys.exit(f"用户不存在：{args.user}")
    uid = row["id"]

    for t in WIPE:
        conn.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
    print(f"已清空 {args.user} 的旧资料/要点/题目/错题")

    stamp = datetime.now().isoformat(timespec="seconds")
    for title, course, content in NOTES:
        conn.execute(
            "INSERT INTO materials(user_id,uuid,title,course,filename,filetype,content,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (uid, uuid.uuid4().hex, title, course, title + ".txt", "txt", content, stamp),
        )

    kp_ids = []
    for title, era, year, desc in KPS:
        cur = conn.execute(
            "INSERT INTO knowledge_points(user_id,uuid,course,title,description,era,year_start,"
            "created_at) VALUES(?,?,?,?,?,?,?,?)",
            (uid, uuid.uuid4().hex, era, title, desc, era, year, stamp),
        )
        kp_ids.append(cur.lastrowid)

    wrong = 0
    for idx, qtype, question, answer, wrong_count in QUESTIONS:
        cur = conn.execute(
            "INSERT INTO questions(user_id,uuid,kp_id,type,question,answer,source,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (uid, uuid.uuid4().hex, kp_ids[idx], qtype, question, answer, "manual", stamp),
        )
        qid = cur.lastrowid
        if wrong_count:
            # 造一条答题记录 + 错题记录，模拟真实使用痕迹
            conn.execute(
                "INSERT INTO practice_records(user_id,uuid,question_id,user_answer,correct,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (uid, uuid.uuid4().hex, qid, "", 0,
                 (datetime.now() - timedelta(days=wrong_count)).isoformat(timespec="seconds")),
            )
            conn.execute(
                "INSERT INTO wrong_book(user_id,uuid,question_id,wrong_count,resolved,"
                "review_marked,last_wrong_at,correct_streak) VALUES(?,?,?,?,0,0,?,0)",
                (uid, uuid.uuid4().hex, qid, wrong_count,
                 (datetime.now() - timedelta(days=wrong_count)).isoformat(timespec="seconds")),
            )
            wrong += 1

    conn.commit()
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id=?", (uid,)).fetchone()[0]
        for t in ("materials", "knowledge_points", "questions", "wrong_book", "events")
    }
    conn.close()
    print(f"完成：{len(NOTES)} 条史料、{len(KPS)} 个要点、{len(QUESTIONS)} 道题、{wrong} 条错题")
    print("当前：", counts)


if __name__ == "__main__":
    main()
