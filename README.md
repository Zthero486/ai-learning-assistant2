# 四史学习助手

> 面向高校「四史」课程（党史 / 新中国史 / 改革开放史 / 社会主义发展史）的个人学习空间：
> **先选课 → 按教材章节建知识点 → 四史对照时间轴 → 检索练习 → 错题间隔复习**，形成完整学习闭环。

![status](https://img.shields.io/badge/version-v2.0--qushi-blue) ![python](https://img.shields.io/badge/python-3.10+-green) ![node](https://img.shields.io/badge/node-18+-green)

> **一个账号只学一门课**。注册后先选课（`/welcome`），此后教材目录、时间轴、史实要点、自测都只围绕这一门展开；
> 侧栏「切换课程」可改选，旧数据不会删除。

## 快速开始

```bash
git clone https://github.com/qianxingzhigui/ai-learning-assistant2.git
cd ai-learning-assistant2

# 1. 后端
cd backend
python -m pip install -r requirements.txt
# 可选：想要 AI 能力再执行（不配也能跑，会自动降级为规则引擎）
#   Windows:  copy .env.example .env
#   bash:     cp .env.example .env
uvicorn app.main:app --reload --port 8000

# 2. 前端（另开终端）
cd frontend
npm install
npm run dev
```

浏览器打开 <http://127.0.0.1:5173>，演示账号 `demo` / `demo123`（已预设为「党史」）。

Windows 下可直接双击 `scripts/start_all.bat` 一键启动。

## 功能总览

| 模块 | 子功能 | 说明 |
|------|--------|------|
| 史料笔记 | 导入  解析  归档 | 支持 PDF、Word、Markdown、TXT 导入，自动提取正文并按时期归类 |
| 史实要点 | 提取 / 标注 / 关联 | 从史料整理史实要点，标注所属时期与起止年份 |
| 历史时间轴 | 聚合 / 编辑 | 按时期分组展示史事，中外史可混排；点击展开背景-经过-影响-评价五要素 |
| 复习任务 | 制定 / 跟踪 | 按时期与史实要点制定复习任务，跟踪完成状态 |
| 自测与错题 | 会话化练习 / 错题本 / 今日复习 | 自测页三步走：**组卷**（全部 / 错题优先 / 按知识点，5-15 题一轮）→ **一次一题**（单选自动解析成选项按钮即时判分，简答对照参考答案自评，参考 Anki/多邻国）→ **结算页**（正确率、用时、错题清单）。每日 10 题目标进度条；答错自动进错题本并交给 **FSRS 算法**（Anki 同款排期，移植自 py-fsrs）算下次复习时间，连对 2 次或间隔超 3 周才移出；错题本可按「今日复习」排到期队列 |
| AI 学习辅助 | 总结 / 答疑 / 薄弱点分析 / 个性化出题 | 支持任意 OpenAI 兼容大模型（阶跃 StepFun、智谱 GLM 等）；**未配置 key 时自动降级为本地规则引擎，软件照常可用** |
| **AI 对话（Agent）** | 自然语言操作全站 + 语音输入 + 联动跳转 | 顶栏「AI 对话」是能动手的助手：调 26 个工具查教材正文/史料/时间轴，并直接**建史实要点、生成资料入库、出题（每题必须附教材原文依据，无依据不入库）、建复习任务、补时间轴、给错题打错因标签、沉淀学生画像、在教材里划 AI 专属紫色重点，以及删除任务/知识点/题目/资料/事件/记忆、清空错题本**。说「切到史料笔记」AI 直接帮你切页面，出完题自动跳到自测——**AI 指令与界面联动**（可关）。支持**麦克风语音输入**（浏览器自带识别优先，录音转文字兜底）。**每个页面右下角都有浮动 AI 入口**，AI 贯穿全软件；行为由 `scripts/agent_eval.py` 的 11 场景评测集守护。写入可一键关闭 |
| 手机 / 平板 | 响应式 + PWA + 局域网/公网访问 | 窄屏自动切抽屉导航；`exe --lan` 后手机扫码即用；公网部署（Dockerfile + Caddy）后任何网络可用，可「添加到主屏幕」当 App。见 [部署到公网](docs/部署到公网.md) |
| 学习记录与统计 | 正确率 / 进度可视化 | 按史实要点统计正确率，图表展示掌握情况 |

## 技术栈

- **后端**：Python 3.10+ / FastAPI / SQLite / pytest
- **前端**：Vue 3 + Element Plus + Vite
- **AI**：OpenAI 兼容协议（智谱 GLM / 硅基流动 / DeepSeek / 通义千问 均可，切换只改 `.env` 三行）；文档解析 pypdf / python-docx

## 打包成便携版（免安装，双击即用）

想给不使用开发环境的电脑用（答辩现场、拷给同学），执行：

```bash
python scripts/build_portable.py
```

产物在 `release/` 目录：**双击 `AILearningAssistant.exe` 即可运行**，自动启动服务并打开界面；数据保存在 exe 同级的 `data/` 目录，整个文件夹可整体拷贝到其他电脑。

> 默认会把 `backend/.env` 里的 AI key 冻结进 exe（分享包开箱即用）；
> 要发「不带任何 key」的公开版本就加 `--no-embed-key`：
> `python scripts/build_portable.py --no-embed-key`。

## 配置 AI（可选，有免费方案）

**默认不用配**：打包版会把 `backend/.env` 里的 key 冻结进 exe 作为「内置默认」，
解压双击就能用大模型（当前内置阶跃 StepFun）。想换自己的模型再往下看。

**方式一：在软件里配置（推荐，免改文件）**
打开「AI 对话」→「AI 设置」（或「AI 工具台」→「配置 API Key」）→ 选平台预设 → 粘贴 Key → 保存并生效 → 点「检测 AI 连接」验证。
配置写入程序目录的 `.env` 并**立即生效，无需重启**；点「恢复默认（阶跃）」可清掉自定义配置、切回内置 key。

**方式二：手工编辑 `.env`**（复制 `backend/.env.example` 为 `backend/.env`）

平台任选，代码无需改动：

| 平台 | 免费情况 | AI_BASE_URL | AI_MODEL |
| --- | --- | --- | --- |
| **阶跃星辰 StepFun（国内推荐）** | 有免费/活动额度，OpenAI 兼容 | `https://api.stepfun.com/v1` | `step-3.5-flash` |
| **智谱 GLM（国内可用）** | GLM-4-Flash 永久免费，128K 上下文 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| **Google Gemini** | 新项目免费档已被 Google 停用（403），需绑卡 | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-3-flash-preview` |
| MiniMax | 需 M 系列订阅 | `https://api.minimax.cn/v1` | `MiniMax-M3.1-Flash` |
| 硅基流动 | 9B 以下模型永久免费 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-7B-Instruct` |
| 阿里云百炼 | 新用户百万级 Token（约 90 天） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| DeepSeek（付费） | 便宜、推理强 | `https://api.deepseek.com` | `deepseek-chat` |

```
AI_API_KEY=你的key
AI_BASE_URL=https://api.stepfun.com/v1
AI_MODEL=step-3.5-flash
```

> 阶跃有两条路径：`/v1` 按量计费可直接用；`/step_plan/v1` 需要有效的 Step Plan 订阅，
> 否则返回 400 `no active step plan subscription`，不确定时用 `/v1`。

> 走 Google 等境外接口时多配一行 `AI_PROXY=http://127.0.0.1:7897`（按自己代理端口改）；
> 不填则自动读取系统代理与 `HTTPS_PROXY` 环境变量。国内平台留空即可。

不配置也能运行——AI 接口自动降级为本地规则引擎（关键词检索 + 统计分析）。
配置后可通过界面的「检测 AI 连接」或 `POST /api/ai/test` 自检，接口会针对 401/402/404/429 给出具体原因。

## 目录结构

```
ai-learning-assistant/
├── backend/          # FastAPI 后端
│   ├── app/          # 应用代码
│   └── tests/        # pytest 测试
├── frontend/         # Vue3 前端
├── scripts/          # 启动 / 打包 / 灌数据脚本
├── docs/             # 设计说明、报告、手册、日志
└── .github/          # CI、issue/PR 模板
```

## 文档

- [**前后端说明**（简版：前端功能板块 / AI 框架搭建 / 状态机设计）](docs/前后端说明.md)
- [**用户手册**（七个子模块图文并茂，面向使用者）](docs/用户手册.md)
- [**实验报告**（环境参数、测试用例、Agent 评测与性能量化）](docs/实验报告.md)
- [**信息安全设计**（口令哈希、令牌、SQL 参数化、Agent 写入预算）](docs/信息安全设计.md)
- [**开源移植清单**（搬了哪些开源项目、改了什么、为什么不用别的，报告可直接引用）](docs/开源移植清单.md)
- [状态机设计说明（Agent 三幕流程与兜底）](docs/状态机演示.md)

## 团队

| 成员 | 角色 |
| --- | --- |
| 韦俊鑫 | 技术负责人 · 后端与架构 |
| 黄吉航 | 前端负责人 · 测试与文档 |

## 开源许可

[MIT](LICENSE)
