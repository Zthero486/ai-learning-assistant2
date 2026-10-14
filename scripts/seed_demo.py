"""演示数据初始化脚本：向本地数据库写入一套完整、可展示的学习数据。

用途：
- 首次体验 / 结课演示视频录制前，一键把软件填成"用过的样子"；
- 覆盖全部功能视图：多门课程、资料、知识点、题目、练习记录、错题本、任务。

用法（在项目根目录执行，需先关闭正在运行的后端或直接执行亦可）：
    python scripts/seed_demo.py            # 库中已有知识点时拒绝执行
    python scripts/seed_demo.py --force    # 清空并重建演示数据

注意：本脚本只操作 data/app.db（已被 .gitignore 排除），不会污染代码仓库。
"""

import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "app.db"

MATERIALS = [
    (
        "机器学习基础",
        "人工智能导论",
        "机器学习是人工智能的核心分支，研究如何让计算机从数据中自动获取规律。"
        "监督学习依赖带标注的训练数据，典型任务是分类与回归，例如垃圾邮件识别。"
        "无监督学习不使用标注数据，通过聚类与降维发现数据内部结构，例如用户分群。"
        "强化学习通过智能体与环境的交互、依据奖励信号不断试错来学习最优策略。"
        "模型评估常用训练集与测试集划分，用准确率、精确率、召回率等指标衡量泛化能力。"
        "过拟合指模型在训练集表现好而在测试集表现差，可通过正则化与交叉验证缓解。",
    ),
    (
        "神经网络与深度学习",
        "人工智能导论",
        "神经网络由输入层、隐藏层与输出层组成，神经元之间通过带权重的连接传递信号。"
        "激活函数为网络引入非线性能力，常用的有 ReLU 与 Sigmoid。"
        "反向传播算法依据链式法则计算损失函数对各层权重的梯度，再通过梯度下降更新参数。"
        "深度学习指使用多层神经网络自动提取特征的机器学习方法。"
        "卷积神经网络通过卷积核提取局部特征，广泛用于图像识别任务。"
        "循环神经网络与注意力机制适合处理文本、语音等序列数据。",
    ),
    (
        "软件设计与重构",
        "软件工程",
        "重构是在不改变软件外部行为的前提下改善其内部结构的过程。"
        "常见坏味道包括重复代码、过长函数、上帝类与硬编码配置，它们会提高维护成本。"
        "设计模式是解决特定场景问题的可复用方案，分为创建型、结构型与行为型三类。"
        "策略模式把一组可互换的算法封装起来，使算法可以独立于使用者变化。"
        "工厂模式负责对象创建的集中管理，降低调用方与具体实现的耦合。"
        "仓储模式在业务逻辑与数据访问之间建立抽象边界，便于替换存储实现与编写单元测试。",
    ),
]

# (课程, 知识点标题, 描述, 资料序号, 正确率目标: (答对次数, 答错次数))
KNOWLEDGE_POINTS = [
    ("人工智能导论", "监督学习与无监督学习", "两类学习范式的区别与典型任务", 0, (5, 1)),
    ("人工智能导论", "强化学习", "智能体、环境与奖励信号", 0, (2, 4)),
    ("人工智能导论", "模型评估与过拟合", "训练/测试划分与评估指标", 0, (3, 2)),
    ("人工智能导论", "反向传播与梯度下降", "神经网络参数更新机制", 1, (4, 1)),
    ("人工智能导论", "卷积神经网络", "局部特征提取与图像识别", 1, (1, 3)),
    ("软件工程", "重构与代码坏味道", "重构的定义与常见坏味道", 2, (6, 1)),
    ("软件工程", "策略模式", "封装可互换算法的行为型模式", 2, (2, 3)),
]

QUESTIONS = {
    "监督学习与无监督学习": [
        ("监督学习的训练数据具有什么特点？", "依赖带标注的训练数据，用输入与标签的对应关系学习映射。"),
        ("无监督学习常见的两类任务是？", "聚类与降维。"),
        ("垃圾邮件识别属于哪类学习任务？", "监督学习中的分类任务。"),
    ],
    "强化学习": [
        ("强化学习中智能体依据什么信号学习？", "依据环境返回的奖励信号不断试错学习最优策略。"),
        ("强化学习与监督学习的关键区别是什么？", "强化学习不依赖标注样本，而是通过与环境交互获得奖励反馈。"),
    ],
    "模型评估与过拟合": [
        ("什么是过拟合？", "模型在训练集表现好、在测试集表现差，泛化能力不足。"),
        ("缓解过拟合的两种常用手段？", "正则化与交叉验证。"),
    ],
    "反向传播与梯度下降": [
        ("反向传播算法计算什么？", "依据链式法则计算损失函数对各层权重的梯度。"),
        ("激活函数的作用是什么？", "为神经网络引入非线性表达能力。"),
    ],
    "卷积神经网络": [
        ("卷积神经网络适合处理什么类型的数据？", "图像等具有局部相关性的网格数据。"),
        ("卷积核的作用是什么？", "提取局部特征，通过权重共享减少参数量。"),
    ],
    "重构与代码坏味道": [
        ("重构的定义是什么？", "在不改变软件外部行为的前提下改善内部结构。"),
        ("列举三种常见代码坏味道。", "重复代码、过长函数、上帝类、硬编码配置等。"),
    ],
    "策略模式": [
        ("策略模式解决什么问题？", "把一组可互换的算法封装起来，使算法独立于使用者变化。"),
        ("策略模式属于哪一类设计模式？", "行为型模式。"),
    ],
}

TASKS = [
    ("人工智能导论", "复习监督学习与无监督学习", "回顾两类范式区别，重做错题", 1, "done"),
    ("人工智能导论", "完成强化学习专项练习", "针对奖励机制整理笔记并完成 5 道练习", 2, "doing"),
    ("人工智能导论", "整理卷积神经网络笔记", "重点掌握卷积核与感受野", 2, "todo"),
    ("软件工程", "阅读设计模式相关资料", "重点关注策略模式与工厂模式", 3, "todo"),
    ("软件工程", "完成重构前后结构对比文档", "含 UML 类图与量化指标", 7, "todo"),
]


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        sys.exit(f"未找到数据库 {DB_PATH}，请先启动过后端一次以自动建表。")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser(description="写入演示数据")
    parser.add_argument("--force", action="store_true", help="清空现有业务数据后重建")
    args = parser.parse_args()

    conn = connect()
    existing = conn.execute("SELECT COUNT(*) AS n FROM knowledge_points").fetchone()["n"]
    if existing and not args.force:
        conn.close()
        sys.exit(f"数据库中已有 {existing} 个知识点，未做任何修改。加 --force 可清空重建演示数据。")

    if args.force:
        for table in ("wrong_book", "practice_records", "questions", "tasks", "knowledge_points", "materials"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        print("已清空原有业务数据")

    # 1. 课程资料
    material_ids = []
    for title, course, content in MATERIALS:
        cur = conn.execute(
            "INSERT INTO materials(title,course,filename,filetype,content,created_at) VALUES(?,?,?,?,?,?)",
            (title, course, f"demo_{title}.md", "markdown", content, now_iso()),
        )
        material_ids.append(cur.lastrowid)
    print(f"写入资料 {len(material_ids)} 份")

    # 2. 知识点 + 题目 + 练习记录
    total_questions = total_attempts = total_wrong = 0
    for course, title, desc, mat_idx, (correct_n, wrong_n) in KNOWLEDGE_POINTS:
        kid = conn.execute(
            "INSERT INTO knowledge_points(material_id,course,title,description,created_at) VALUES(?,?,?,?,?)",
            (material_ids[mat_idx], course, title, desc, now_iso()),
        ).lastrowid

        qids = []
        for question, answer in QUESTIONS[title]:
            qid = conn.execute(
                "INSERT INTO questions(kp_id,type,question,answer,source,created_at) VALUES(?,?,?,?,?,?)",
                (kid, "short_answer", question, answer, "demo", now_iso()),
            ).lastrowid
            qids.append(qid)
        total_questions += len(qids)

        # 轮转分配正确/错误次数，形成有差异的正确率，让看板有层次
        plan = [1] * correct_n + [0] * wrong_n
        for i, is_correct in enumerate(plan):
            qid = qids[i % len(qids)]
            conn.execute(
                "INSERT INTO practice_records(question_id,user_answer,correct,created_at) VALUES(?,?,?,?)",
                (qid, "演示数据答案" if is_correct else "演示数据（答错）", is_correct, now_iso()),
            )
            total_attempts += 1
            if not is_correct:
                total_wrong += 1
                conn.execute(
                    """INSERT INTO wrong_book(question_id,wrong_count,resolved,review_marked,last_wrong_at)
                       VALUES(?,1,0,?,?)
                       ON CONFLICT(question_id) DO UPDATE SET wrong_count=wrong_count+1,
                       last_wrong_at=excluded.last_wrong_at""",
                    (qid, 1 if total_wrong % 2 == 0 else 0, now_iso()),
                )
    conn.commit()
    print(f"写入知识点 {len(KNOWLEDGE_POINTS)} 个、题目 {total_questions} 道、练习记录 {total_attempts} 条、错题 {total_wrong} 条")

    # 3. 学习任务（含近 3 天到期任务，用于看板提醒）
    for course, title, desc, due_in_days, status in TASKS:
        due = (date.today() + timedelta(days=due_in_days)).isoformat()
        conn.execute(
            "INSERT INTO tasks(course,kp_id,title,description,due_date,status,created_at) VALUES(?,?,?,?,?,?,?)",
            (course, None, title, desc, due, status, now_iso()),
        )
    conn.commit()
    print(f"写入学习任务 {len(TASKS)} 个")

    conn.close()
    print("\n演示数据就绪，打开 http://localhost:5173 查看效果。")


if __name__ == "__main__":
    main()
