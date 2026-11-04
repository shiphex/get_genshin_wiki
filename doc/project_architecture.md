# 项目架构设计

对应发布版本：V2.2.0。操作入口以 [统一指南](guide/unified_operation_guide.md) 和 [离线恢复指南](guide/snapshot_recovery_guide.md) 为准。

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
│  ├─ recovery/
│  └─ reports/
├─ doc/
│  ├─ guide/
│  │  ├─ unified_operation_guide.md
│  │  └─ *.md
│  ├─ project_architecture.md
│  ├─ reports/
│  ├─ releases/
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
│  ├─ recovery/
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

### 实体版本与离线更新

`versions.py` 提供共享主体版本提取与规范化，返回值、状态及原文位置证据。解析器将其接入所有主体模型，序列化时仅在实体根对象输出 `所属版本`；角色普通/精简格式均支持，子记录不增加属性。提取优先使用主体模板参数，对已识别的损坏查询语法支持受限原文参数回退；缺失和歧义不推断。

`tools/refresh_parsed_offline.py` 负责冻结本地原始缓存、按现有命名空间重解析和维护任务汇总。它复用 `offline_guard` 和 `run_recovery`，在互不嵌套的暂存目录中生成两次完整恢复并校验确定性；版本之外的业务变化及旧恢复文本/分支差异会阻断应用。验证后备份并替换正式业务及 `recovery/full-offline-20261104`，检查并发修改、支持失败回滚，不触及其他恢复实验或历史 ZIP。

对经确认的旧业务滞后，刷新工具可显式读取带输入指纹、解析器来源和文件哈希的独立业务基线，仅接受与其完全一致的非版本变化；逐项记录完整差异。逐目标替换后核对原目标哈希，最终原始缓存和恢复清单验收也位于回滚事务内。

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
  - 提供四组命令：
    - `crawl`
    - `parse`
    - `all`
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

`all` 子命令：

- `weapons`
- `artifacts`
- `monsters`
- `books`
- `foods`
- `wildlife`
- `quest-items`
- `items`
- `materials`
- `namecards`
- `secret-items`
- `characters`
- `event-quests`
- `chronicles`
- `north-library`
- `archon-quests`
- `character-quests`

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
- `tools/recover_snapshot.py`
  - 只读加载冻结页面和缓存依赖，生成新的来源、场景、分支、候选节点和问题清单；不创建在线抓取运行时。

### 4.3 当前边界

- `character-quest` 目前仍没有 CLI 级 `parse` 子命令，但已经有 `python main.py all character-quests` 统一全量入口。
- 活动任务现在同时具备 `crawl event-quests` / `parse event-quest` 单页链路，以及 `python main.py all event-quests` 全量入口。
- 提瓦特编年史现在有 `python main.py all chronicles` 全量入口；其实现仍基于内置标题列表，而不是动态枚举全部国家/地区页。
- 北陆图书馆现在同时支持 `crawl north-library` 与 `python main.py all north-library`，两者共用同一条抓取 + 解析逻辑；当前仍没有独立 `parse north-library` 命令。

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

V2.2.0 已修复原有 CLI 测试的导入语法错误。发布验证基线为 122 passed / 18 subtests passed，包含 19 份真实冻结页面、来源位置、分支、缓存可见性、独立候选节点清单与离线边界测试；当前结果以实际执行 `python -m pytest -q` 为准。

## 8. 当前规范与文档入口

- 优先使用 `python main.py` 编写命令示例，避免再写旧 worktree 专用路径。
- 如需说明在线全量处理流程，优先使用 `python main.py all <entity>`，并解释各实体不同的上下文依赖；冻结来源恢复使用独立的离线入口。
- 新增或更新分项能力时，应同步更新：
  - `doc/guide/unified_operation_guide.md`
  - `doc/project_architecture.md`
  - `CLAUDE.md`

## 9. 已知不一致与后续关注点

- 历史 worktree 日志只记录当时实现，当前操作以统一指南和对应分项指南为准。
- `python -m get_genshin_wiki` 目前不是有效入口，因为仓库内没有 `get_genshin_wiki/__main__.py`。
- 活动任务、编年史、北陆图书馆已有 `all` 入口，但分别依赖关联主页、内置标题列表和固定入口页，并非动态覆盖全部 Wiki 页面。
- `TODO.md` 当前聚焦秘境解析验收，说明项目仍处于持续补齐与校验阶段。
## 来源追踪与离线恢复

`get_genshin_wiki/recovery/` 提供原文节点偏移、确定性显示规则、场景/分支提取、业务兼容投影及独立候选节点校验。`WikiTextParser.recover_page` 是来源提取 API；任务业务解析器复用该提取后生成兼容数组。

`tools/recover_snapshot.py` 只读加载冻结 payload 和本地依赖，使用 JsonFileStore 写新的派生目录。权威文本为 `text_units.jsonl`，其字符范围基于原始解码 WikiText；独立校验器不调用被测正文提取逻辑。接口与边界见 [离线恢复指南](guide/snapshot_recovery_guide.md)。

角色任务的业务模型保留展示名称，并增加 `source_title`、`page_id`。独立批处理、索引与离线恢复按完整原标题及身份处理存储和引用，批处理 resume 会重新解析缺少身份的旧汇总，组索引提供 `task_refs`。统一 CLI 的 `all character-quests` 仍按展示名处理存储、去重及 resume；它只复用部分辅助函数，尚未同步批处理的身份修复。

离线输出和既有 raw / parsed 分开保存；已导出单元可重放不代表所有原文都已支持。未知节点、缺依赖、媒体文字和未解决分支仍进入机器清单，不调用模型猜测或补写。

### 折叠剧情与换行边界

任务业务入口（魔神、角色、活动）使用 `recovery/extract.py` 读取原始 AST，
递归进入 `折叠` / `折叠框` 的 `内容` 或第二位置参数，再通过 `recovery/legacy.py`
生成原有字段。不要将 `parse_sections()` 的 `strip_code()` 纯文本结果作为剧情权威来源，
也不要重新接回只展开选项模板的旧 `_extract_archon_dialogues()` 路径。

对话中的顶层 `<br>` 产生候选片段，分别识别显式说话者；无标记片段保留为 narration，
并记录 `unattributed_break_fragment`。列表项中未重新标记说话者的换行沿用列表项范围；
人物对话模板的显式角色参数和单条台词内的显示标签同样限定内容范围。
整段对白被 HTML 包装时只在逻辑行起点进入容器，避免把台词中的冒号重新识别为人名。

业务投影保留有有效文本的章节前导场景；任务描述模板和章节前导引用仍为 description，
不生成额外任务流程。剧情区域外的折叠内容保留为 description 并记录 `fold_outside_story`，
不凭冒号推断角色。诊断通过 `recover_page()['issues']` 获取，不增加业务 JSON 字段。

剧情标题支持“后续剧情”等前缀变体；已处于剧情区时，更深的“与某人对话”标题是任务流程，
不会重新设置父剧情边界。具有明细、账目、日志、留言、档案等文档语境的折叠按旁白保存，
保留冒号前后的全文；冒号后为空的行也回退旁白并产生 `empty_speech_after_colon` 诊断。

台词中附着的黑幕从业务台词分离，在恢复 API 中保存为 `annotation`。主单元的
`excluded_spans` 标明排除的原文模板范围，`replay_unit()` 按该范围重放；
`speaker_excluded_spans` 对应说话者中的编者补全请求。普通冒号对白和人物对话模板共用
说话者处理，不删除儿童等语义限定词。无法确认的黑幕保留 `ambiguous_*` 诊断。
书籍、故事等非对白正文不按台词注释清除黑幕。详见 [语义补修报告](reports/fold_dialogue_audit_fix.md)。

文档/UI 的判断也作用于单行，不仅依赖折叠标题。阅读动作、文档标签、整句配对引文
保留为带完整来源的 narration，混合折叠内后续对白不继承该分类。
`classification_reason` 是恢复单元的可选解释字段；业务四字段不变。
不完整角色名引号保留并诊断为 unresolved；详见 [第二轮补修](reports/document_ui_fix_2026-11-04.md)。

剧情内 `narration` 由共享恢复层补充 `narration_kind` 与可选文档分组标识，
分类和 `source_kind` 分别判断；显式旁白使用空说话者。未知文本保留并诊断，
文档作用域继承到嵌套展示容器，公告板混合对白仍逐行识别。
旧业务适配器不输出细分字段，权威 JSONL 的说明见 [恢复指南](guide/snapshot_recovery_guide.md)。
