---
description: 检查当前 worktree 的 git-worktree-spec.md 是否存在，读取后依照 spec 内容执行开发任务
---

# 执行 Worktree Feature Spec

## 前置条件

1. 检查当前工作目录根目录是否存在 `git-worktree-spec.md`
   - 若**不存在**：告知使用者此 worktree 没有 spec 档案，询问是否要手动描述需求或中止
   - 若**存在**：继续下一步

## 读取 Spec

2. 读取 `git-worktree-spec.md` 全文内容

3. 解析 Spec 中的以下区块，确认理解任务：
   - **目标**：这个 feature 要达成什么
   - **实作范围**：具体的 checklist 任务
   - **验收标准**：完成后需通过的条件
   - **技术约束**：开发时的限制与惯例
   - **跨分支备注**：是否有相依其他分支的注意事项

## 执行实作

4. 依照 spec 中「实作范围」的 checklist **逐项执行**：
   - 每完成一项任务，更新 `git-worktree-spec.md`，将已完成的 checklist 项目打勾 `[x]`
   - 若遇到模糊不清的任务描述，主动询问使用者而非猜测
   - 遵守「技术约束」中列出的所有限制

## 验收

6. 实作完成后，逐项检查「验收标准」：
   - 能跑测试的就跑测试
   - 能透过 dev server 验证的就启动验证
   - 将验收结果回报给使用者