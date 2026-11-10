"""AI 辅助模块 v1：OpenAI 兼容大模型 API 调用 + 无 key 时的本地规则引擎降级。

v1 朴素实现说明：
- 支持任意 OpenAI 兼容服务（智谱 GLM / 硅基流动 / DeepSeek / 通义千问 / Groq 等），
  只需在 backend/.env 里配置 AI_API_KEY + AI_BASE_URL + AI_MODEL 三项。
- 未配置 key 时 is_available() 返回 False，上层接口自动走规则引擎
  （抽取式总结 / 关键词检索答疑 / 统计薄弱点分析）。
"""

import json
import os
import re
import time

import httpx

from . import apppaths

# ---------- v1 硬编码配置（v2 重构目标：迁移到统一配置中心） ----------
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"  # 智谱 GLM：永久免费额度
DEFAULT_MODEL = "glm-4-flash"
REQUEST_TIMEOUT = 90.0  # 出 5 道题实测要 20~25s，留足余量
PRIMARY_RETRY_DELAY = 2.0  # 无备用渠道时，超时后原地重试前的等待秒数
MAX_CONTEXT_CHARS = 4000  # 拼进 prompt 的资料片段上限

# 常用免费/低价平台预设（套餐见 .env.example，切换只需改 .env 三行）
PROVIDER_PRESETS = {
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
    },
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-turbo",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-chat:free",
    },
    # Google Gemini 的 OpenAI 兼容端点（国内直连不通，需 AI_PROXY 或系统代理）
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-flash-latest",
    },
    # MiniMax M Plan 订阅：Key 要取「订阅管理 → M Plan」里的订阅 Key，不是按量付费 Key
    "minimax": {
        "base_url": "https://api.minimax.cn/v1",
        "model": "MiniMax-M3.1-Flash",
    },
    # 阶跃星辰 StepFun：国内直连。
    # 注意 /step_plan/v1 是订阅套餐专用地址，账号没有生效中的 Step Plan 会返回
    # 400 "you have no active step plan subscription"；所以默认用 /v1（走账户额度）。
    "stepfun": {
        "base_url": "https://api.stepfun.com/v1",
        "model": "step-3.5-flash",
    },
}


def _load_dotenv() -> None:
    """朴素 .env 读取：只支持 KEY=VALUE 行，不覆盖已有环境变量。

    打包为便携版后读取 exe 同级的 .env，开发态读取 backend/.env。
    """
    env_file = apppaths.env_file()
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


# ---------- 内置默认 key（打包时注入）----------
# 课设演示用：scripts/build_portable.py 会把 .env 里的阶跃 key 写进 _builtin_key.py，
# 并随 exe 一起冻结，使分享包「解压即用、默认走阶跃大模型」。
# 源码树里该文件为空/不存在，开发与测试仍按 .env 走，不依赖内置 key。
try:  # pragma: no cover - 只有打包产物里才有内容
    from ._builtin_key import BUILTIN_API_KEY as _BUILTIN_API_KEY
except Exception:  # 文件缺失、语法错误都不该影响启动
    _BUILTIN_API_KEY = ""

BUILTIN_PROVIDER = "stepfun"
BUILTIN_LABEL = "内置阶跃 StepFun（默认）"


def _env_key() -> str:
    """环境变量（.env 或界面配置）里的 key。"""
    return (os.environ.get("AI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "").strip()


def builtin_key() -> str:
    """构建时注入的内置 key；设置 AI_DISABLE_BUILTIN=1 可临时关掉（测试用）。"""
    if os.environ.get("AI_DISABLE_BUILTIN"):
        return ""
    return (_BUILTIN_API_KEY or "").strip()


def key_source() -> str:
    """key 来源：custom（用户自己配的）/ builtin（内置阶跃）/ none（未配置）。"""
    if _env_key():
        return "custom"
    return "builtin" if builtin_key() else "none"


def get_api_key() -> str:
    """取 API key：用户配置优先，其次内置默认，都没有返回空串（走规则引擎）。"""
    return _env_key() or builtin_key()


def is_available() -> bool:
    """是否可用大模型（用户配置或内置默认任一存在）。"""
    return bool(get_api_key())


def get_base_url() -> str:
    if os.environ.get("AI_BASE_URL"):
        return os.environ["AI_BASE_URL"].rstrip("/")
    if builtin_key():
        return PROVIDER_PRESETS[BUILTIN_PROVIDER]["base_url"].rstrip("/")
    return DEFAULT_BASE_URL


def get_model() -> str:
    if os.environ.get("AI_MODEL"):
        return os.environ["AI_MODEL"]
    if builtin_key():
        return PROVIDER_PRESETS[BUILTIN_PROVIDER]["model"]
    return DEFAULT_MODEL


def get_proxy() -> str:
    """可选代理：AI_PROXY=http://127.0.0.1:7897。

    留空时交给 httpx 的 trust_env（自动读 HTTPS_PROXY 与 Windows 系统代理）。
    访问 Google Gemini 等境外接口时通常需要填。
    """
    return (os.environ.get("AI_PROXY") or "").strip()


def mask_key(key: str) -> str:
    """脱敏展示 key，避免完整回显到界面或日志。"""
    if not key:
        return ""
    return key[:4] + "*" * max(len(key) - 8, 4) + key[-4:] if len(key) >= 10 else "****"


def apply_runtime_config(api_key: str, base_url: str, model: str, proxy: str = "") -> None:
    """把配置写入当前进程环境，使设置立即生效（无需重启程序）。"""
    os.environ["AI_API_KEY"] = api_key
    os.environ["AI_BASE_URL"] = base_url
    os.environ["AI_MODEL"] = model
    os.environ["AI_PROXY"] = proxy or ""


def write_env_config(api_key: str, base_url: str, model: str, proxy: str = "") -> None:
    """把 AI 配置写回 .env（保留其他行与注释），使用 UTF-8 无 BOM。"""
    path = apppaths.env_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    pairs = {"AI_API_KEY": api_key, "AI_BASE_URL": base_url, "AI_MODEL": model}
    if proxy:
        pairs["AI_PROXY"] = proxy

    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    handled = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        name = stripped.split("=", 1)[0].strip()
        if name in pairs:
            out.append(f"{name}={pairs[name]}")
            handled.add(name)
        else:
            out.append(line)
    for name, value in pairs.items():
        if name not in handled:
            out.append(f"{name}={value}")

    path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")


def config_snapshot() -> dict:
    """当前 AI 配置（key 已脱敏），供界面展示。"""
    key = get_api_key()
    source = key_source()
    return {
        "configured": bool(key),
        "source": source,
        "source_label": {
            "custom": "自定义大模型（你在软件内配置的 Key）",
            "builtin": BUILTIN_LABEL,
            "none": "未配置（规则引擎模式）",
        }[source],
        "api_key_masked": mask_key(key) if key else "",
        "base_url": get_base_url(),
        "model": get_model(),
        "proxy": get_proxy(),
        "env_path": str(apppaths.env_file()),
    }


def reset_runtime_config() -> None:
    """清掉运行时 AI 配置，回落到内置默认（阶跃）或规则引擎。"""
    for name in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL", "AI_PROXY", "DEEPSEEK_API_KEY",
                 "AI_ASR_URL", "AI_ASR_KEY", "AI_ASR_MODEL"):
        os.environ.pop(name, None)
    path = apppaths.env_file()
    if not path.exists():
        return
    keep = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.split("=", 1)[0].strip()
        if name in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL", "AI_PROXY", "DEEPSEEK_API_KEY"):
            continue
        keep.append(line)
    path.write_text("\n".join(keep).rstrip("\n") + "\n", encoding="utf-8")


# ---------- 语音识别 ASR（可选，OpenAI 兼容 /audio/transcriptions）----------
# 用途：AI 对话页的麦克风按钮。浏览器自带的 Web Speech API 免费但依赖境外服务
# （Chrome 走 Google，国内多半连不上），所以留一条服务端 ASR 的路：
#   AI_ASR_URL=https://api.siliconflow.cn/v1/audio/transcriptions   （硅基流动，SenseVoice 免费档）
#   AI_ASR_KEY=sk-xxx                                               （可省略，复用 AI_API_KEY）
#   AI_ASR_MODEL=FunAudioLLM/SenseVoiceSmall
DEFAULT_ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"
ASR_TIMEOUT = 60.0
MAX_AUDIO_BYTES = 15 * 1024 * 1024  # 一段话的录音到不了这个量级，超了多半是没停麦


def get_asr_url() -> str:
    return (os.environ.get("AI_ASR_URL") or "").strip().rstrip("/")


def get_asr_key() -> str:
    """语音识别可以单独配 key；不配则复用大模型 key（同平台时正好省一步）。"""
    return (os.environ.get("AI_ASR_KEY") or get_api_key()).strip()


def get_asr_model() -> str:
    return (os.environ.get("AI_ASR_MODEL") or DEFAULT_ASR_MODEL).strip()


def asr_available() -> bool:
    return bool(get_asr_url() and get_asr_key())


def transcribe(filename: str, content: bytes, content_type: str = "") -> str:
    """把一段录音转成文字。失败抛异常，由路由层兜成 4xx/5xx。"""
    url = get_asr_url()
    if not url:
        raise RuntimeError("未配置语音识别服务（AI_ASR_URL）")
    if not get_asr_key():
        raise RuntimeError("未配置语音识别的 API key")
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {get_asr_key()}"},
        files={"file": (filename or "audio.webm", content, content_type or "audio/webm")},
        data={"model": get_asr_model()},
        timeout=ASR_TIMEOUT,
        proxy=get_proxy() or None,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"语音识别服务返回 HTTP {resp.status_code}: {(resp.text or '')[:200]}")
    payload = resp.json()
    return (payload.get("text") or "").strip()


def _chat_once(base_url: str, api_key: str, model: str, payload: dict) -> dict:
    """向单个渠道发一次请求，返回 assistant message；HTTP>=400 抛 HTTPStatusError。"""
    body = dict(payload, model=model)
    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=body,
        timeout=REQUEST_TIMEOUT,
        proxy=get_proxy() or None,
    )
    if resp.status_code >= 400:
        detail = (resp.text or "")[:500]
        raise httpx.HTTPStatusError(
            f"HTTP {resp.status_code}: {detail}", request=resp.request, response=resp
        )
    return resp.json()["choices"][0]["message"]


def _providers() -> list:
    """本次调用依次尝试的 (base_url, api_key, model) 列表：主配置在前，备用兑底。

    备用渠道在 .env 里配三行（如智谱免费档做阶跃的兑底，见 .env.example）：
        AI_BACKUP_BASE_URL=https://open.bigmodel.cn/api/paas/v4
        AI_BACKUP_API_KEY=...
        AI_BACKUP_MODEL=glm-4-flash
    """
    chain = [(get_base_url(), get_api_key(), get_model())]
    b_url = (os.environ.get("AI_BACKUP_BASE_URL") or "").strip()
    b_key = (os.environ.get("AI_BACKUP_API_KEY") or "").strip()
    if b_url and b_key:
        b_model = (os.environ.get("AI_BACKUP_MODEL") or "").strip() or "glm-4-flash"
        chain.append((b_url, b_key, b_model))
    return chain


def _is_transient(e: Exception) -> bool:
    """超时/连接抖动/限流/服务端 5xx —— 换个渠道再试是有意义的。"""
    if isinstance(e, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        return code == 429 or code >= 500
    return False


def _chat_with_failover(payload: dict) -> dict:
    """带兑底的多渠道调用：主模型超时/限流/5xx 时自动切备用，不丢调用上下文。

    状态机（感知→行动→审查）每一轮都走这里，中途切模型对它完全透明——
    轮次、工具调用、上下文都不受影响，只有 HTTP 请求换了目的地。
    渠道遍历完仍失败则把最后一个错误抛出去，由上层翻译成人话。
    """
    chain = _providers()
    last: Exception | None = None
    for i, (url, key, model) in enumerate(chain):
        try:
            return _chat_once(url, key, model, payload)
        except httpx.HTTPStatusError as e:
            last = e
            if not _is_transient(e):
                # 400/401/451 这类换渠道也大概率复现的问题：带工具时先试同渠道去工具降级
                if payload.get("tools") and e.response.status_code in (400, 404, 422):
                    light = {k: v for k, v in payload.items() if k not in ("tools", "tool_choice")}
                    try:
                        return _chat_once(url, key, model, light)
                    except Exception as e2:
                        last = e2
                continue
            if i + 1 >= len(chain):
                break
        except Exception as e:  # 超时/连接错误
            last = e
            if i + 1 >= len(chain):
                # 没有备用渠道了：原地重试一次（阶跃抖动常是瞬时的）
                time.sleep(PRIMARY_RETRY_DELAY)
                return _chat_once(url, key, model, payload)
    raise last


def call_llm(system_prompt: str, user_prompt: str) -> str:
    """调用大模型（OpenAI 兼容 /chat/completions），返回文本回复。"""
    if not get_api_key():
        raise RuntimeError("未配置 AI_API_KEY")
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
    }
    msg = _chat_with_failover(payload)
    return msg.get("content") or ""


def chat_completion(messages: list, tools: list = None, temperature: float = 0.4) -> dict:
    """多轮对话 + 工具调用：返回 assistant 的 message 字典（含 tool_calls）。

    两层兜底：
    1. 渠道兑底——主模型超时/限流/5xx 自动切备用渠道（AI_BACKUP_* 配置），
       状态机轮次与上下文不受影响；
    2. 工具降级——某渠道不认 tools 字段（400/404/422）时去掉工具重问，
       模型仍能纯文本作答，不至于让对话整条挂掉。
    """
    if not get_api_key():
        raise RuntimeError("未配置 AI_API_KEY")
    payload = {
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return _chat_with_failover(payload)


def test_connection() -> dict:
    """连通性自检：发一条最短请求，验证 key / 地址 / 模型三项配置是否正确。"""
    if not is_available():
        return {
            "ok": False,
            "reason": "no_key",
            "message": "未配置 AI_API_KEY（当前为规则引擎降级模式）",
        }
    try:
        reply = call_llm("你是连通性测试助手，只回复两个字。", "请回复：正常")
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        hint = {
            401: "API key 无效或未激活",
            402: "账户余额不足，请充值或换免费模型",
            403: "无权限访问该模型，请检查模型名与实名认证状态",
            404: "接口地址或模型名不存在，请核对 AI_BASE_URL / AI_MODEL",
            429: "触发速率限制（免费额度常见），稍后重试",
        }.get(code, "请核对配置")
        if code == 403 and "free tier" in (e.response.text or "")[:2000].lower():
            hint = (
                "该 key 的 Gemini 免费额度已被 Google 停用（提示需开通付费）——"
                "要么到 aistudio.google.com/billing 绑卡开通，要么换国内平台"
                "（智谱 GLM-4-Flash 永久免费，在「配置 API Key」里切换预设即可）"
            )
        return {
            "ok": False,
            "reason": f"http_{code}",
            "message": f"调用失败：{hint}（HTTP {code}）",
        }
    except httpx.HTTPError as e:
        hint = ""
        if not get_proxy() and ("gemini" in get_base_url() or "openai.com" in get_base_url()):
            hint = "（该接口在境内需代理：可在 .env 里设置 AI_PROXY=http://127.0.0.1:端口）"
        return {"ok": False, "reason": "network", "message": f"网络不通：{e}{hint}"}
    except Exception as e:
        # 兜底：非 httpx 异常（如打包环境归档损坏导致的模块加载失败）也不能 500，
        # 学生只会看到「请求失败」，必须给出可行动的提示。异常照记日志。
        import traceback
        traceback.print_exc()
        return {
            "ok": False,
            "reason": "error",
            "message": f"AI 调用出现意外错误：{type(e).__name__}: {e}（请重启软件再试一次）",
        }
    return {
        "ok": True,
        "reason": "ok",
        "message": f"连接成功，模型回复：{reply.strip()[:30]}",
        "base_url": get_base_url(),
        "model": get_model(),
    }


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
            "提示：到「AI 助手 → 配置 API Key」选平台（如阶跃 StepFun / 智谱 GLM）"
            "粘贴 Key 并保存，即可获得基于大模型的智能答疑。"
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
