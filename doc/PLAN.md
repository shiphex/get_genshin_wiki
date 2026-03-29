# PLAN.md

本文件为当前开发调试的短期计划。

## 当前要执行的计划
目前武器爬取工作已经阶段性完成，当前需要对该阶段工作做出归纳总结：
- 对不规范的输出文件进行整理
  - 将`scripts\tests`路径下文件统一到`tests\output`中
  - 对未按 @doc\TEST_REQUIREMENTS.md 中`### 临时文件管理`要求的文件进行整理的原因进行说明，并给出改进方案
- 按照 @CLAUDE.md 中`## 方案管理`条目要求，归纳整理新版本武器爬取方案、操作指南，参考：
  - 重点参考 @doc\TARGETS.md 中`## 武器爬取目标（已经完成）`条目
  - 重点参考`doc\target\crawl_arms.md`文件
  - 重点参考武器爬取相关代码
  - 另可参考 `doc/plan/` 下的对应方案文档和 `doc/operation_guide/` 下的操作指南
- 按照 @CLAUDE.md 中`## 项目架构`条目要求，参考当前`doc\ARCHITECTURE.md`，更新 @doc\ARCHITECTURE.md 中的项目架构图，要求：
  - 浏览项目文件架构，更新项目架构图中的武器爬取相关模块设计
  - 无需生成新的项目整理方案
- 按照 @CLAUDE.md 中`## 常用命令`条目要求，更新 @doc\COMMON_COMMANDS.md 中的常用命令，要求：
  - 参考 @doc\COMMON_COMMANDS.md 中`## 书籍爬取命令`添加武器爬取命令索引
  - 无需在 @doc\COMMON_COMMANDS.md 中书写命令

注意： @CLAUDE.md 文件是为Claude Code在本仓库中工作时提供指导的文档，在开发过程中除特殊要求外，严格按照该文件中的要求进行开发。