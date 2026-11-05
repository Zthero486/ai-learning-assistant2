# -*- coding: utf-8 -*-
"""给演示库灌四史示例数据（党史线）。

只动 release/data/app.db：
1. 清掉旧的「中学历史」演示内容（先秦到清的史料 / 知识点 / 事件 / 做题记录）；
2. 把 demo 账号设成学「党史」，灌入内置关键事件；
3. 挂若干知识点到具体章节（带思政课考法标记），每题配一道样例题；
4. 加几条四史史料，供「史料总结 / 史料答疑」演示。

幂等：同名知识点/题目已存在则跳过。
"""

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

# (章节 code, 知识点标题, 要点, 考法, 题目类型, 题干, 答案)
SEED = [
    (
        "party-01-03",
        "中共一大",
        "1921 年 7 月在上海召开，后转浙江嘉兴南湖；通过党的第一个纲领，宣告中国共产党正式成立。",
        "recall",
        "单选题",
        "中国共产党第一次全国代表大会的召开时间和地点是？",
        "1921 年 7 月，上海（后转浙江嘉兴南湖）。大会通过党的第一个纲领，宣告中国共产党正式成立。",
    ),
    (
        "party-01-02",
        "五四运动与马克思主义的传播",
        "1919 年 5 月 4 日爆发于北京，因巴黎和会上中国外交失败而起；工人阶级登上政治舞台，是新民主主义革命的开端。",
        "recall",
        "单选题",
        "五四运动成为中国新民主主义革命开端的标志性意义在于？",
        "运动中工人阶级作为独立的政治力量登上历史舞台，推动了马克思主义在中国的广泛传播；"
        "从此中国革命由旧民主主义革命转变为新民主主义革命。",
    ),
    (
        "party-02-02",
        "农村包围城市、武装夺取政权",
        "秋收起义受挫后，毛泽东率部转向井冈山，1927 年 10 月创建第一个农村革命根据地，开辟中国革命新道路。",
        "argument",
        "简答",
        "为什么说「农村包围城市、武装夺取政权」是中国革命唯一正确的道路？",
        "中国是半殖民地半封建社会，内无民主、外无民族独立，敌人长期占据中心城市且力量强大；"
        "农民占人口绝大多数，农村是敌人统治的薄弱环节。因此必须把工作重心放在农村，"
        "建立根据地、积累力量，最后夺取城市和全国政权。这是把马克思主义基本原理同中国实际相结合的成果。",
    ),
    (
        "party-02-05",
        "遵义会议",
        "1935 年 1 月在贵州遵义召开，确立毛泽东在党中央和红军的领导地位，是党的历史上生死攸关的转折点。",
        "recall",
        "简答",
        "为什么说遵义会议是党的历史上生死攸关的转折点？",
        "它在红军第五次反“围剿”失败和长征初期严重受挫的危急关头，纠正了“左”倾错误，"
        "确立毛泽东在党中央和红军的领导地位，使党中央和红军得以转危为安，"
        "标志着中国共产党在政治上开始走向成熟。",
    ),
    (
        "party-03-06",
        "中共七大与毛泽东思想的确立",
        "1945 年 4—6 月在延安召开，确立毛泽东思想为党的指导思想，形成理论联系实际、密切联系群众、批评与自我批评三大优良作风。",
        "argument",
        "论述",
        "结合史实说明中共七大确立毛泽东思想为党的指导思想的意义。",
        "七大总结了建党以来特别是抗战以来的经验，把毛泽东思想确立为党的指导思想并写入党章，"
        "使全党在思想上、政治上、组织上达到空前团结，为夺取抗日战争最后胜利和新民主主义革命胜利奠定基础。",
    ),
    (
        "party-03-02",
        "敌后抗日游击战争与《论持久战》",
        "1938 年毛泽东发表《论持久战》，指出抗战将经过战略防御、战略相持、战略反攻三个阶段，最后胜利属于中国。",
        "argument",
        "材料分析",
        "结合《论持久战》的主要内容，说明中国共产党为什么主张持久抗战。",
        "中日战争是半殖民地半封建的中国同帝国主义的日本之间在 20 世纪 30 年代进行的决死战争。"
        "日本是强国但国小、退步、失道寡助；中国是弱国但国大、进步、得道多助。"
        "因此中国既不会速胜，也不会亡国，必然经过防御、相持、反攻三个阶段走向胜利，"
        "而兵民是胜利之本，必须实行全面抗战路线。",
    ),
    (
        "party-04-06",
        "七届二中全会与“两个务必”",
        "1949 年 3 月在河北西柏坡召开，提出党的工作重心由乡村转向城市，告诫全党做到“两个务必”。",
        "argument",
        "名词解释",
        "“两个务必”",
        "毛泽东在党的七届二中全会上提出，务必使同志们继续地保持谦虚、谨慎、不骄、不躁的作风，"
        "务必使同志们继续地保持艰苦奋斗的作风。",
    ),
    (
        "party-05-05",
        "三大改造与社会主义制度的确立",
        "1956 年底，对农业、手工业和资本主义工商业的社会主义改造基本完成，社会主义基本制度在中国确立。",
        "argument",
        "简答",
        "简述社会主义改造基本完成的历史意义。",
        "实现了生产资料私有制向社会主义公有制的转变，社会主义基本制度在我国建立起来，"
        "我国从此进入社会主义初级阶段，为当代中国一切发展进步奠定了根本政治前提和制度基础。",
    ),
    (
        "party-05-02",
        "抗美援朝战争",
        "1950 年 10 月中国人民志愿军入朝作战，1953 年 7 月签订停战协定，打破了美军不可战胜的神话，新中国国际地位空前提高。",
        "apply",
        "材料分析",
        "结合抗美援朝战争，谈谈你对「打得一拳开，免得百拳来」的理解。",
        "抗美援朝是在新中国百废待兴、国家安全受到严重威胁的情况下作出的艰难决策。"
        "战争的胜利保卫了朝鲜北部和我国东北的安全，为国内经济建设赢得了相对稳定的和平环境，"
        "极大提高了新中国的国际威望，增强了民族自信心和自豪感，也积累了现代化战争的经验。",
    ),
    (
        "party-06-01",
        "中共八大对主要矛盾的判断",
        "1956 年 9 月召开，指出国内主要矛盾是人民对于建立先进工业国的要求同落后农业国现实之间的矛盾。",
        "argument",
        "简答",
        "中共八大是如何判断国内主要矛盾的？",
        "八大指出，社会主义改造基本完成后，国内主要矛盾已经是人民对于建立先进的工业国的要求"
        "同落后的农业国的现实之间的矛盾，是人民对于经济文化迅速发展的需要同当前经济文化"
        "不能满足人民需要的状况之间的矛盾。",
    ),
    (
        "party-07-01",
        "十一届三中全会",
        "1978 年 12 月召开，重新确立解放思想、实事求是的思想路线，把工作中心转移到经济建设上来，作出改革开放的历史性决策。",
        "recall",
        "单选题",
        "实现新中国成立以来党的历史上具有深远意义的伟大转折的会议是？",
        "1978 年 12 月召开的党的十一届三中全会。",
    ),
    (
        "party-07-10",
        "邓小平南方谈话",
        "1992 年 1—2 月邓小平视察武昌、深圳、珠海、上海等地并发表谈话，提出计划和市场都是经济手段、发展才是硬道理等论断。",
        "argument",
        "材料分析",
        "南方谈话为什么被称为「又一个解放思想、实事求是的宣言书」？",
        "谈话针对当时关于「姓社姓资」的争论，明确指出计划和市场都是经济手段，"
        "计划和市场都不是区分社会主义与资本主义的标志；提出「三个有利于」作为判断标准，"
        "强调发展才是硬道理、科学技术是第一生产力。"
        "它极大解放了思想，为党的十四大确立社会主义市场经济体制目标奠定了思想基础。",
    ),
    (
        "party-08-01",
        "社会主义市场经济体制目标的确立",
        "1992 年 10 月党的十四大明确提出我国经济体制改革的目标是建立社会主义市场经济体制。",
        "sequence",
        "时间排序",
        "按时间先后排列下列事件：①党的十四大提出建立社会主义市场经济体制 ②十一届三中全会作出改革开放决策 ③邓小平南方谈话 ④党的十五大确立邓小平理论为党的指导思想",
        "②→③→①→④（1978 年 12 月 → 1992 年春 → 1992 年 10 月 → 1997 年 9 月）。",
    ),
    (
        "party-10-06",
        "推动构建人类命运共同体",
        "2013 年以来习近平总书记多次阐述人类命运共同体理念，倡导共建「一带一路」，为全球治理提供中国方案。",
        "apply",
        "材料分析",
        "结合共建「一带一路」的实践，说明人类命运共同体理念的现实意义。",
        "它顺应了各国相互联系、相互依存加深的时代潮流，主张以合作共赢代替零和博弈；"
        "共建「一带一路」通过基础设施互联互通和产能合作带动沿线国家发展，"
        "为发展中国家提供了新的发展机遇，也为完善全球治理、构建更加公正合理的国际秩序提供了中国方案。",
    ),
    (
        "party-10-11",
        "全面建成小康社会",
        "2021 年 7 月宣布全面建成小康社会，历史性解决绝对贫困问题，实现第一个百年奋斗目标。",
        "apply",
        "材料分析",
        "结合脱贫攻坚的实践，说明全面建成小康社会的意义。",
        "全面建成小康社会使近一亿农村贫困人口全部脱贫，历史性解决绝对贫困问题，"
        "彰显了中国共产党领导和中国特色社会主义制度的显著优势，"
        "为实现第二个百年奋斗目标奠定了基础。",
    ),
]

# (标题, 课程/时期, 文件名, 类型, 全文) —— 供「史料总结 / 史料答疑」演示
MATERIALS = [
    (
        "《中国共产党简史》节选：中国共产党的创建",
        "党史",
        "简史-01-党的创建.txt",
        "txt",
        "第一章 中国共产党的创建和投身大革命的洪流\n\n"
        "一、近代中国民族复兴的历史任务和各种力量的艰难探索\n\n"
        "1840 年鸦片战争以后，中国逐步成为半殖民地半封建社会，国家蒙辱、人民蒙难、文明蒙尘，"
        "中华民族遭受了前所未有的劫难。争取民族独立、人民解放和实现国家富强、人民幸福，"
        "成为近代以来中华民族面临的两大历史任务。\n\n"
        "为了拯救民族危亡，太平天国运动、洋务运动、戊戌变法、义和团运动、辛亥革命接连而起，"
        "各种救国方案轮番出台，但都以失败告终。辛亥革命推翻了统治中国几千年的君主专制制度，"
        "但并没有改变中国半殖民地半封建的社会性质和人民的悲惨命运。\n\n"
        "二、五四运动和马克思主义在中国的传播\n\n"
        "1919 年 5 月 4 日，因巴黎和会上中国外交失败，北京学生举行示威游行，五四运动爆发。"
        "6 月以后，运动中心由北京转移到上海，工人阶级以独立的姿态登上政治舞台。"
        "五四运动是中国旧民主主义革命走向新民主主义革命的转折点。\n\n"
        "三、中国共产党的成立和民主革命纲领的制定\n\n"
        "1921 年 7 月 23 日，中国共产党第一次全国代表大会在上海开幕，最后一天的会议转移到"
        "浙江嘉兴南湖的游船上举行。出席大会的有 13 名代表，代表全国 50 多名党员。"
        "大会通过党的第一个纲领，确定党的名称为「中国共产党」，宣告中国共产党正式成立。"
        "中国共产党的成立，是开天辟地的大事变，深刻改变了近代以后中华民族发展的方向和进程。\n",
    ),
    (
        "毛泽东《论联合政府》节选（1945 年 4 月）",
        "党史",
        "论联合政府-节选.txt",
        "txt",
        "（一九四五年四月二十四日，中国共产党第七次全国代表大会上的政治报告）\n\n"
        "我们共产党人区别于其他任何政党的又一个显著的标志，就是和最广大的人民群众取得最密切的联系。"
        "全心全意地为人民服务，一刻也不脱离群众；一切从人民的利益出发，而不是从个人或小集团的利益出发；"
        "向人民负责和向党的领导机关负责的一致性；这些就是我们的出发点。\n\n"
        "以马克思列宁主义的理论思想武装起来的中国共产党，在中国人民中产生了新的工作作风，"
        "这主要的就是理论和实践相结合的作风，和人民群众紧密地联系在一起的作风以及自我批评的作风。\n\n"
        "放手发动群众，壮大人民力量，在我党的领导下，打败日本侵略者，解放全国人民，"
        "建立一个新民主主义的中国。——这就是我们党的路线。\n",
    ),
    (
        "《中华人民共和国简史》节选：抗美援朝、保家卫国",
        "新中国史",
        "简史-抗美援朝.txt",
        "txt",
        "1950 年 6 月朝鲜内战爆发后，美国武装干涉朝鲜并派第七舰队侵入台湾海峡，"
        "美军飞机多次轰炸中国东北边境地区，新中国的国家安全受到严重威胁。\n\n"
        "应朝鲜党和政府请求，中共中央作出抗美援朝、保家卫国的历史性决策。"
        "1950 年 10 月 19 日，中国人民志愿军跨过鸭绿江入朝作战。"
        "志愿军将士面对的是世界第一工业强国的军队，在武器装备处于极大劣势的条件下，"
        "以「钢少气多」力克「钢多气少」，连续进行五次战役，把战线稳定在三八线附近。\n\n"
        "1953 年 7 月 27 日，《朝鲜停战协定》在板门店签字。抗美援朝战争的胜利，"
        "打破了美军不可战胜的神话，保卫了朝鲜北部和中国的安全，"
        "为国内经济建设赢得了相对稳定的和平环境，极大提高了新中国的国际威望。\n",
    ),
    (
        "邓小平南方谈话要点（1992 年 1—2 月）",
        "改革开放史",
        "南方谈话-要点.txt",
        "txt",
        "1992 年 1 月 18 日至 2 月 21 日，邓小平先后视察武昌、深圳、珠海、上海等地并发表重要谈话。\n\n"
        "革命是解放生产力，改革也是解放生产力。\n"
        "计划多一点还是市场多一点，不是社会主义与资本主义的本质区别。"
        "计划经济不等于社会主义，资本主义也有计划；市场经济不等于资本主义，社会主义也有市场。"
        "计划和市场都是经济手段。\n"
        "社会主义的本质，是解放生产力，发展生产力，消灭剥削，消除两极分化，最终达到共同富裕。\n"
        "判断的标准，应该主要看是否有利于发展社会主义社会的生产力，"
        "是否有利于增强社会主义国家的综合国力，是否有利于提高人民的生活水平。\n"
        "发展才是硬道理。科学技术是第一生产力。\n"
        "要坚持两手抓，一手抓改革开放，一手抓打击各种犯罪活动。\n\n"
        "南方谈话从理论上深刻回答了长期困扰和束缚人们思想的许多重大问题，"
        "是把改革开放和现代化建设推向新阶段的又一个解放思想、实事求是的宣言书。\n",
    ),
    (
        "《共产党宣言》节选（1848 年）",
        "社会主义发展史",
        "共产党宣言-节选.txt",
        "txt",
        "一个幽灵，共产主义的幽灵，在欧洲游荡。\n\n"
        "至今一切社会的历史都是阶级斗争的历史。\n\n"
        "资产阶级在历史上曾经起过非常革命的作用。资产阶级在它的不到一百年的阶级统治中所创造的生产力，"
        "比过去一切世代创造的全部生产力还要多，还要大。\n\n"
        "随着大工业的发展，资产阶级赖以生产和占有产品的基础本身也就从它的脚下被挖掉了。"
        "它首先生产的是它自身的掘墓人。资产阶级的灭亡和无产阶级的胜利是同样不可避免的。\n\n"
        "共产党人可以把自己的理论概括为一句话：消灭私有制。\n\n"
        "代替那存在着阶级和阶级对立的资产阶级旧社会的，将是这样一个联合体，"
        "在那里，每个人的自由发展是一切人的自由发展的条件。\n\n"
        "无产者在这个革命中失去的只是锁链。他们获得的将是整个世界。\n"
        "全世界无产者，联合起来！\n",
    ),
]


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
    # 旧任务可能挂在已删除的知识点上
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


def seed_materials(conn: sqlite3.Connection) -> int:
    added = 0
    for title, course, filename, ftype, content in MATERIALS:
        have = conn.execute(
            "SELECT 1 FROM materials WHERE user_id=1 AND title=?", (title,)
        ).fetchone()
        if have:
            continue
        conn.execute(
            "INSERT INTO materials(user_id,uuid,title,course,filename,filetype,content,created_at)"
            " VALUES(1,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, title, course, filename, ftype, content, now()),
        )
        added += 1
    conn.commit()
    return added


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
    # 前 60% 正确、后 40% 错误：看起来像「先复习后做题、越做越好」的真实轨迹
    added = 0
    for i, qid in enumerate(qids[:14]):
        day = 6 - min(i // 2, 6)          # 最近 7 天内均摊
        ts = (datetime.now() - timedelta(days=day, hours=2)).isoformat(timespec="seconds")
        correct = 1 if i < 9 else 0
        conn.execute(
            "INSERT INTO practice_records(user_id,question_id,user_answer,correct,created_at,uuid)"
            " VALUES(1,?,?,?,?,?)",
            (qid, "已作答" if correct else "", correct, ts, uuid.uuid4().hex),
        )
        added += 1
    conn.commit()
    return added


def seed_tasks(conn: sqlite3.Connection) -> int:
    """两三个四史复习任务，演示「复习任务」页。已有任务则跳过。"""
    if conn.execute("SELECT COUNT(*) FROM tasks WHERE user_id=1").fetchone()[0]:
        return 0
    plan = [
        ("party-02-05", "复习：遵义会议与长征的胜利",
         "把「生死攸关的转折点」讲清楚：背景（第五次反围剿失败）→ 会议内容 → 意义三层。", 2),
        ("party-07-01", "复习：十一届三中全会",
         "思想路线、工作重心、改革开放决策三条线各写一句，注意与南方谈话的承接关系。", 4),
        ("party-10-11", "整理：全面建成小康社会的答题素材",
         "准备两个数据型论据 + 一句制度优势的表述，用于材料分析题。", 7),
    ]
    added = 0
    for code, title, desc, days in plan:
        conn.execute(
            "INSERT INTO tasks(user_id,course,kp_id,title,description,due_date,status,created_at,uuid)"
            " VALUES(1,'党史',NULL,?,?,?, 'todo', ?,?)",
            (title, desc,
             (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d"),
             now(), uuid.uuid4().hex),
        )
        added += 1
    conn.commit()
    return added


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
    log.append(f"内置事件新增 {seeded}")

    kp_added = q_added = 0
    new_qids = []
    for code, title, desc, exam, qtype, question, answer in SEED:
        row = conn.execute(
            "SELECT id FROM knowledge_points WHERE user_id=1 AND title=?", (title,)
        ).fetchone()
        if row:
            kid = row["id"]
        else:
            cur = conn.execute(
                "INSERT INTO knowledge_points(user_id,uuid,course,title,description,"
                "node_code,exam_type,created_at) VALUES(1,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, "党史", title, desc, code, exam, now()),
            )
            kid = cur.lastrowid
            kp_added += 1
        have = conn.execute(
            "SELECT id FROM questions WHERE user_id=1 AND kp_id=? AND question=?", (kid, question)
        ).fetchone()
        if not have:
            cur = conn.execute(
                "INSERT INTO questions(user_id,uuid,kp_id,type,question,answer,source,exam_type,created_at)"
                " VALUES(1,?,?,?,?,?,'manual',?,?)",
                (uuid.uuid4().hex, kid, qtype, question, answer, exam, now()),
            )
            new_qids.append(cur.lastrowid)
            q_added += 1
        else:
            new_qids.append(have["id"])
    conn.commit()
    log.append(f"知识点新增 {kp_added}，题目新增 {q_added}")

    mat_added = seed_materials(conn)
    log.append(f"四史史料新增 {mat_added}")

    # 造两条错题，让「错题本 / 复习计划」有内容可演示（挑两道论述型）
    made = []
    for qid in new_qids[-3:]:
        row = conn.execute(
            "SELECT id FROM wrong_book WHERE user_id=1 AND question_id=?", (qid,)
        ).fetchone()
        if row:
            continue
        conn.execute(
            "INSERT INTO wrong_book(user_id,question_id,wrong_count,resolved,review_marked,"
            "last_wrong_at,uuid,correct_streak,next_review_at,error_type) VALUES(1,?,?,0,0,?,?,0,?,?)",
            (qid, 2, now(), uuid.uuid4().hex,
             (datetime.now() + timedelta(days=1)).isoformat(timespec="seconds"), "concept"),
        )
        made.append(qid)
    conn.commit()
    log.append(f"错题样本新增 {len(made)}")

    log.append(f"做题记录新增 {seed_practice(conn)}")
    log.append(f"复习任务新增 {seed_tasks(conn)}")

    for table in ("syllabus_nodes", "materials", "knowledge_points", "questions",
                  "events", "wrong_book", "practice_records"):
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
