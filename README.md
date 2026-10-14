# AI 智能学习助手

> 面向学习场景的个人智能学习空间：课程资料 → 知识点 → 学习任务 → 练习 → 错题 → AI 分析，形成完整学习闭环。

![status](https://img.shields.io/badge/version-v1.0--naive-blue) ![python](https://img.shields.io/badge/python-3.10+-green) ![node](https://img.shields.io/badge/node-18+-green)

## 功能总览

| 模块 | 子功能 | 说明 |
|------|--------|------|
| 课程资料管理 | 资料导入 / 解析 / 归档 | 支持 PDF、Word、Markdown、TXT 导入，自动提取正文并按课程归类 |
| 知识点管理 | 提取 / 标注 / 关联 | 从资料整理知识点，支持人工补充标注 |
| 学习任务管理 | 制定 / 跟踪 | 按课程与知识点制定任务，跟踪完成状态 |
| 练习与错题 | 练习记录 / 错题本 | 记录练习结果，自动沉淀错题并支持回顾 |
| AI 学习辅助 | 总结 / 答疑 / 薄弱点分析 / 出题 | 基于 DeepSeek API；**未配置 key 时自动降级为本地规则引擎，软件照常可用** |
| 学习记录与统计 | 正确率 / 进度可视化 | 按知识点统计正确率，图表展示掌握情况 |

## 技术栈

- **后端**：Python 3.10+ / FastAPI / SQLite / pytest
- **前端**：Vue 3 + Element Plus + Vite
- **AI**：DeepSeek API（OpenAI 兼容协议，可配置其他兼容供应商）；文档解析 pypdf / python-docx

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

### 配置 AI（可选）

复制 `backend/.env.example` 为 `backend/.env`，填入你的 API key：

```
DEEPSEEK_API_KEY=sk-xxxx
```

不配置也能运行——AI 接口自动降级为本地规则引擎（关键词检索 + 统计分析）。

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

- [贡献指南与代码规范](CONTRIBUTING.md)
- [设计文档（重构对比）](docs/) —— v2 重构完成后补充 UML 与量化分析

## 开源许可

[MIT](LICENSE)
