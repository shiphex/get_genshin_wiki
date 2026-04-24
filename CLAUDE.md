# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

## 项目概述

原神 Wiki 数据爬虫，使用 MediaWiki API。从[哔哩哔哩原神 Wiki](https://wiki.biligame.com/ys/) 爬取数据，用于 RAG/Agent 训练数据集。

**本项目使用 venv 虚拟环境开发，虚拟环境位于 `.get_wiki/` 目录。**

## 现阶段开发计划

现阶段开发计划 @doc\PLAN.md ，将告诉你当前需要完成的开发计划。

当计划完成后：
1. 将 @doc\PLAN.md 中 `## 当前要执行的计划` 的**完整内容原封不动地**移动到 @doc\plan_history.md 的最前面
2. 在 @doc\plan_history.md 中为该计划添加标题，标题格式为 `YYYY-MM-DD_主题_<num>.md`，其中 `<num>` 为该主题的第 num 次任务
3. 将 @doc\PLAN.md 中 `## 当前要执行的计划` 的内容**删除**，只保留 `(暂无)` 或类似占位符

## 方案管理

每次进入 Plan Mode 制定的方案，必须保存到 `doc\plan\` 目录下，文件名需包含日期和主题，例如：`YYYY-MM-DD_主题.md`。

操作指南保存到 `doc\operation_guide\` 目录下。

## 需要爬取的内容

需要爬取的内容 @doc\TARGETS.md ，包括书籍、角色、任务、剧情等。

## 项目架构

项目架构 @doc\ARCHITECTURE.md ，包括目录结构、模块职责、文件组织等。  

计划的架构迭代储存在 `doc\plan` 文件夹下，当前已经迭代到 v1 版本:
``` text
doc\plan\2026-03-27_项目结构整理方案.md
```

## 常用命令

常用命令 @doc\COMMON_COMMANDS.md ，包括进入虚拟环境、安装依赖、运行测试等。


## 测试要求

测试要求 @doc\TEST_REQUIREMENTS.md ，包括测试用例要求、数据完整性验证、运行测试命令等。


## 技术栈

- Python 3.10+，`requests`，`BeautifulSoup`，`mwparserfromhell`，`pyyaml`，`python-dotenv`
- 测试：`pytest`

## 核心约定

- **请求间隔**：每次请求间隔 3 秒
- **错误处理**：捕获具体异常类型，禁止使用裸 `except:`
- **重试逻辑**：对 429/5xx 错误使用指数退避
- **日志**：使用标准库 `logging` 模块

## 数据结构

每条记录包含：`id`、`title`、`url`、`namespace`、`source`、`fetched_at`、`content_raw`、`content_clean`、`categories`、`links`、`templates`、`infobox`、`revision`

原始数据和清洗后数据必须分开存储。

## MediaWiki 爬取规则

1. 优先使用 API 而不是 HTML 爬取
2. 正确处理 `continue` 分页
3. 将 Infobox 数据提取为结构化字段
4. 保留原始 wikitext、模板和内部链接
5. 设置正确的 User-Agent 请求头
6. 遵守 robots.txt 和 API 使用政策

