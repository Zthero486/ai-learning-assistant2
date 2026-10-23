# T1 · 把 fanqie 分支的 README 修复提 PR 合进 develop

**负责人**：黄吉航　**状态**：⏳ 待开始　**优先级**：最高（阻塞 T4/T5 开工）

## 背景

你已经在你自己的 fork（`Zthero486/ai-learning-assistant2`）上提交了 `fix/docs-repo-dir-name` 分支，里面改了 `README.md` 和 `docs/team.md`。这个 commit 现在只存在于你的 fork，**还没有进入主仓库 `qianxingzhigui/ai-learning-assistant2` 的 develop 分支**。

跨 fork 的 Pull Request 只能由 fork 的主人（你）发起，我这边代建会被 GitHub 拒绝（错误码 422 `fork_collab`）。所以要你亲手点几下。

## 动手前：先把你的分支同步到最新 develop

develop 在 2026-10-23 已经前进到 `7f2191d`，`README.md` 被我加过内容。你的分支如果还基于旧的 `707b74a`，PR 会显示 README 冲突。

```bash
git checkout fix/docs-repo-dir-name      # 换成你的实际分支名
git fetch upstream
git rebase upstream/develop
# 有冲突就解决后 git add + git rebase --continue
git push --force-with-lease origin fix/docs-repo-dir-name
```

## 操作步骤

### 第一步：打开对比页

浏览器直接打开这个地址（把分支名替换成你自己的实际分支名）：

```
https://github.com/qianxingzhigui/ai-learning-assistant2/compare/develop...Zthero486:fix/docs-repo-dir-name
```

**确认页面顶部两个下拉框：**

| 位置 | 应该是 |
| --- | --- |
| `base repository` | `qianxingzhigui/ai-learning-assistant2` |
| `base` | `develop` |
| `head repository` | `Zthero486/ai-learning-assistant2` |
| `compare` | `fix/docs-repo-dir-name` |

如果页面提示 **"There isn't anything to compare"**，说明分支名不对或已经被合并过了——截图发我。

### 第二步：创建 PR

1. 点右侧绿色的 **Create pull request**
2. 标题填：

   ```
   docs: 修正仓库目录名并补充提交署名对照表
   ```

3. 描述填：

   ```
   - 修正 README 中的克隆目录名
   - docs/team.md 补充 GitHub 账号与真实姓名对照表

   Closes 无（文档修正，无对应 issue）
   ```

4. 再点一次 **Create pull request**（GitHub 有两步确认，第二次才是真的创建）

### 第三步：等我 review

PR 创建后，我会收到通知并 review + merge。你不需要再做任何操作。

如果 24 小时内 PR 还是 open 状态，直接在群里喊我。

## 验收标准

- [ ] PR 已经在 `qianxingzhigui/ai-learning-assistant2/pulls` 列表里能看到
- [ ] base = `develop`，head = `Zthero486:fix/docs-repo-dir-name`
- [ ] 改动文件只有 `README.md` 和 `docs/team.md`（+13 / -2 左右）

## 常见问题

**Q：点 Compare 后提示 404？**
A：先确认你已经登录 GitHub，且账号是 `Zthero486`。

**Q：分支名忘了？**
A：打开 `https://github.com/Zthero486/ai-learning-assistant2/branches`，看列表里 `fix/` 开头的分支。

**Q：能不能我直接 push 到主仓库？**
A：可以，但需要你先被加为 collaborator（这一步可能还没做）。走 PR 更稳，而且 PR 记录是评分里「协作痕迹」的直接证据，别省。
