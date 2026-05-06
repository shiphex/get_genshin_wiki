# 项目架构设计

## 1. 目标

本项目用于从 `https://wiki.biligame.com/ys/` 获取原神 Wiki 数据，并将原始页面与结构化结果落盘，供后续大模型训练、微调和数据清洗使用。

核心约束：

- 遵循 `robots.txt`
- 通过 `MediaWiki API` 获取分类、分类成员和页面内容
- 通过 `mwparserfromhell` 解析 WikiText
- 基础能力与业务解析解耦，便于后续扩展到武器、任务、圣遗物等实体

## 2. 目录结构

```text
get_genshin_wiki/
├─ doc/
│  └─ project_architecture.md
├─ get_genshin_wiki/
│  ├─ __init__.py
│  ├─ cli.py
│  ├─ client.py
│  ├─ config.py
│  ├─ crawler.py
│  ├─ exceptions.py
│  ├─ models.py
│  ├─ parser.py
│  └─ storage.py
├─ tests/
│  ├─ helpers.py
│  ├─ test_client.py
│  ├─ test_crawler.py
│  ├─ test_parser.py
│  └─ test_storage.py
├─ main.py
├─ CLAUDE.md
├─ TODO.md
└─ pyproject.toml
```

## 3. 分层设计

### 3.1 基础设施层

- `config.py`
  - 默认 API 地址、用户代理、超时、限速参数
- `exceptions.py`
  - 网络异常、解析异常、`robots.txt` 拒绝等统一异常
- `models.py`
  - 页面、解析结果、请求策略等数据模型
- `storage.py`
  - 本地 JSON 存储，负责增删查改与文件命名规整

### 3.2 平台接入层

- `client.py`
  - MediaWiki API 访问封装
  - `robots.txt` 检查
  - 分页处理
  - 页面正文抽取

### 3.3 业务编排层

- `crawler.py`
  - 按分类抓取成员
  - 按标题抓取页面
  - 将原始数据落盘到本地存储

### 3.4 数据解析层

- `parser.py`
  - 通用模板聚合
  - 分类、简介、章节抽取
  - 角色页面解析
  - 后续可扩展武器、任务、圣遗物专用解析器

### 3.5 交互入口层

- `cli.py`
  - 命令行触发分类抓取、页面抓取、解析任务
- `main.py`
  - 统一入口，便于直接运行

## 4. 爬虫模块设计

`client.py` 与 `crawler.py` 共同组成爬虫模块。

### 4.1 MediaWikiClient 职责

- 读取并校验 `robots.txt`
- 发送 API 请求并统一附带请求头
- 处理 `allcategories` 分页
- 处理 `categorymembers` 分页
- 获取指定页面的 `revisions` 内容
- 将 MediaWiki 原始响应转换为 `WikiPage`

### 4.2 WikiCrawler 职责

- 抓取并保存分类列表
- 抓取并保存分类成员列表
- 抓取并保存页面原始 JSON
- 将“远程抓取”与“本地落盘”解耦，便于单测替换 client/store

### 4.3 反爬与可靠性策略

- 默认限速，避免短时间高频请求
- 请求超时与可配置重试次数
- 任何线上请求前先检查 `robots.txt`
- API 返回结构异常时抛出明确异常，不静默吞错

## 5. 数据解析模块设计

`parser.py` 负责从页面原始 JSON 中提取结构化信息。

### 5.1 通用解析输出

- 页面标题
- 原始 WikiText
- 简介纯文本
- 所有模板及其参数
- 页面分类
- 正文章节列表

### 5.2 角色解析输出

- 角色标题
- 角色主信息模板参数
- 技能/天赋模板参数集合
- 命座模板参数集合
- 页面分类
- 简介与章节文本

### 5.3 设计原则

- 先做“通用解析”，再做“实体专用解析”
- 模板名称匹配使用关键字规则，避免对单一模板名强绑定
- 保留原始模板结果，避免因为解析规则不足导致信息丢失

## 6. 数据存储设计

当前阶段采用本地 JSON 文件存储，原因：

- 结构简单，便于审计与回放
- 适合抓取原始数据与解析中间产物
- 对训练数据预处理友好

存储命名空间：

- `data/categories/`
  - 分类列表，如全量分类或带前缀的分类结果
- `data/category_members/`
  - 分类对应的成员标题列表
- `data/pages/`
  - 原始页面 JSON
- `data/parsed/pages/`
  - 通用页面解析结果
- `data/parsed/characters/`
  - 角色结构化结果

文件名使用“原始标题 + 摘要哈希”模式，避免中文标题中的非法文件名字符和重名冲突。

`storage.py` 提供以下操作：

- `write`
- `read`
- `exists`
- `list_keys`
- `delete`

这满足“新增、查询、更新、删除”的最小存储需求。后续如需大规模检索，可在此层替换为 SQLite 或对象存储，而不影响上层逻辑。

## 7. 测试方案

测试目标：核心模块覆盖率达到 90% 以上。

测试策略：

- `test_client.py`
  - 分类分页
  - 分类成员分页
  - 页面正文抽取
  - `robots.txt` 拒绝场景
- `test_storage.py`
  - 写入、读取、删除、列举
  - 非法文件名规整
- `test_parser.py`
  - 通用模板聚合
  - 分类与章节提取
  - 角色模板解析
- `test_crawler.py`
  - 抓取编排与持久化调用

测试原则：

- 单测全部使用离线假响应，不依赖真实网络
- 关键解析逻辑使用接近 MediaWiki 实际结构的 fixture
- 对边界情况做显式断言：空页面、无模板页面、缺失 revisions、重复模板

## 8. 端到端数据流

1. `MediaWikiClient` 校验 `robots.txt`
2. 获取分类列表或分类成员
3. `WikiCrawler` 将原始响应落盘
4. 获取具体页面原始 JSON
5. `WikiTextParser` 解析出通用页面结构
6. `CharacterPageParser` 在通用结果基础上提取角色结构化字段
7. 将解析结果落盘供后续训练管道消费

## 9. 后续扩展

- 新增武器、任务、圣遗物专用解析器
- 增加批量抓取入口与断点续抓能力
- 补充数据去重、清洗与训练样本导出模块
- 若数据量增大，将 `storage.py` 适配 SQLite/Parquet
