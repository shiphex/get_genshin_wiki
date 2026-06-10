# 项目架构设计

## 1. 项目定位

本项目用于从 `https://wiki.biligame.com/ys/` 抓取原神 Wiki 页面，并将页面原始 payload 与结构化解析结果落盘到本地 `data/` 目录，供后续训练数据整理、检查与下游消费使用。

当前仓库已经从“通用骨架”演进为“多数据族并行支持”的实现，重点不再只是角色，而是同时覆盖：

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

“全部数据”在当前语境下，指上面这些已经有代码支持的类型，而不是历史规划中过的全部 Wiki 类别。

## 2. 当前目录结构

```text
get_genshin_wiki/
├─ CLAUDE.md
├─ README.md
├─ TODO.md
├─ main.py
├─ pyproject.toml
├─ uv.lock
├─ data/
│  ├─ category_members/
│  ├─ pages/
│  ├─ parsed/
│  └─ reports/
├─ doc/
│  ├─ guide/
│  │  ├─ unified_operation_guide.md
│  │  └─ *.md
│  ├─ project_architecture.md
│  ├─ todo_logs.md
│  └─ worktree_logs/
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
├─ refer/
│  └─ *.py
├─ tests/
│  └─ *.py
└─ tools/
   └─ *.py
```

说明：

- `doc/guide/` 下保留了分项指南；`doc/guide/unified_operation_guide.md` 是新的统一入口。
- `doc/worktree_logs/` 记录历史 worktree 的开发日志，适合追溯背景，不应再作为当前命令入口文档。
- `refer/` 是参考实现与探索脚本，不是生产代码路径。

## 3. 运行时分层

### 3.1 配置与异常

- `config.py`
  - 定义默认 API 地址、User-Agent、超时、限流、重试次数、默认 `data/` 根目录。
- `exceptions.py`
  - 定义网络失败、页面缺失、`robots.txt` 禁止访问等异常类型。

### 3.2 平台接入层

- `client.py`
  - 封装 MediaWiki API 访问。
  - 负责 `robots.txt` 校验、分页拉取、请求限流、重试、页面原始 payload 获取。
  - 额外提供 `fetch_rendered_section_titles()`，用于部分任务页的模板展开辅助。

### 3.3 编排层

- `crawler.py`
  - 将远程抓取与本地持久化组合起来。
  - 提供通用能力：`crawl_categories`、`crawl_category_members`、`crawl_page`、`crawl_category_pages`。
  - 提供专项探测/抓取能力：
    - `discover_event_quest_category`
    - `discover_character_quest_categories`
    - `crawl_chronicle_pages`
    - `crawl_north_library`

### 3.4 解析层

- `parser.py`
  - `parse_page()` 提供通用页面解析：标题、摘要、模板、分类、章节。
  - 在通用解析之上派生实体专用解析：
    - `parse_character_page`
    - `parse_weapon_page`
    - `parse_artifact_set_page`
    - `parse_monster_page`
    - `parse_food_page`
    - `parse_wildlife_page`
    - `parse_quest_item_page`
    - `parse_item_page`
    - `parse_material_page`
    - `parse_namecard_page`
    - `parse_secret_item_page`
    - `parse_book_page`
    - `parse_chronicle_page`
    - `parse_event_quest_page`
    - `parse_archon_quest_page`
    - `parse_character_quest_page`
    - `parse_north_library_page`

### 3.5 存储层

- `storage.py`
  - `JsonFileStore` 是当前唯一持久化实现。
  - 按命名空间写入 JSON 文件。
  - 文件名采用 `{规范化标题}__{sha1前10位}.json`，避免中文标题重名与非法字符问题。
  - 提供 `write/read/update/add/exists/delete/list_keys/resolve_path`。

### 3.6 CLI 与批处理入口

- `main.py`
  - 当前最稳妥的统一 CLI 入口，直接转发到 `get_genshin_wiki.cli:main`。
- `get_genshin_wiki/cli.py`
  - 提供三组命令：
    - `crawl`
    - `parse`
    - `store`
- `tools/*.py`
  - 承担“全量批处理”“索引生成”“验证报告”职责，是当前仓库的重要一等入口，而不是辅助脚本。

## 4. 命令面与能力边界

### 4.1 通用 CLI 能力

`crawl` 子命令：

- `categories`
- `members`
- `page`
- `category-pages`
- `north-library`
- `chronicle-pages`
- `event-quests`

`parse` 子命令：

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

`store` 子命令：

- `put/query/update/add/delete/exists/list`

### 4.2 批处理脚本

- `tools/crawl_reparse_all.py`
  - 适用于 `characters/weapons/artifacts/monsters/books/foods/wildlife/quest-items/items/materials/namecards/secret-items`
  - 负责抓取、重解析、验证，并附带跑测试。
- `tools/parse_all_categories.py`
  - 对已存在的本地页面做离线重解析与验证。
- `tools/crawl_validate_characters.py`
  - 针对角色的抓取、解析与完整性报告。
- `tools/batch_archon_quests.py`
  - 批量抓取并解析魔神任务。
- `tools/generate_archon_quest_index.py`
  - 生成魔神任务独立索引。
- `tools/batch_character_quests.py`
  - 批量抓取并解析角色传说任务 / 部族纪闻。
- `tools/generate_character_quest_index.py`
  - 生成角色传说任务独立索引。

### 4.3 当前边界

- `character-quest` 目前没有 CLI 级 `parse` 子命令，只能通过批处理脚本或 Python API 解析。
- 活动任务目前有 `crawl event-quests` 与 `parse event-quest`，但没有专用“全量批解析”脚本。
- 提瓦特编年史当前有主页面自动探测能力，但“国家/地区编年史全量抓取”仍依赖显式标题列表。
- 北陆图书馆当前通过 `crawl north-library` 一步完成抓取与解析，没有单独的 `parse north-library` 命令。

## 5. 数据流

### 5.1 标准实体数据流

适用于武器、圣遗物套装、怪物、书籍、食物、野生生物、任务道具、道具、材料、名片、秘境：

1. `crawl members <分类>`
2. `crawl category-pages <分类>` 或逐页 `crawl page <标题>`
3. `parse <类型> <标题>`
4. 结果写入 `data/parsed/<namespace>/`

### 5.2 上下文相关数据流

- 角色
  - 除主页面外，通常还需要 `<角色名>语音` 页面。
- 魔神任务
  - 为获得更稳定的章节/幕上下文，通常要保留 `魔神任务` 列表页。
- 活动任务
  - 任务页常依赖活动主页补全活动名称、活动期间、活动列表。
- 角色传说任务 / 部族纪闻
  - 依赖列表页 `传说任务` 与分类探测结果构造系列上下文。

## 6. 存储命名空间

当前仓库会实际使用到的主要命名空间包括：

- `categories/`
- `category_members/`
- `pages/`
- `chronicle_meta/`
- `parsed/pages/`
- `parsed/chronicles/`
- `parsed/characters/`
- `parsed/archon-quests/`
- `parsed/archon-quest-index/`
- `parsed/character-quests/`
- `parsed/character-quest-index/`
- `parsed/event-quests/`
- `parsed/weapons/`
- `parsed/artifacts/`
- `parsed/monsters/`
- `parsed/foods/`
- `parsed/wildlife/`
- `parsed/quest-items/`
- `parsed/items/`
- `parsed/materials/`
- `parsed/namecards/`
- `parsed/secret-items/`
- `parsed/books/`
- `parsed/north-library/`
- `reports/`

## 7. 测试与当前状态

测试分布在：

- `tests/test_client.py`
- `tests/test_crawler.py`
- `tests/test_parser.py`
- `tests/test_storage.py`
- `tests/test_cli.py`
- `tests/test_batch_*.py`
- `tests/test_generate_*.py`

当前代码库的测试目标已经从基础 CRUD 扩展到：

- CLI 命令行为
- 专项解析器输出
- 批处理脚本
- 索引生成

按 2026-06-10 在当前仓库执行 `pytest -q` 的结果，测试尚未完全可运行：`tests/test_cli.py` 存在语法错误，进而导致 `tests/test_batch_tools.py` 在收集阶段失败。也就是说，文档应以“测试体系存在，但当前工作树测试并非全绿”来描述现状，而不是继续假定测试已经稳定通过。

## 8. 当前规范与文档入口

- 优先使用 `python main.py` 编写命令示例，避免再写旧 worktree 专用路径。
- 如需说明全量处理流程，优先引用 `tools/*.py` 的真实能力，而不是假定所有实体都能用同一个批处理脚本。
- 新增或更新分项能力时，应同步更新：
  - `doc/guide/unified_operation_guide.md`
  - `doc/project_architecture.md`
  - `CLAUDE.md`

## 9. 已知不一致与后续关注点

- 旧分项指南中仍残留历史 worktree 路径、旧入口和已过时命令示例。
- `python -m get_genshin_wiki` 目前不是有效入口，因为仓库内没有 `get_genshin_wiki/__main__.py`。
- 活动任务、编年史、北陆图书馆在“全量自动化”程度上低于标准实体。
- `TODO.md` 当前聚焦秘境解析验收，说明项目仍处于持续补齐与校验阶段。
