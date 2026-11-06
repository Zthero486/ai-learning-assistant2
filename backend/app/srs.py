"""间隔复习排期：FSRS 算法适配层。

来源与授权
----------
算法移植自 https://github.com/open-spaced-repetition/py-fsrs （MIT License），
即 Anki 现役排期算法 FSRS-6 的 Python 实现。本文件只做「适配」：
把 py-fsrs 的 Card/Scheduler 贴到本项目的 wrong_book 表上，不改算法本身。

为什么单独一层
--------------
1. **可降级**：没装 fsrs 时 AUTOMATICALLY 退回旧的天数阶梯（1/2/4/7/15 天），
   打包体积、离线环境都不受影响。
2. **不动表结构**：卡片状态整体序列化成一个 JSON 塞进 wrong_book.srs 一列，
   以后换算法版本只改这里，不用再加列、不用改同步字段。
3. **老数据直接兼容**：没有 srs 记录的老错题，用 next_review_at 反推一个
   「已经排到今天」的卡片，不会因为升级把复习计划清零。

与 Anki 默认参数唯一的区别：学习步长按「天」而不是「分钟」。
这是每天打开一次的学习工具，不是一天刷几百张卡的背单词 App —— 默认参数
会让「答错」的卡 1 分钟后到期，学生根本不会回来。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

try:  # 可选依赖：缺失时全程走降级分支
    from fsrs import Card, Rating, Scheduler

    AVAILABLE = True
except Exception:  # pragma: no cover - 只在缺包时触发
    Card = Rating = Scheduler = None  # type: ignore
    AVAILABLE = False


# 旧的天数阶梯，fsrs 不可用时的兜底（也是坏卡片的默认值）
FALLBACK_INTERVALS = (1, 2, 4, 7, 15)

# 排期间隔超过这么多天，视为进入长期记忆（可以直接移出活跃错题库）
LONG_TERM_DAYS = 21

_scheduler = None


def scheduler():
    """惰性构造单例 Scheduler（构造有开销，且插件包不保证可重入）。"""
    global _scheduler
    if not AVAILABLE:
        return None
    if _scheduler is None:
        _scheduler = Scheduler(
            desired_retention=0.9,
            learning_steps=(timedelta(days=1),),
            relearning_steps=(timedelta(days=1),),
            enable_fuzzing=False,  # 抖动对单机演示没意义，反而让排期不好解释
        )
    return _scheduler


# ==================== 时间工具 ====================
def _to_local_naive(dt: datetime) -> datetime:
    """fsrs 内部一律 UTC aware，库里存的是本地 naive，这里统一口径。"""
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _as_utc(dt: datetime) -> datetime:
    """naive 时间按本地时区理解，再转 UTC —— 和 _to_local_naive 互为逆操作。"""
    if dt.tzinfo is None:
        return dt.astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_iso(text: str) -> datetime | None:
    """宽松解析：兼容 '2026-11-06T09:14:44' 与带时区的写法，坏值返回 None。"""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def local_iso(dt: datetime) -> str:
    return _to_local_naive(dt).isoformat(timespec="seconds")


# ==================== 卡片状态 <-> 数据库 ====================
def row_to_card(row) -> "Card | None":
    """把 wrong_book 的一行还原成 fsrs 卡片。

    优先读 srs JSON；没有就用 next_review_at / last_wrong_at 反推，
    保证老数据升级后「下次复习时间」不丢。
    """
    if not AVAILABLE:
        return None
    raw = ""
    try:
        raw = row["srs"] or ""
    except (KeyError, IndexError, TypeError):
        raw = ""
    card = None
    if raw:
        try:
            card = Card.from_dict(json.loads(raw))
        except Exception:
            card = None
    if card is None:
        card = Card()
        due = parse_iso(row["next_review_at"] if "next_review_at" in row.keys() else "")
        if due:
            card.due = _as_utc(due)
    return card


def card_to_row(card) -> str:
    if card is None:
        return ""
    try:
        return json.dumps(card.to_dict(), ensure_ascii=False)
    except Exception:
        return ""


def fallback_interval(wrong_count: int) -> int:
    """旧逻辑：错得越多，下次复习越晚（1/2/4/7/15 天）。"""
    n = max(int(wrong_count or 1) - 1, 0)
    return FALLBACK_INTERVALS[min(n, len(FALLBACK_INTERVALS) - 1)]


# ==================== 主入口：排下一次复习 ====================
def review(
    row,
    correct: bool,
    at: datetime | None = None,
    rating: str = "",
) -> dict:
    """根据「这次答对没」算出下次复习时间与新的卡片状态。

    返回 dict：
      next_review_at  本地 naive iso，直接写库/展示
      interval_days   距今天数（浮点，保留 1 位）
      srs             要写回 wrong_book.srs 的 JSON（降级时为空串）
      stability/difficulty/retrievability  可展示的掌握度指标
      algorithm       'fsrs' 或 'ladder'，方便测试和界面说明
      long_term       True 表示间隔已够长，可视为长期记住
    """
    at = at or datetime.now()
    wrong_count = int(row["wrong_count"] or 1) if _has(row, "wrong_count") else 1

    sched = scheduler()
    if sched is None:
        days = fallback_interval(wrong_count if not correct else 1)
        if correct:
            days = 2  # 答对一次，按阶梯第二档往后排
        return {
            "next_review_at": local_iso(at + timedelta(days=days)),
            "interval_days": float(days),
            "srs": "",
            "stability": None,
            "difficulty": None,
            "retrievability": None,
            "algorithm": "ladder",
            "long_term": False,
        }

    card = row_to_card(row)
    if card is None:  # pragma: no cover - AVAILABLE 时不会走到
        card = Card()
    kind = rating or ("good" if correct else "again")
    grade = {
        "again": Rating.Again,
        "hard": Rating.Hard,
        "good": Rating.Good,
        "easy": Rating.Easy,
    }.get(kind, Rating.Good if correct else Rating.Again)

    try:
        card, _log = sched.review_card(card, grade, _as_utc(at))
    except Exception:
        # 算法内部异常（比如老 JSON 字段不兼容）→ 退回阶梯，别让答题接口 500
        days = fallback_interval(wrong_count)
        return {
            "next_review_at": local_iso(at + timedelta(days=days)),
            "interval_days": float(days),
            "srs": "",
            "stability": None,
            "difficulty": None,
            "retrievability": None,
            "algorithm": "ladder",
            "long_term": False,
        }

    due_local = _to_local_naive(card.due)
    interval = (due_local - at).total_seconds() / 86400.0
    try:
        retrievability = sched.get_card_retrievability(card, _as_utc(at))
    except Exception:
        retrievability = None
    return {
        "next_review_at": local_iso(due_local),
        "interval_days": round(interval, 1),
        "srs": card_to_row(card),
        "stability": round(card.stability, 2) if card.stability else None,
        "difficulty": round(card.difficulty, 2) if card.difficulty else None,
        "retrievability": round(retrievability, 3) if retrievability is not None else None,
        "algorithm": "fsrs",
        "long_term": interval >= LONG_TERM_DAYS,
    }


def _has(row, key: str) -> bool:
    try:
        return key in row.keys()
    except AttributeError:
        try:
            row[key]
            return True
        except (KeyError, IndexError, TypeError):
            return False


# ==================== 查询辅助 ====================
def due_state(next_review_at: str, now: datetime | None = None) -> tuple[bool, int]:
    """返回 (是否到期, 还有几天到期/逾期几天)。空值当作立即到期。"""
    due = parse_iso(next_review_at)
    if due is None:
        return True, 0
    now = now or datetime.now()
    if due.tzinfo is not None:
        due = _to_local_naive(due)
    days = (due.date() - now.date()).days
    return days <= 0, days


def describe(interval_days: float | None) -> str:
    """把间隔天数说人话：10 分钟 / 6 小时 / 3 天 / 2 周。"""
    if interval_days is None:
        return ""
    minutes = interval_days * 1440
    if minutes < 60:
        return f"{max(int(minutes), 1)} 分钟"
    hours = interval_days * 24
    if hours < 24:
        return f"{int(hours)} 小时"
    if interval_days < 14:
        return f"{int(round(interval_days))} 天"
    if interval_days < 60:
        return f"{int(round(interval_days / 7))} 周"
    return f"{int(round(interval_days / 30))} 个月"


def describe_interval(next_review_at: str, now: datetime | None = None) -> str:
    """错题卡片上的「还有几天/逾期几天」，没有排期就返回空串。"""
    due = parse_iso(next_review_at)
    if due is None:
        return ""
    due_ = _to_local_naive(due)
    now = now or datetime.now()
    days = (due_.date() - now.date()).days
    if days < 0:
        return f"已逾期 {abs(days)} 天"
    if days == 0:
        return "今天复习"
    if days == 1:
        return "明天复习"
    return f"还有 {days} 天"


def card_meta(raw: str, now: datetime | None = None) -> dict:
    """从 srs JSON 里取出可展示的记忆指标（拿不到就返回空值，不抛异常）。"""
    empty = {"stability": None, "difficulty": None, "retrievability": None}
    if not AVAILABLE or not raw:
        return empty
    try:
        card = Card.from_dict(json.loads(raw))
    except Exception:
        return empty
    sched = scheduler()
    try:
        retr = sched.get_card_retrievability(card, _as_utc(now or datetime.now()))
    except Exception:
        retr = None
    return {
        "stability": round(card.stability, 2) if card.stability else None,
        "difficulty": round(card.difficulty, 2) if card.difficulty else None,
        "retrievability": round(retr, 3) if retr is not None else None,
    }
