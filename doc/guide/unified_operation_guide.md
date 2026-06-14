# 统一数据获取操作指南

本指南整合 `doc/guide/` 下现有分项文档，并以当前仓库中的 `get_genshin_wiki/cli.py` 为准说明如何抓取、解析和检查数据。

结论先行：

- 推荐入口是 `python main.py all`。
- `crawl` + `parse` 手动流程继续保留，但定位为调试参考。
- “当前支持的数据类型”以 CLI 已实现的命令为准，不再沿用旧 worktree 的规划清单。

## 1. 环境与入口

推荐在当前 worktree 根目录执行：

```powershell
cd E:\Workplace\Learn_project\get_genshin_wiki-simplify-pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

推荐始终使用：

```powershell
python main.py ...
```

安装完成后，下面两个入口也可用：

- `python -m get_genshin_wiki.cli ...`
- `get-genshin-wiki ...`

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
python main.py all character-quests --resume
```

行为说明：

- `python main.py all` 不带子命令时，会按固定顺序跑完全部 17 类实体。
- 顶层顺序是：`weapons`、`artifacts`、`monsters`、`books`、`foods`、`wildlife`、`quest-items`、`items`、`materials`、`namecards`、`secret-items`、`characters`、`event-quests`、`chronicles`、`north-library`、`archon-quests`、`character-quests`。
- `--page-limit` 与 `--no-persist` 适用于 `all` 顶层命令和所有 `all <entity>` 子命令。
- `--resume` 只存在于 `all archon-quests` 和 `all character-quests`。
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
- 角色传说任务 / 部族纪闻：使用 `python main.py all character-quests`，或走下文的 Python API 调试流程

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
python main.py all character-quests
python main.py all character-quests --resume
```

保留的批处理调试入口：

```powershell
python tools/batch_character_quests.py
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
