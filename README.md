# get_genshin_wiki

版本：**V2.2.0** · Python **3.11+**

从 [bilibili 原神 Wiki](https://wiki.biligame.com/ys/) 抓取页面、解析 WikiText 并保存结构化 JSON，也支持从冻结快照中完全离线恢复带来源、场景和分支的中文文本。

## 主要能力

- `python main.py all`：统一抓取、解析和保存 17 类数据。
- `crawl`、`parse`、`store`：单页调试、读取本地页面和管理存储。
- 冻结快照恢复：只读解析已保存来源，输出可重放的文本、场景、分支、依赖关系及未解决问题。
- 角色任务批处理与离线恢复按页面 ID 和完整原标题保存身份，同名展示名称不会互相覆盖。
- 在线抓取遵守 `robots.txt`，提供限流和重试；离线恢复不补抓网页、不下载媒体、不调用模型。

支持的数据族：角色、武器、圣遗物套装、怪物、书籍、食物、野生生物、任务道具、道具、材料、名片、秘境、提瓦特编年史、北陆图书馆、活动任务、魔神任务、角色传说任务 / 部族纪闻。

## 快速开始

安装 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)，然后在仓库根目录准备环境：

```powershell
git clone https://github.com/shiphex/get_genshin_wiki.git
cd get_genshin_wiki
uv sync --frozen --group dev
.\.venv\Scripts\Activate.ps1
python main.py --help
```

macOS / Linux 使用 `source .venv/bin/activate` 激活环境。也可以在仓库根目录通过 `uv run python main.py ...` 执行命令。

### 在线抓取与解析

这些命令需要访问 Wiki API，会按需抓取页面：

```powershell
python main.py all weapons
python main.py all characters
python main.py all event-quests
python main.py all archon-quests --resume
python tools/batch_character_quests.py --resume
```

`python main.py all` 不带实体时处理全部 17 类；`--page-limit N` 对每个实体分别限制页面数；`--resume` 仅适用于魔神任务与角色任务。更多参数见[统一操作指南](doc/guide/unified_operation_guide.md)。

单页调试示例：

```powershell
python main.py crawl page "霜结的誓金枝"
python main.py parse weapon "霜结的誓金枝"
python main.py crawl page "七七"
python main.py crawl page "七七语音"
python main.py parse character "七七"
```

单页解析读取本地页面。角色语音页、关联活动主页及魔神任务列表页需要提前缓存；在线 `all` 流程会按各实体的规则补充上下文。

### 冻结快照离线恢复

先准备包含 `pages/` 的快照目录和完整本地依赖环境。下例中的 `snapshot_input` 和哈希清单路径需替换为实际位置，输出必须是新的空目录：

```powershell
uv run --offline --no-sync python tools/recover_snapshot.py --input-root "snapshot_input" --output-root "data/recovery/run-001" --offline --manifest "snapshot_manifest.json"
```

`--offline` 必须提供。`--manifest` 可选；提供时先核对交接哈希，不提供时仍核对运行前后的输入哈希。缺页面、缺引用、媒体文字或未知模板会登记，不联网或调用模型补写。

> [!NOTE]
> 离线运行前应准备好依赖；需要补齐依赖时应先完成环境准备。已有非空恢复目录不会被覆盖，重复实验请换一个输出目录。

恢复输出包括权威 `text_units.jsonl`、场景、候选节点、依赖和问题清单、兼容 parsed、摘要及输入 / 输出哈希清单。来源范围使用解码 WikiText 的零基半开字符区间；下游应按来源、场景、分支及消费上下文切分。接口见[离线恢复指南](doc/guide/snapshot_recovery_guide.md)。

## 命令入口

| 命令组 | 用途 |
|---|---|
| `all` | 17 类实体的在线抓取、解析和保存流程 |
| `crawl` | 分类、成员、单页及专项页面抓取 |
| `parse` | 对本地页面进行通用或实体解析 |
| `store` | 本地 JSON 的读写、更新、追加、删除和查询 |
| `tools/recover_snapshot.py` | 独立的冻结来源离线恢复入口 |

```powershell
python main.py all --help
python main.py crawl --help
python main.py parse --help
python main.py store --help
python tools/recover_snapshot.py --help
```

当前没有 `python -m get_genshin_wiki` 入口，也没有 `parse character-quest`、`parse north-library` 子命令；角色任务单页调试使用 Python API，北陆图书馆使用专项入口。

## 数据输出与升级

| 内容 | 默认位置 |
|---|---|
| 原始页面 / 分类成员 | `data/pages/`、`data/category_members/` |
| 业务解析结果 | `data/parsed/<namespace>/` |
| 魔神任务 / 角色任务汇总 | `data/archon_quests.json`、`data/character_quests.json` |
| 冻结恢复的独立实验输出 | `data/recovery/<新目录>/` |
| 在线验证报告 | `data/reports/` |

文件名仍采用安全标题与 SHA1 后缀。V2.2.0 的角色任务批处理、独立索引与离线恢复使用完整原标题作为存储键和索引引用，展示名保留在“任务名称”中，并增加 `source_title`、`page_id` 及结构化任务引用。

统一 CLI 的 `all character-quests`（也由顶层 `all` 调用）仍按展示名去重和判断 resume，可能遗漏同名页面或跳过缺少身份的旧记录。角色任务请使用 `python tools/batch_character_quests.py`；上述身份保证不适用于这一旧 CLI 路径。

从 V2.1 升级时，应将旧汇总与新输出分开保存。缺少来源身份的旧汇总不能用于按展示名判断 resume，需从原始页面重新解析；旧展示名文件名也不能作为新结果的查找键。旧对话数组保留兼容用途，新恢复的来源与分支使用权威文本单元。

`data/` 被 Git 忽略。本次 Release 提供代码、测试和说明，恢复数据继续保留在本地；历史快照可从[已有 Releases](https://github.com/shiphex/get_genshin_wiki/releases)取得，使用前需核对快照身份与哈希。

## 验证与能力边界

```powershell
python -m pytest -q
```

V2.2.0 发布验收包含 **122 项测试和 18 个子测试**。冻结快照实验处理 5,946 页，导出 172,136 个单元；两次运行的 5,952 个输出文件逐字节一致，11,439 个输入文件哈希不变。详细证据见[实验报告](doc/reports/snapshot_recovery_2026-10-10.md)。

这些检查证明已导出内容可回查、重放和重复运行。仍有未知模板、未支持正文别名、缺失来源和 150 个未解决分支归属；候选节点与中文字符的恢复比例不代表全游戏剧情覆盖率。RAG 接入需独立验收，现有 RAG 不自动切换。

## 文档与目录

- [统一操作指南](doc/guide/unified_operation_guide.md)：在线操作及当前 CLI 边界。
- [离线恢复指南](doc/guide/snapshot_recovery_guide.md)：输入输出、来源与分支契约。
- [角色任务指南](doc/guide/character-quests_guide.md)：页面身份、索引与升级。
- [项目架构](doc/project_architecture.md)：模块、数据流与存储。
- [V2.2.0 发布说明](doc/releases/V2.2.0.md)：版本变化及兼容性。
- `doc/worktree_logs/`：历史功能规格，不作为当前操作入口。

```text
get_genshin_wiki/
├─ main.py
├─ pyproject.toml / uv.lock
├─ get_genshin_wiki/        # 客户端、编排、解析、存储与 CLI
│  └─ recovery/            # 来源追踪、分支、显示规则和独立校验
├─ tools/                  # 批处理、索引、离线恢复
├─ tests/                  # 单元测试与冻结回归页面
├─ doc/                    # 指南、架构、报告、发布说明及历史规格
├─ data/                   # 本地生成数据，Git 忽略
└─ refer/                  # 参考探索代码
```
