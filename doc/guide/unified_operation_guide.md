# 统一数据获取操作指南

本指南整合 `doc/guide/` 下现有分项文档，并以当前仓库中的 `get_genshin_wiki/cli.py` 为准说明如何抓取、解析和检查数据。

结论先行：

- 推荐入口是 `python main.py all`。
- `crawl` + `parse` 手动流程继续保留，但定位为调试参考。
- “当前支持的数据类型”以 CLI 已实现的命令为准，不再沿用旧 worktree 的规划清单。

## 1. 环境与入口

在仓库根目录准备环境后执行；在线抓取需要访问 Wiki API：

```powershell
uv sync --frozen --group dev
.\.venv\Scripts\Activate.ps1
```

推荐始终使用：

```powershell
python main.py ...
```

未激活环境时，可使用 `uv run python main.py ...`；macOS / Linux 使用 `source .venv/bin/activate`。当前项目按源码运行，uv 环境准备不会安装项目 console script。

当前不支持：

- `python -m get_genshin_wiki ...`

常用帮助命令：

```powershell
python main.py --help
python main.py all --help
python main.py crawl --help
python main.py parse --help
python main.py store --help
```

## 2. 推荐入口：`python main.py all`

### 已有缓存的完全离线刷新

仅更新本地解析结果、无需重新抓取时使用以下独立入口。不要用在线 `all` 命令代替：

```powershell
python tools/refresh_parsed_offline.py --data-root data
python tools/refresh_parsed_offline.py --data-root data --apply
```

默认暂存并验证，不改变正式数据。`--apply` 在全部验证通过后备份并覆盖现有 17 类 `parsed`、两个任务汇总，以及指定全量目录 `recovery/full-offline-20261104`。保留原始 `pages/categories/category_members`、其他恢复实验及历史 ZIP。`--work-root <新目录>` 可指定与数据根目录互不包含的暂存目录；默认使用 `.uv-cache/entity-versions/<运行标识>/`。

所有实体根对象包含 `所属版本` 字符串，原页多版本保留原顺序并用顿号连接，数字版本和“月之…”不互转。版本缺失、无效或冲突为空字符串；不向分卷、部件、对白等子项新增字段，也不从食谱版本、正文数字、修改日期或关联活动推断。

刷新使用本地语音、活动页和任务目录作为上下文，以完整原标题/页面身份关联单页和汇总；北陆图书馆已有分类发现信息作为缓存上下文保留。版本之外的业务差异、已有非空版本不一致或缺少主体原页会阻止覆盖。恢复过程沿用离线封网、来源重放和分支校验，完整输出生成两遍并比较字节；已有全量恢复的文本、分支和诊断必须保持。

每次运行保存 `report.json`、`version_evidence.jsonl`、`unresolved_versions.json` 和输入哈希清单。应用时还保存 `backup.zip`、覆盖前状态、替换日志及旧目标；替换或落盘验证失败自动回滚。应用后的报告副本为 `data/reports/entity-versions-latest.json`。不使用 `resume` 跳过旧解析记录，不修改现有 RAG。

默认不接受版本以外的变化。如果确认旧 JSON 尚未同步改动前解析器的既有结果，可以显式提供 `--baseline-business-root <目录>`。该目录按正式相对路径保存独立复现的业务结果，`baseline_manifest.json` 包含 `input_fingerprint_sha256`、`parser_source_sha256` 和 `files`（输出文件的相对路径、大小、SHA-256）；生成此清单时排除清单自身。工具先验证基线输入/文件哈希，再要求新结果的全部非版本字段与基线一致，已有非空版本冲突仍阻断。接受项的文件和字段进入运行报告，完整前后值及基线文件哈希写入 `accepted_existing_differences.json`。该参数不跳过差异检查，也不授权重新抓取。

优先使用一体化流水线，而不是自己手写 PowerShell 循环。

```powershell
python main.py all
python main.py all --page-limit 2
python main.py all weapons
python main.py all characters
python main.py all event-quests
python main.py all chronicles
python main.py all north-library
python main.py all archon-quests --resume
python tools/batch_character_quests.py --resume
```

行为说明：

- `python main.py all` 不带子命令时，会按固定顺序跑完全部 17 类实体。
- 顶层顺序是：`weapons`、`artifacts`、`monsters`、`books`、`foods`、`wildlife`、`quest-items`、`items`、`materials`、`namecards`、`secret-items`、`characters`、`event-quests`、`chronicles`、`north-library`、`archon-quests`、`character-quests`。
- `--page-limit` 与 `--no-persist` 适用于 `all` 顶层命令和所有 `all <entity>` 子命令。
- `--resume` 只存在于 `all archon-quests` 和 `all character-quests`。
- `all character-quests`（包括顶层 `all` 内的该步骤）仍按展示名去重和判断 resume，可能遗漏同名页面或跳过缺少身份的旧记录。角色任务推荐独立批处理脚本，其参数见第 5.7 节。
- `python main.py all` 的输出是按实体汇总后的摘要；`python main.py all <entity>` 会返回该实体的详细逐页结果。

## 3. `all` 当前支持的 17 类实体

### 3.1 标准分类实体

这 11 类实体都走同一种共享流程：先取分类成员，再逐页 `crawl page`，最后调用对应解析器。

| `all` 子命令 | Wiki 分类 | 单页解析命令 | 输出目录 |
|------|------|------|------|
| `weapons` | `武器` | `parse weapon <标题>` | `data/parsed/weapons/` |
| `artifacts` | `圣遗物套装` | `parse artifact <标题>` | `data/parsed/artifacts/` |
| `monsters` | `怪物` | `parse monster <标题>` | `data/parsed/monsters/` |
| `books` | `书籍` | `parse book <标题>` | `data/parsed/books/` |
| `foods` | `食物` | `parse food <标题>` | `data/parsed/foods/` |
| `wildlife` | `野生生物` | `parse wildlife <标题>` | `data/parsed/wildlife/` |
| `quest-items` | `任务道具` | `parse quest-item <标题>` | `data/parsed/quest-items/` |
| `items` | `道具` | `parse item <标题>` | `data/parsed/items/` |
| `materials` | `材料` | `parse material <标题>` | `data/parsed/materials/` |
| `namecards` | `名片` | `parse namecard <标题>` | `data/parsed/namecards/` |
| `secret-items` | `秘境` | `parse secret-item <标题>` | `data/parsed/secret-items/` |

### 3.2 特殊流程实体

这 6 类实体不是简单的“分类成员 -> 单页解析”，推荐直接使用 `all` 子命令。

| `all` 子命令 | 输入来源 | 自动补充行为 | 输出位置 |
|------|------|------|------|
| `characters` | 分类 `角色` | 自动抓取 `<角色名>语音` 页面，再调用 `parse character` | `data/parsed/characters/` |
| `event-quests` | 自动探测实际分类名，再抓分类成员 | 自动补抓关联活动主页，并把主页内容传给事件任务解析器 | `data/parsed/event-quests/` |
| `chronicles` | `cli.py` 内置的 13 个标题列表 | 对每个标题执行 `crawl page` + `parse chronicle` | `data/parsed/chronicles/` |
| `north-library` | 固定标题 `北陆图书馆` | 复用北陆图书馆专项一体化抓取 + 解析逻辑 | `data/parsed/north-library/` |
| `archon-quests` | 列表页 `魔神任务` | 展开系列页、构建章节上下文、写索引和聚合输出 | `data/parsed/archon-quests/`、`data/parsed/archon-quest-index/`、`data/archon_quests.json` |
| `character-quests` | 列表页 `传说任务` + 自动探测任务分类 | 合并 `传说任务` / `部族纪闻` 成员、跳过系列页、只写叶子任务、写索引和聚合输出 | `data/parsed/character-quests/`、`data/parsed/character-quest-index/`、`data/character_quests.json` |

`all chronicles` 当前使用的内置标题列表为：

- `提瓦特编年史（公元纪）`
- `提瓦特编年史`
- `蒙德`
- `璃月`
- `稻妻`
- `须弥`
- `枫丹`
- `纳塔`
- `至冬`
- `坎瑞亚`
- `白夜国`
- `星球`
- `宇宙`

## 4. 单页调试入口

### 4.1 已提供 `parse` 子命令的页面类型

当你只想检查某一个标题时，优先用 `crawl page` + `parse ...`。

| `parse` 子命令 | 对应数据 | 默认输出目录 | 调试备注 |
|------|------|------|------|
| `page` | 通用页面 | `data/parsed/pages/` | 仅做通用 wikitext 解析，不包含实体专用逻辑 |
| `chronicle` | 提瓦特编年史 | `data/parsed/chronicles/` | 适合调试某个国家或地区页 |
| `character` | 角色 | `data/parsed/characters/` | 若本地已有 `<角色名>语音`，会自动加载 |
| `archon-quest` | 魔神任务 | `data/parsed/archon-quests/` | 若本地已有 `pages/魔神任务`，会自动补章节上下文 |
| `event-quest` | 活动任务 | `data/parsed/event-quests/` | 若本地已有对应活动主页，会自动补活动上下文 |
| `weapon` | 武器 | `data/parsed/weapons/` | 标准分类实体 |
| `artifact` | 圣遗物套装 | `data/parsed/artifacts/` | 标准分类实体 |
| `monster` | 怪物 | `data/parsed/monsters/` | 标准分类实体 |
| `food` | 食物 | `data/parsed/foods/` | 标准分类实体 |
| `wildlife` | 野生生物 | `data/parsed/wildlife/` | 标准分类实体 |
| `quest-item` | 任务道具 | `data/parsed/quest-items/` | 标准分类实体 |
| `item` | 道具 | `data/parsed/items/` | 标准分类实体 |
| `material` | 材料 | `data/parsed/materials/` | 标准分类实体 |
| `namecard` | 名片 | `data/parsed/namecards/` | 标准分类实体 |
| `secret-item` | 秘境 | `data/parsed/secret-items/` | 标准分类实体 |
| `book` | 书籍 | `data/parsed/books/` | 标准分类实体 |

示例：

```powershell
python main.py crawl page "霜结的誓金枝"
python main.py parse weapon "霜结的誓金枝"

python main.py crawl page "哥伦比娅"
python main.py crawl page "哥伦比娅语音"
python main.py parse character "哥伦比娅"
```

### 4.2 没有独立 `parse` 子命令的页面类型

这两类数据当前没有 CLI 级单页解析子命令：

- 北陆图书馆：使用 `python main.py crawl north-library`
- 角色传说任务 / 部族纪闻：使用 `python tools/batch_character_quests.py`，或走下文的 Python API 调试流程

## 5. 旧式手动流程（保留作调试参考）

### 5.1 标准分类实体的手动流程

推荐入口：

```powershell
python main.py all weapons
```

等价的旧式调试流程：

```powershell
python main.py crawl category-pages "武器"
$titles = python main.py store query category_members "武器" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py parse weapon $title | Out-Null
}
```

把上面的分类名和 `parse` 目标替换为下表即可：

| 分类名 | `parse` 目标 |
|------|------|
| `武器` | `weapon` |
| `圣遗物套装` | `artifact` |
| `怪物` | `monster` |
| `书籍` | `book` |
| `食物` | `food` |
| `野生生物` | `wildlife` |
| `任务道具` | `quest-item` |
| `道具` | `item` |
| `材料` | `material` |
| `名片` | `namecard` |
| `秘境` | `secret-item` |

### 5.2 角色

推荐入口：

```powershell
python main.py all characters
```

旧式调试流程：

```powershell
python main.py crawl members "角色" | Out-Null
$titles = python main.py store query category_members "角色" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py crawl page $title | Out-Null
    python main.py crawl page "$($title)语音" | Out-Null
    python main.py parse character $title | Out-Null
}
```

如果只想抽样验证，也可以继续用：

```powershell
python tools/crawl_validate_characters.py --title "哥伦比娅" --title "钟离"
```

### 5.3 活动任务

推荐入口：

```powershell
python main.py all event-quests
```

旧式调试流程：

```powershell
python main.py crawl event-quests | Out-Null
$titles = python main.py store query category_members "活动事件" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py parse event-quest $title | Out-Null
}
```

说明：

- `crawl event-quests` 会自动探测实际分类名，当前通常是 `活动事件`。
- 它会顺带抓取关联活动主页，因此后续单页 `parse event-quest` 的补全效果会更好。

### 5.4 提瓦特编年史

推荐入口：

```powershell
python main.py all chronicles
```

旧式调试流程一：

```powershell
python main.py crawl chronicle-pages
```

旧式调试流程二：显式按 CLI 内置标题列表逐页执行。

```powershell
$chronicleTitles = @(
    "提瓦特编年史（公元纪）",
    "提瓦特编年史",
    "蒙德",
    "璃月",
    "稻妻",
    "须弥",
    "枫丹",
    "纳塔",
    "至冬",
    "坎瑞亚",
    "白夜国",
    "星球",
    "宇宙"
)

foreach ($title in $chronicleTitles) {
    python main.py crawl page $title | Out-Null
    python main.py parse chronicle $title | Out-Null
}
```

### 5.5 北陆图书馆

推荐入口：

```powershell
python main.py all north-library
```

旧式调试入口：

```powershell
python main.py crawl north-library
python main.py crawl north-library --title "北陆图书馆"
python main.py crawl north-library --output-namespace parsed/north-library
```

说明：

- `crawl north-library` 本身就是“抓取 + 解析 + 可选落盘”的一体命令。
- `all north-library` 只是把这条专项流程挂到了统一的 `all` 命令组下。

### 5.6 魔神任务

推荐入口：

```powershell
python main.py all archon-quests
python main.py all archon-quests --resume
```

保留的批处理调试入口：

```powershell
python tools/batch_archon_quests.py
python tools/generate_archon_quest_index.py
```

如果只调试单页，建议先把列表页抓到本地：

```powershell
python main.py crawl page "魔神任务"
python main.py crawl page "鸟瞰风物"
python main.py parse archon-quest "鸟瞰风物"
```

### 5.7 角色传说任务 / 部族纪闻

推荐入口：

```powershell
python tools/batch_character_quests.py
python tools/batch_character_quests.py --resume
```

独立索引入口：

```powershell
python tools/generate_character_quest_index.py
```

当前 CLI 没有 `parse character-quest`。若要调试单页，建议：

```powershell
python main.py crawl page "传说任务"
python main.py crawl page "漩涡之遗"
python main.py crawl members "传说任务"
python main.py crawl members "部族纪闻"
```

然后在 Python 里解析：

```python
from pathlib import Path

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore

store = JsonFileStore(Path("data"))
parser = WikiTextParser()

list_payload = store.read("pages", "传说任务")
page_payload = store.read("pages", "漩涡之遗")

list_entries = parser.parse_character_quest_list_page(list_payload)
series_context = parser.build_character_quest_series_context(list_entries)
record = parser.parse_character_quest_page(page_payload, series_context=series_context)

print(record.to_dict())
```

## 6. 常用检查命令

```powershell
python main.py store list parsed/weapons
python main.py store query parsed/weapons "霜结的誓金枝"
python main.py store exists pages "哥伦比娅"
python main.py store query parsed/archon-quest-index "魔神任务"
python main.py store query parsed/character-quest-index "传说任务"
```

聚合输出文件：

- `data/archon_quests.json`
- `data/character_quests.json`

## 7. 当前代码库的真实限制

- `python -m get_genshin_wiki` 当前不是有效入口，因为仓库里没有 `get_genshin_wiki/__main__.py`。
- `all` 顶层命令没有 `--resume`；只有 `all archon-quests` 和 `all character-quests` 支持 `--resume`。
- `all chronicles` 不是动态发现全部编年史页面，而是使用 `cli.py` 中写死的 13 个标题。
- `all north-library` 固定处理标题 `北陆图书馆`，也不暴露 `--title` / `--output-namespace`；需要这些参数时请改用 `crawl north-library`。
- `parse character` 不会自动联网抓取 `"<角色名>语音"`；只有语音页已经在本地时，才会自动加载。
- `parse event-quest` 不会自动联网补抓关联活动主页；只有活动主页已经在本地时，才会自动加载。
- `parse archon-quest` 不会自动联网补抓 `魔神任务` 列表页；只有列表页已经在本地时，章节上下文才会更完整。
- 当前没有 CLI 级 `parse north-library` 子命令。
- 当前没有 CLI 级 `parse character-quest` 子命令；角色传说任务 / 部族纪闻的单页调试仍需借助 Python API。
- `python main.py all --page-limit N` 会把同一个 `N` 应用于每个实体子流程，不是“全局总量只处理 N 页”。
## 8. 冻结快照恢复入口

不联网的冻结来源恢复使用 `tools/recover_snapshot.py --offline`，详见 [离线恢复指南](snapshot_recovery_guide.md)。该入口复用解析器，不使用下方抓取命令补依赖，也不覆盖现有 parsed 或 RAG。

V2.2.0 的角色任务批处理、独立索引与离线恢复以 `source_title` 和 `page_id` 保存来源身份，存储键及索引中的 `tasks` 使用完整原标题，“任务名称”仍为展示名。旧汇总缺少来源身份时需重新解析；新旧结果应保存到不同目录。该身份保证不适用于仍按展示名处理的统一 CLI 角色任务路径。结构化引用见 [角色任务指南](character-quests_guide.md)。

折叠剧情修复沿用现有业务字段，旧快照的 parsed / 汇总需要重新生成；`--resume` 会跳过
旧记录，不能用于此次迁移。单页使用 `python main.py parse archon-quest "尾声的尾声"`。
来源诊断通过 `recover_page()['issues']` 或独立离线恢复输出读取，详见
[0605 折叠剧情验收报告](../reports/fold_dialogue_2026-10-30.md)。

第一轮语义抽样未通过，后续修复和复验命令见 [独立审计补修报告](../reports/fold_dialogue_audit_fix.md)。
恢复 API 会分离台词附着的黑幕 annotation，业务对话字段不增加注释键；
直接读取 JSONL 的消费者需要识别 annotation 和 excluded_spans，详见离线恢复指南。

文档/UI 行级分类补修后的冻结数据重生成和复验，见
[2026-11-04 补修报告](../reports/document_ui_fix_2026-11-04.md)；
其中的专用脚本默认只生成审计产物，`--apply` 会先备份，再更新任务产物及汇总。

剧情旁白与非角色文本的后续修正见 [执行报告](../reports/story_narration_fix_2026-11-04.md)。
`python doc/reports/story_narration_fix_2026-11-04/reparse.py` 默认仅生成审计差异和新的
恢复 JSONL；加 `--apply` 会先备份并更新三个任务数据族及汇总。细分字段仅在恢复层，
现有业务 JSON 保持原格式。
