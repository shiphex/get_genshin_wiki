# get_genshin_wiki

> README 版本：`V2.0.0`
>
> 本仓库为 V2 重构版，定位为“原神 Wiki 数据抓取 + 解析 + 本地 JSON 存储”工具集。

## 项目简介

本项目面向 bilibili 原神 Wiki（`https://wiki.biligame.com/ys/`），提供：

- MediaWiki API 抓取
- WikiText 解析
- 结构化 JSON 落盘
- 分类级、单页级、批处理级数据获取流程

当前代码已经支持的主要数据族包括：

- 角色
- 武器
- 圣遗物套装
- 怪物
- 书籍
- 食物
- 野生生物
- 任务道具
- 道具
- 材料
- 名片
- 秘境
- 提瓦特编年史
- 北陆图书馆
- 活动任务
- 魔神任务
- 角色传说任务 / 部族纪闻

## 核心特性

- 统一 CLI 入口：`python main.py`
- 通用抓取命令：`crawl categories / members / page / category-pages`
- 通用解析命令：`parse <type> <title>`
- 本地命名空间存储：`data/pages`、`data/parsed/...`
- 支持批处理脚本、索引生成与抽样验证
- 默认遵守 `robots.txt`，并带有限流与重试策略

## 快速开始

### 环境准备

```powershell
cd E:\Workplace\Learn_project\get_genshin_wiki
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

查看帮助：

```powershell
python main.py --help
python main.py crawl --help
python main.py parse --help
python main.py store --help
```

### 获取单个页面

以武器 `霜结的誓金枝` 为例：

```powershell
python main.py crawl page "霜结的誓金枝"
python main.py parse weapon "霜结的誓金枝"
```

以角色 `哥伦比娅` 为例：

```powershell
python main.py crawl page "哥伦比娅"
python main.py crawl page "哥伦比娅语音"
python main.py parse character "哥伦比娅"
```

### 获取某一类数据

以 `武器` 分类为例：

```powershell
python main.py crawl category-pages "武器"
$titles = python main.py store query category_members "武器" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py parse weapon $title | Out-Null
}
```

### 获取批量任务数据

魔神任务：

```powershell
python tools/batch_archon_quests.py
python tools/generate_archon_quest_index.py
```

角色传说任务 / 部族纪闻：

```powershell
python tools/batch_character_quests.py
python tools/generate_character_quest_index.py
```

## 主要命令

### `crawl`

当前支持：

- `categories`
- `members`
- `page`
- `category-pages`
- `north-library`
- `chronicle-pages`
- `event-quests`

### `parse`

当前支持：

- `page`
- `chronicle`
- `character`
- `archon-quest`
- `event-quest`
- `weapon`
- `artifact`
- `monster`
- `food`
- `wildlife`
- `quest-item`
- `item`
- `material`
- `namecard`
- `secret-item`
- `book`

### `store`

当前支持：

- `put`
- `query`
- `update`
- `add`
- `delete`
- `exists`
- `list`

## 文档入口

- 统一操作指南：`doc/guide/unified_operation_guide.md`
- 项目架构说明：`doc/project_architecture.md`
- 分项指南：`doc/guide/*.md`
- 历史 worktree 记录：`doc/worktree_logs/*.md`

如果分项文档与统一指南冲突，以 `doc/guide/unified_operation_guide.md` 为准。

## 目录结构

```text
get_genshin_wiki/
├─ main.py
├─ README.md
├─ CLAUDE.md
├─ pyproject.toml
├─ data/
├─ doc/
│  ├─ guide/
│  ├─ project_architecture.md
│  └─ worktree_logs/
├─ get_genshin_wiki/
│  ├─ cli.py
│  ├─ client.py
│  ├─ crawler.py
│  ├─ parser.py
│  └─ storage.py
├─ tools/
├─ tests/
└─ refer/
```

## 数据输出

常见输出位置：

- 原始页面：`data/pages/`
- 分类成员：`data/category_members/`
- 通用解析结果：`data/parsed/pages/`
- 角色：`data/parsed/characters/`
- 武器：`data/parsed/weapons/`
- 圣遗物套装：`data/parsed/artifacts/`
- 怪物：`data/parsed/monsters/`
- 书籍：`data/parsed/books/`
- 食物：`data/parsed/foods/`
- 野生生物：`data/parsed/wildlife/`
- 任务道具：`data/parsed/quest-items/`
- 道具：`data/parsed/items/`
- 材料：`data/parsed/materials/`
- 名片：`data/parsed/namecards/`
- 秘境：`data/parsed/secret-items/`
- 编年史：`data/parsed/chronicles/`
- 北陆图书馆：`data/parsed/north-library/`
- 活动任务：`data/parsed/event-quests/`
- 魔神任务：`data/parsed/archon-quests/`
- 角色传说任务 / 部族纪闻：`data/parsed/character-quests/`
- 报告：`data/reports/`

## 当前状态

当前仓库的实现重点已经从“单一角色原型”转向“多实体、多脚本入口”的 V2 结构。

已知现状与限制：

- `python main.py` 是当前最稳妥的统一入口。
- 仓库当前没有 `get_genshin_wiki/__main__.py`，因此 `python -m get_genshin_wiki` 不是有效入口。
- `parse character` 会尝试读取本地 `"<角色名>语音"` 页面，但不会自动联网补抓。
- `parse archon-quest` 在存在 `魔神任务` 列表页时，章节上下文更完整。
- 活动任务当前没有专门的“全量批解析脚本”。
- `character-quest` 当前没有 CLI 级解析子命令，单页调试依赖 Python API。

## 测试状态

仓库已经包含 `client / crawler / parser / storage / cli / tools` 对应测试。

按当前工作树实际情况，`pytest -q` 还不是全绿：

- `tests/test_cli.py` 存在语法错误
- `tests/test_batch_tools.py` 会被该问题连带影响

因此，当前 README 将项目描述为“具备测试体系”，而不是“测试已全部通过”。

## 约束

- 抓取逻辑必须遵守目标站点 `robots.txt`
- 文档与命令说明以当前代码实现为准
- `refer/` 目录仅作参考，不作为生产接口
