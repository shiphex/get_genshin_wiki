# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

## 项目概述

原神 Wiki 数据爬虫，使用 MediaWiki API。从[哔哩哔哩原神 Wiki](https://wiki.biligame.com/ys/) 爬取数据，用于 RAG/Agent 训练数据集。

**本项目使用 venv 虚拟环境开发，虚拟环境位于 `.get_wiki/` 目录。**

## 常用命令

```bash
# 进入虚拟环境
source .get_wiki/Scripts/activate  # Linux/Mac
# 或
.get_wiki\Scripts\activate  # Windows

# 安装依赖
uv pip install -e ".[dev]"

# 运行测试
pytest

# 运行单个测试文件
pytest tests/test_book_parser.py
```

## 项目架构

```
src/
├── crawler/     # MediaWiki API 客户端，页面获取，分页处理
├── parser/      # Wikitext/HTML 解析
├── cleaner/     # 文本清洗与标准化
├── storage/     # JSONL/SQLite 存储
├── schema/      # 数据模型
├── utils/       # 配置、日志、限速
└── old_file/    # 旧版文件，已经废弃
doc/
├── plan/        # 开发方案和计划文档
└── operation_guide/  # 操作指南
tests/
└── output/      # 测试产生的临时文件
```

## 测试要求

### 临时文件管理

测试过程中生成的临时文件（如 HTML 页面、JSON 数据等）必须保存到 `tests/output/` 目录，不得留在项目根目录。

### 测试用例要求

- **解析器测试**：每类数据（书籍/角色/任务/剧情等）必须有对应的解析器测试文件，命名格式 `tests/test_*_parser.py`
- **测试覆盖**：单元测试覆盖 HTML 解析、数据模型转换、字段提取
- **回归测试**：修改解析逻辑后运行 `pytest` 确保不破坏已有功能

### 数据完整性验证

- 爬取后检查 JSONL 条目数量是否符合预期
- 验证必填字段（`title`、`url`、`fetched_at`、`content`）非空
- 检查重复条目并去重

### 运行测试命令

```bash
pytest                              # 运行所有测试
pytest tests/test_book_parser.py    # 运行书籍解析器测试
pytest tests/test_*parser*.py        # 运行所有解析器测试
```

## 方案管理

每次进入 Plan Mode 制定的方案，必须保存到 `doc/plan/` 目录下，文件名需包含日期和主题，例如：`YYYY-MM-DD_主题.md`。

操作指南保存到 `doc/operation_guide/` 目录下。

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

## 需要爬取的内容

### 游戏内书籍及内容

- 书籍列表所在网页[书籍一览](https://wiki.biligame.com/ys/%E4%B9%A6%E7%B1%8D%E4%B8%80%E8%A7%88)
- 每本书的详情页，如[终北祷歌集](https://wiki.biligame.com/ys/%E7%BB%88%E5%8C%97%E7%A5%B7%E6%AD%8C%E9%9B%86)，该网页链接在'书籍一览'中可以找到
- 获取书籍内容（包括每卷的标题，每卷的文本）：
  - 每卷的标题都存在于网页代码如`<span class="mw-headline" id="终北祷歌集">终北祷歌集</span></h2>`
  - 每卷的文本都存在于每卷的标题的网页代码的后面的段落中，可能有好几段
  - **保留换行格式**：HTML 中的 `<br />` 标签代表诗歌的换行，`<p>` 标签代表段落。解析时应将 `<br />` 转换为 `\n`，将段落用 `\n\n` 分隔
- 获取书籍的相关信息：
  - 名称
  - 卷数
  - 稀有度
  - 体裁
  - 国家
  - 实装版本
  - 图鉴
  - 相关角色
  - 获取方式（请抓取全部卷的获取方式）
    - **获取方式解析方法**：从书籍详情页的 Infobox（`<table class="wikitable boxright">`）中提取，每卷的获取方式在卷名标题后的 `<td>` 单元格中
    - 各卷获取方式汇总格式：`"卷名1: 获取方式1; 卷名2: 获取方式2; ..."`

获取到的书籍内容保存到 `storage/book/` 文件夹下

### 待扩展内容（规划中）

- **角色**：角色一览、角色详情页（含立绘、语音、故事等）
- **任务**：任务一览、任务详情页（含任务流程、奖励等）
- **剧情**：剧情文本、对白内容

扩展时请参考 `doc/plan/` 下的对应方案文档和 `doc/operation_guide/` 下的操作指南。