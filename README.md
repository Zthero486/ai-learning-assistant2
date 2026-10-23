# AI 智能学习助手

> 面向学习场景的个人智能学习空间：课程资料 → 知识点 → 学习任务 → 练习 → 错题 → AI 分析，形成完整学习闭环。

![status](https://img.shields.io/badge/version-v1.0--naive-blue) ![python](https://img.shields.io/badge/python-3.10+-green) ![node](https://img.shields.io/badge/node-18+-green)

> 📌 **协作成员请先读：[协作看板](docs/协作看板.md)** —— 谁做什么、做到哪一步，全部以看板为准，不看群聊不看口头。

## 功能总览

| 模块 | 子功能 | 说明 |
|------|--------|------|
| 课程资料管理 | 资料导入 / 解析 / 归档 | 支持 PDF、Word、Markdown、TXT 导入，自动提取正文并按课程归类 |
| 知识点管理 | 提取 / 标注 / 关联 | 从资料整理知识点，支持人工补充标注 |
| 学习任务管理 | 制定 / 跟踪 | 按课程与知识点制定任务，跟踪完成状态 |
| 练习与错题 | 练习记录 / 错题本 | 记录练习结果，自动沉淀错题并支持回顾 |
| AI 学习辅助 | 总结 / 答疑 / 薄弱点分析 / 出题 | 支持任意 OpenAI 兼容大模型（智谱 GLM 永久免费即可用）；**未配置 key 时自动降级为本地规则引擎，软件照常可用** |
| 学习记录与统计 | 正确率 / 进度可视化 | 按知识点统计正确率，图表展示掌握情况 |

## 技术栈

- **后端**：Python 3.10+ / FastAPI / SQLite / pytest
- **前端**：Vue 3 + Element Plus + Vite
- **AI**：OpenAI 兼容协议（智谱 GLM / 硅基流动 / DeepSeek / 通义千问 均可，切换只改 `.env` 三行）；文档解析 pypdf / python-docx

## 快速开始

```bash
# 1. 后端
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. 前端（另开终端）
cd frontend
npm install
npm run dev
```

Windows 下可直接双击 `scripts/start_all.bat` 一键启动。

### 打包成便携版（免安装，双击即用）

想给不使用开发环境的电脑用（答辩现场、拷给同学），执行：

```bash
python scripts/build_portable.py
```

产物在 `release/` 目录：**双击 `AILearningAssistant.exe` 即可运行**，自动启动服务并打开界面；数据保存在 exe 同级的 `data/` 目录，整个文件夹可整体拷贝到其他电脑。详见[打包与发布说明](docs/打包发布说明.md)。

### 配置 AI（可选，有免费方案）

**方式一：在软件里配置（推荐，免改文件）**
打开「AI 助手」页 → 点「配置 API Key」→ 选平台预设 → 粘贴 Key → 保存并生效 → 点「检测 AI 连接」验证。
配置写入程序目录的 `.env` 并**立即生效，无需重启**。

**方式二：手工编辑 `.env`**（复制 `backend/.env.example` 为 `backend/.env`）

三家免费平台任选，代码无需改动：

| 平台 | 免费情况 | AI_BASE_URL | AI_MODEL |
| --- | --- | --- | --- |
| **智谱 GLM（推荐）** | GLM-4-Flash 永久免费，128K 上下文 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| 硅基流动 | 9B 以下模型永久免费 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-7B-Instruct` |
| 阿里云百炼 | 新用户百万级 Token（约 90 天） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| DeepSeek（付费） | 便宜、推理强 | `https://api.deepseek.com` | `deepseek-chat` |

```
AI_API_KEY=你的key
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
AI_MODEL=glm-4-flash
```

不配置也能运行——AI 接口自动降级为本地规则引擎（关键词检索 + 统计分析）。
配置后可通过界面的「检测 AI 连接」或 `POST /api/ai/test` 自检，接口会针对 401/402/404/429 给出具体原因。

## 目录结构

```
ai-learning-assistant/
├── backend/          # FastAPI 后端
│   ├── app/          # 应用代码
│   └── tests/        # pytest 测试
├── frontend/         # Vue3 前端
├── scripts/          # 一键启动脚本
├── docs/             # 设计文档 / 用户手册
└── .github/          # CI、issue/PR 模板
```

## 文档

- [**协作看板**（任务分派与进度，成员每日必看）](docs/协作看板.md)
- [**协作自动化**（任务如何自动通知到人，不用口头转述）](docs/协作自动化.md)
- [贡献指南与代码规范](CONTRIBUTING.md)
- [**项目交接说明**（接手者先读这个）](docs/交接说明.md)
- [项目开发日志（决策与踩坑）](docs/项目开发日志.md)
- [团队分工、协作流程与绩效分配](docs/team.md)
- [打包与发布说明（便携版）](docs/打包发布说明.md)
- [工作量统计（自动生成）](docs/工作量统计.md)
- [原始需求（开题报告）](docs/需求/)
- [设计文档（重构对比）](docs/) —— v2 重构完成后补充 UML 与量化分析

## 团队

| 成员 | 角色 |
| --- | --- |
| 韦俊鑫 | 技术负责人 · 后端与架构 |
| 黄吉航 | 前端负责人 · 测试与文档 |

## 开源许可

[MIT](LICENSE)
