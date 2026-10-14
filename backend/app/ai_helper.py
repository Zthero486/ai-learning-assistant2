"""AI 辅助模块 v1：DeepSeek API 调用 + 无 key 时的本地规则引擎降级。

v1 朴素实现说明：
- API key 从环境变量 / .env 读取，未配置时 is_available() 返回 False，
  上层接口自动走规则引擎（抽取式总结 / 关键词检索答疑 / 统计薄弱点分析）。
- 供应商为 OpenAI 兼容协议，默认 DeepSeek (https://api.deepseek.com)。
"""

import json
import os
import re
from pathlib import Path

import httpx

# ---------- v1 硬编码配置（v2 重构目标：迁移到统一配置中心） ----------
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
REQUEST_TIMEOUT = 60.0
MAX_CONTEXT_CHARS = 4000  # 拼进 prompt 的资料片段上限


def _load_dotenv() -> None:
    """朴素 .env 读取：只支持 KEY=VALUE 行，不覆盖已有环境变量。"""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def is_available() -> bool:
    """是否配置了大模型 API key。"""
    return bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())


def get_base_url() -> str:
    return os.environ.get("AI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def get_model() -> str:
    return os.environ.get("AI_MODEL", DEFAULT_MODEL)


def call_llm(system_prompt: str, user_prompt: str) -> str:
    """调用大模型（OpenAI 兼容 /chat/completions），返回文本回复。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")
    resp = httpx.post(
        f"{get_base_url()}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": get_model(),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.5,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ==================== 文本处理工具（规则引擎与 RAG 共用） ====================

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?\n])")


def split_sentences(text: str) -> list:
    """按中英文句读切句，过滤过短句。"""
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.strip()) >= 6]


def chunk_text(text: str, chunk_size: int = 500) -> list:
    """把长文本切成约 chunk_size 字的片段（用于关键词检索）。"""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # 尽量在句末断开，避免把句子切一半
        if end < len(text):
            tail = text[start:end]
            cut = max(tail.rfind("。"), tail.rfind("\n"))
            if cut > chunk_size // 2:
                end = start + cut + 1
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


_STOPWORDS = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "或",
    "等",
    "对",
    "为",
    "我们",
    "可以",
    "通过",
    "一个",
    "这个",
    "因此",
    "并且",
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "is",
    "and",
    "or",
    "for",
}


def extract_keywords(text: str, top_n: int = 10) -> list:
    """朴素关键词提取：中文按 2~4 字词组频次统计，英文按单词。"""
    words = re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,4}", text)
    freq = {}
    for w in words:
        w = w.lower()
        if w in _STOPWORDS or len(w) < 2:
            continue
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    return [w for w, _ in ranked[:top_n]]


def keyword_score(query: str, text: str) -> float:
    """朴素相关性打分：query 中各词在 text 中出现的加权次数。"""
    terms = re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,4}", query.lower())
    score = 0.0
    for t in set(terms):
        if t in _STOPWORDS:
            continue
        score += text.lower().count(t) * (1.0 if len(t) >= 3 else 0.5)
    return score


def search_chunks(query: str, chunks: list, top_k: int = 3) -> list:
    """返回与 query 最相关的 top_k 个片段（按 keyword_score 排序）。"""
    scored = [(keyword_score(query, c), i, c) for i, c in enumerate(chunks)]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, _, c in scored if s > 0][:top_k]


# ==================== 规则引擎降级实现 ====================


def fallback_summary(content: str) -> str:
    """无大模型时的抽取式总结：关键词句 + 首尾句 + 高频关键词。"""
    sentences = split_sentences(content)
    if not sentences:
        return "（资料内容过短，无法生成总结）"
    keywords = extract_keywords(content, top_n=8)
    kw_set = set(keywords)
    key_sentences = sorted(
        sentences,
        key=lambda s: sum(1 for k in kw_set if k in s),
        reverse=True,
    )[:5]
    lines = ["【规则引擎总结（未配置 AI，模式：抽取式）】", ""]
    lines.append("◆ 核心关键词：" + "、".join(keywords))
    lines.append("")
    lines.append("◆ 重点句子：")
    lines += [f"  {i+1}. {s}" for i, s in enumerate(key_sentences)]
    return "\n".join(lines)


def fallback_answer(question: str, chunks: list) -> str:
    """无大模型时的答疑：返回最相关的资料片段。"""
    hits = search_chunks(question, chunks, top_k=3)
    if not hits:
        return (
            "【规则引擎答疑】在已导入的资料中没有检索到与该问题相关的内容。\n"
            "提示：配置 DEEPSEEK_API_KEY 后可获得基于大模型的智能答疑。"
        )
    lines = ["【规则引擎答疑（未配置 AI，模式：资料检索）】", ""]
    for i, h in enumerate(hits, 1):
        lines.append(f"◆ 相关片段 {i}：")
        lines.append(f"  {h[:300]}{'……' if len(h) > 300 else ''}")
        lines.append("")
    return "\n".join(lines)


def fallback_questions(kp_title: str, content: str, num: int) -> list:
    """无大模型时的出题：从资料中挑含关键词的句子做简答题模板。"""
    sentences = split_sentences(content)
    keywords = extract_keywords(content, top_n=15)
    picked = []
    for s in sentences:
        hit_kws = [k for k in keywords if k in s]
        if hit_kws:
            picked.append((len(hit_kws), s, hit_kws[0]))
    picked.sort(key=lambda x: x[0], reverse=True)
    questions = []
    for _, s, kw in picked[:num]:
        blanked = s.replace(kw, "______", 1)
        questions.append(
            {
                "type": "short_answer",
                "question": f"填空：{blanked}（请答出空缺处的术语）",
                "answer": kw,
            }
        )
    while len(questions) < num:
        questions.append(
            {
                "type": "short_answer",
                "question": f"请用自己的话简述「{kp_title}」的核心内容。",
                "answer": "参考知识点描述与课程资料原文。",
            }
        )
        if len(questions) >= num:
            break
    return questions


def parse_questions_json(raw: str) -> list:
    """解析大模型返回的题目 JSON（容错：剥掉 markdown 代码块）。"""
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("模型输出中未找到 JSON 数组")
    data = json.loads(text[start : end + 1])
    out = []
    for item in data:
        q = {
            "type": str(item.get("type", "short_answer")),
            "question": str(item.get("question", "")).strip(),
            "answer": str(item.get("answer", "")).strip(),
        }
        if q["question"]:
            out.append(q)
    return out
