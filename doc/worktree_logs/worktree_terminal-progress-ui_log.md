# 功能规范：轻量终端进度 UI

> 本文档在 worktree 设置期间生成，用于指导本分支的实现。

## 分支信息

| 项目 | 值 |
|------|------|
| 分支名 | `feature/terminal-progress-ui` |
| 基础分支 | `develop/v2.2` (`fb80155`) |
| Worktree 路径 | `E:\Workplace\Learn_project\get_genshin_wiki-terminal-progress-ui` |
| 创建时间 | `2026-06-15` |

## 目标

为 `python main.py all` 和 `python main.py all <entity>` 添加轻量终端显示，展示：

- 当前正在执行的项目
- 已完成的项目
- 执行进度
- 待处理的项目

UI 必须保持轻量，避免复杂的终端库，并保留现有的机器可读命令输出。

## 实现范围

- [x] 设计进度事件模型，所有 `all` 运行器均可触发该事件
- [x] 添加轻量终端渲染器，在交互式终端上重绘紧凑仪表盘
- [x] 保持最终 JSON 输出在 `stdout`，进度 UI 在 `stderr`
- [x] 在共享循环（如 `_run_all_title_pipeline()` 和顶层 `handle_all_everything()`）中植入事件
- [x] 使用相同的进度模型覆盖特殊运行器（`characters`、`event-quests`、`chronicles`、`north-library`、`archon-quests`、`character-quests`）
- [x] 显示各实体和顶层的进度计数、当前阶段、当前标题、最近完成项以及剩余项预览
- [x] 为非交互式 shell、重定向输出和不支持 ANSI 的终端添加安全降级行为
- [x] 记录该行为及任何控制标志

## 验收标准

- `python main.py all` 显示实时顶级进度，不破坏最终 JSON 输出
- `python main.py all weapons` 显示当前项、已完成项、总进度和待处理标题
- 非 TTY 使用保持脚本友好，不在 `stdout` 上产生仪表盘噪音
- 失败和跳过/恢复的项在进度输出中可见
- 实现不添加 `rich`、`textual` 或其他重型 UI 依赖

## 技术约束

- 优先使用标准库方案，借助 ANSI 转义序列和行重写
- 仅在状态变化或较粗的时间间隔刷新
- 保持渲染器与抓取/解析业务逻辑隔离
- 除非有必要增加最小的 opt-in 或 opt-out 标志，否则保留现有命令签名

## 跨分支说明

- 独立于 `feature/llm-data-format`
- 预计接触点：`get_genshin_wiki/cli.py`、小型辅助模块、文档和测试
- 合并顺序灵活，因为本分支不依赖于解析 JSON 的重设计
