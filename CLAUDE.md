# CLAUDE.md

## 项目目标

本项目用于抓取并解析 bilibili 原神 Wiki（`https://wiki.biligame.com/ys/`）的数据，输出原始页面 payload 与结构化 JSON，供后续数据清洗、检索、训练和验证使用。

当前仓库已经不是单一“角色解析器”，而是一个多数据族抓取与解析仓库。已落地支持的范围包括：

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

## 当前推荐文档入口

- 统一操作入口：`doc/guide/unified_operation_guide.md`
- 架构说明：`doc/project_architecture.md`
- 分项指南：`doc/guide/*.md`
- 历史开发记录：`doc/worktree_logs/*.md`

说明：

- `doc/guide/*.md` 中有不少历史分项说明，但统一执行路径与命令应以 `unified_operation_guide.md` 为准。
- `doc/worktree_logs/` 是历史 worktree 日志，不应继续作为“当前怎么操作”的权威来源。

## 代码结构认知

### 核心包

- `get_genshin_wiki/client.py`
  - MediaWiki API 访问、分页、限流、重试、`robots.txt` 校验。
- `get_genshin_wiki/crawler.py`
  - 通用抓取编排与专项分类探测。
- `get_genshin_wiki/parser.py`
  - 通用页面解析与各实体解析器。
- `get_genshin_wiki/storage.py`
  - `JsonFileStore`，负责本地 JSON 命名空间存储。
- `get_genshin_wiki/cli.py`
  - `crawl / parse / all / store` 四组命令。

### 运行入口

- `main.py`
  - 当前最稳妥的统一 CLI 入口。
- `tools/*.py`
  - 批处理、索引生成、抽样验证、重解析脚本。

### 参考与测试

- `refer/`
  - 参考实现和探索脚本，只能参考，不应作为生产代码改造目标。
- `tests/`
  - 覆盖 CLI、crawler、parser、storage、批处理脚本与索引生成。

## 命令与数据规范

### 统一命令写法

文档或脚本示例优先使用：

```powershell
python main.py ...
```

原因：

- 该写法不依赖额外的 console script 安装。
- 仓库当前没有 `get_genshin_wiki/__main__.py`，因此不应再写 `python -m get_genshin_wiki ...`。

如果明确已经 `pip install -e .`，则可以使用：

- `python -m get_genshin_wiki.cli ...`
- `get-genshin-wiki ...`

### 存储规范

- 原始页面统一进入 `data/pages/`
- 分类成员统一进入 `data/category_members/`
- 解析结果统一进入 `data/parsed/<namespace>/`
- 文件名格式统一为 `{规范化标题}__{sha1前10位}.json`

### 全量处理规范

- 标准实体现在优先使用 `python main.py all <entity>`；保留“抓分类页 + 循环 parse”的显式流程作为调试 / 回归手段。
- 魔神任务、角色传说任务 / 部族纪闻现在优先使用 `python main.py all archon-quests` 与 `python main.py all character-quests`；CLI 内部仍复用既有 `tools/*.py` 逻辑。
- 活动任务、编年史、北陆图书馆现在也都有 `python main.py all ...` 统一入口；文档中仍要写清楚它们依赖的额外上下文页或内置标题列表。

## 文档维护要求

更新项目能力时，至少同步检查以下文档是否需要改：

- `doc/guide/unified_operation_guide.md`
- `doc/project_architecture.md`
- 与该能力直接相关的 `doc/guide/*.md`
- `CLAUDE.md`

写文档时必须遵守：

- 以当前代码实现为准，不复述已经过时的 worktree 路径。
- 不把“规划中的能力”写成“已经支持的能力”。
- 如果某条命令依赖额外上下文页，例如角色语音页、魔神任务列表页、活动主页，必须写清楚。

## 当前已知现状

- `parse character` 会尝试读取本地 `"<角色名>语音"` 页面，但不会自动联网补抓。
- `parse archon-quest` 在本地存在 `魔神任务` 列表页时，章节/幕上下文更完整。
- `python main.py all event-quests` 会补抓关联活动主页并完成全量解析；单页调试仍可继续使用 `crawl event-quests` 与 `parse event-quest`。
- `python main.py all north-library` 与 `crawl north-library` 共用同一条“抓取 + 解析 + 持久化”逻辑；当前仍没有独立 `parse north-library` 子命令。
- `python main.py all character-quests` 已提供全量入口，但当前仍没有 CLI 级 `parse character-quest` 单页子命令，单页调试依赖 Python API。

## 当前测试状态

本分支已修复 `tests/test_cli.py` 的无效 import 括号，恢复完整测试收集，并新增冻结来源恢复测试。当前状态必须以实际执行 `python -m pytest -q` 为准；最终验收记录见 `doc/reports/snapshot_recovery_2026-10-10.md`。

## 冻结快照恢复

- `WikiTextParser.recover_page` 返回带原文位置、场景和分支的文本。
- `tools/recover_snapshot.py --offline` 只读解析本地快照，不初始化 crawler 或联网补依赖。
- `text_units.jsonl` 是来源与分支的权威输出；旧业务数组是兼容投影。
- 输入与现有 RAG 不修改；输出写新的 `data/recovery/` 目录，未知规则和缺来源必须保留。
- 使用与限制见 `doc/guide/snapshot_recovery_guide.md`。

## 约束

- 抓取逻辑必须遵守 `robots.txt`。
- 不要把 `refer/` 中的脚本当成生产接口。
- 不要新增和当前代码不匹配的文档入口或虚构命令。
