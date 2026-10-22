# 贡献指南

## 开工前：先看协作看板

**任务分派不走群聊、不走口头，一律以 [`docs/协作看板.md`](docs/协作看板.md) 为准。**

每次开始工作前：

```bash
git checkout develop && git pull    # 先同步
```

然后打开看板，找到你名下的任务：

| 情况 | 你要做的 |
| --- | --- |
| 状态是 `⏳ 待开始`，且已有任务卡链接 | 改成 `🔄 进行中` 并单独提交，然后按任务卡执行 |
| 状态是 `⏳ 待开始`，但写「待下发」 | **不要动手**，需求还没设计完，做了也不合格 |
| 状态是 `🚫 阻塞` | 看「备注」列的阻塞原因，不要重复踩坑 |
| 做完了 | 状态改 `✅ 已完成`，在「交付说明」写清改了哪些文件 + PR 链接 |

改状态单独一个 commit，别和代码混在一起：

```bash
git add docs/协作看板.md
git commit -m "docs: 领取任务 T2"
```

## 代码风格

### Python（后端）

- 遵循 PEP 8；提交前用 `black .`（行宽 100）与 `isort .` 格式化
- 类型注解：公共函数必须带参数与返回类型注解
- 命名：模块/函数 `snake_case`，类 `PascalCase`，常量 `UPPER_CASE`

### JavaScript / Vue（前端）

- ESLint + Prettier 约束；单文件组件 `PascalCase`
- 组件props用 `camelCase`，模板中事件用 `kebab-case`

## Git 提交规范

采用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：

```
<类型>(<范围>): <一句话描述，50 字以内>

[可选正文：说明动机与影响]
```

**类型**：`feat` 新功能 / `fix` 修复 / `docs` 文档 / `style` 格式 / `refactor` 重构 / `test` 测试 / `chore` 构建/工具

**要求**：

1. **单一职责**：一次提交只做一件事，不把多个功能混在一个 commit
2. **中文描述统一用中文**，不中英混用
3. 提交前运行 `black`/`isort`（后端）或 `prettier`（前端），不提交格式化噪音
4. 禁止提交：二进制产物、日志、`node_modules`、数据库文件、密钥（见 `.gitignore`）

## 分支与协作流程

```
master        保护分支，只接受 PR 合入，始终可运行
  └── develop 开发主线，功能分支的合入目标
        ├── feat/xxx   功能分支（从 develop 切出）
        └── fix/xxx    修复分支
```

1. 从 `develop` 切出功能分支：`git checkout -b feat/quiz-generator`
2. 开发并提交（遵循上面的提交规范）
3. 推送后在 GitHub 发起 **PR → develop**，至少 1 人 review 后合入
4. 需求与缺陷用 **issue** 跟踪，commit/PR 关联 issue 编号（如 `feat: 支持PDF导入 (#12)`）

## 测试

后端改动必须通过 `pytest`（在 `backend/` 下运行）：

```bash
python -m pytest -v
```

新增功能须附带测试用例；修复 bug 前先写能复现问题的失败测试。

## 安全

- 任何密钥、token 只放 `.env`（已 gitignore），严禁写进代码或配置提交
- 上传文件大小与类型在服务端校验
