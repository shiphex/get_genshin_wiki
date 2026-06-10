# 统一数据获取操作指南

本指南整合 `doc/guide/` 下现有分项文档，并以当前仓库代码为准，统一说明如何：

- 获取当前代码已支持的全部数据
- 获取某一类数据
- 获取某一个具体页面

如果旧指南与本指南冲突，以本指南和当前代码实现为准。

## 1. 适用范围与基本约定

- 所有命令默认在仓库根目录 `E:\Workplace\Learn_project\get_genshin_wiki` 下执行。
- 示例统一使用 `python main.py` 作为 CLI 入口。这是当前最稳妥的零额外配置入口。
- 如果已经执行过 `pip install -e .`，也可以把同一条命令改写为：
  - `python -m get_genshin_wiki.cli ...`
  - 或 `get-genshin-wiki ...`
- “全部数据”指当前代码已经支持抓取或解析的数据族，不等于历史规划中过的所有 Wiki 类别。
- 所有原始页面默认写入 `data/pages/`；结构化结果默认写入 `data/parsed/.../`。

## 2. 环境准备

```powershell
cd E:\Workplace\Learn_project\get_genshin_wiki
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

可选：

```powershell
pip install pytest
```

常用帮助命令：

```powershell
python main.py --help
python main.py crawl --help
python main.py parse --help
python main.py store --help
```

## 3. 统一入口与输出位置

### 3.1 CLI 命令分组

- `crawl`
  - 抓取分类、分类成员、单页、分类下全部页面，以及少量专项入口。
- `parse`
  - 读取本地 `pages/` 中的原始页面并做结构化解析。
- `store`
  - 查询或维护本地 JSON 存储。

### 3.2 常见命名空间

| 命名空间 | 说明 |
|------|------|
| `data/categories/` | 分类探测或分类列表 |
| `data/category_members/` | 分类成员标题列表 |
| `data/pages/` | 原始页面 payload |
| `data/parsed/characters/` | 角色解析结果 |
| `data/parsed/weapons/` | 武器解析结果 |
| `data/parsed/artifacts/` | 圣遗物套装解析结果 |
| `data/parsed/monsters/` | 怪物解析结果 |
| `data/parsed/books/` | 书籍解析结果 |
| `data/parsed/foods/` | 食物解析结果 |
| `data/parsed/wildlife/` | 野生生物解析结果 |
| `data/parsed/quest-items/` | 任务道具解析结果 |
| `data/parsed/items/` | 道具解析结果 |
| `data/parsed/materials/` | 材料解析结果 |
| `data/parsed/namecards/` | 名片解析结果 |
| `data/parsed/secret-items/` | 秘境解析结果 |
| `data/parsed/chronicles/` | 编年史解析结果 |
| `data/parsed/north-library/` | 北陆图书馆解析结果 |
| `data/parsed/event-quests/` | 活动任务解析结果 |
| `data/parsed/archon-quests/` | 魔神任务解析结果 |
| `data/parsed/archon-quest-index/` | 魔神任务索引 |
| `data/parsed/character-quests/` | 角色传说任务 / 部族纪闻解析结果 |
| `data/parsed/character-quest-index/` | 角色传说任务 / 部族纪闻索引 |
| `data/reports/` | 验证与批处理报告 |

## 4. 当前支持的数据类型

### 4.1 标准 CLI 解析型实体

这类数据都遵循同一模式：先 `crawl page` 或 `crawl category-pages`，再 `parse <type>`。

| 分类名 | 解析命令 | 输出目录 |
|------|------|------|
| `武器` | `parse weapon <标题>` | `data/parsed/weapons/` |
| `圣遗物套装` | `parse artifact <标题>` | `data/parsed/artifacts/` |
| `怪物` | `parse monster <标题>` | `data/parsed/monsters/` |
| `书籍` | `parse book <标题>` | `data/parsed/books/` |
| `食物` | `parse food <标题>` | `data/parsed/foods/` |
| `野生生物` | `parse wildlife <标题>` | `data/parsed/wildlife/` |
| `任务道具` | `parse quest-item <标题>` | `data/parsed/quest-items/` |
| `道具` | `parse item <标题>` | `data/parsed/items/` |
| `材料` | `parse material <标题>` | `data/parsed/materials/` |
| `名片` | `parse namecard <标题>` | `data/parsed/namecards/` |
| `秘境` | `parse secret-item <标题>` | `data/parsed/secret-items/` |

### 4.2 需要额外上下文或专项入口的数据

| 数据类型 | 推荐入口 | 说明 |
|------|------|------|
| 角色 | `crawl page "<角色名>"` + `crawl page "<角色名>语音"` + `parse character "<角色名>"` | 为获得完整语音数据，通常要补抓 `语音` 页 |
| 提瓦特编年史 | `crawl chronicle-pages` 或 `crawl page "<页面名>"` + `parse chronicle "<页面名>"` | 主页面可自动探测，国家/地区页仍依赖显式标题 |
| 北陆图书馆 | `crawl north-library` | 当前没有单独的 `parse north-library` 命令 |
| 活动任务 | `crawl event-quests` + `parse event-quest "<标题>"` | `crawl event-quests` 会顺带抓关联活动主页 |
| 魔神任务 | `tools/batch_archon_quests.py` | 单页可用 `parse archon-quest`，但全量更适合批处理脚本 |
| 角色传说任务 / 部族纪闻 | `tools/batch_character_quests.py` | 当前没有 CLI 级 `parse character-quest` 子命令 |

## 5. 获取某一个具体页面

### 5.1 标准实体

以武器 `霜结的誓金枝` 为例：

```powershell
python main.py crawl page "霜结的誓金枝"
python main.py parse weapon "霜结的誓金枝"
```

以秘境 `待解「弈局」` 为例：

```powershell
python main.py crawl page "待解「弈局」"
python main.py parse secret-item "待解「弈局」"
```

只查看解析结果、不落盘：

```powershell
python main.py parse weapon "霜结的誓金枝" --no-persist
```

### 5.2 角色

角色解析会尝试读取本地已存在的 `"<角色名>语音"` 页面；如果没有语音页，结果中会缺少完整语音信息。

```powershell
python main.py crawl page "哥伦比娅"
python main.py crawl page "哥伦比娅语音"
python main.py parse character "哥伦比娅"
```

### 5.3 魔神任务

为了让章节/幕信息更完整，单页解析前建议先保留列表页 `魔神任务`：

```powershell
python main.py crawl page "魔神任务"
python main.py crawl page "鸟瞰风物"
python main.py parse archon-quest "鸟瞰风物"
```

### 5.4 活动任务

活动任务解析会优先读取“关联活动主页”来补全活动名称、活动期间、活动列表和所属任务描述。因此最稳妥的单项流程是先跑专项抓取：

```powershell
python main.py crawl event-quests --page-limit 20
python main.py parse event-quest "有朋自远方来·其二"
```

如果你明确知道要抓的任务页和活动主页，也可以手动抓两页再解析。

### 5.5 提瓦特编年史

```powershell
python main.py crawl page "提瓦特编年史（公元纪）"
python main.py parse chronicle "提瓦特编年史（公元纪）"
```

### 5.6 北陆图书馆

北陆图书馆是一条一步完成的命令：

```powershell
python main.py crawl north-library
```

### 5.7 角色传说任务 / 部族纪闻

当前 CLI 没有 `parse character-quest` 子命令。若要调试单页，建议：

```powershell
python main.py crawl page "传说任务"
python main.py crawl page "漩涡之遗"
python main.py crawl members "传说任务"
python main.py crawl members "部族纪闻"
```

然后用 Python API 解析：

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

## 6. 获取某一类数据

### 6.1 标准实体的通用做法

这套流程适用于武器、圣遗物套装、怪物、书籍、食物、野生生物、任务道具、道具、材料、名片、秘境。

示例：抓取并解析整类 `武器`。

```powershell
python main.py crawl category-pages "武器"
$titles = python main.py store query category_members "武器" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py parse weapon $title | Out-Null
}
```

把上面的 `武器` 和 `weapon` 换成对应映射即可：

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

### 6.2 角色整类抓取

角色和标准实体的区别在于需要额外抓语音页：

```powershell
python main.py crawl members "角色" | Out-Null
$titles = python main.py store query category_members "角色" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py crawl page $title | Out-Null
    python main.py crawl page "$($title)语音" | Out-Null
    python main.py parse character $title | Out-Null
}
```

如果只想验证一组指定角色，也可以使用：

```powershell
python tools/crawl_validate_characters.py --title "哥伦比娅" --title "钟离"
```

### 6.3 活动任务整类抓取

```powershell
python main.py crawl event-quests | Out-Null
$titles = python main.py store query category_members "活动事件" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py parse event-quest $title | Out-Null
}
```

说明：

- `crawl event-quests` 会自动探测实际分类名，当前通常是 `活动事件`。
- 该命令会同步抓活动主页，所以后续 `parse event-quest` 的补全效果更好。
- 当前没有专门的“活动任务全量批解析脚本”。

### 6.4 魔神任务整类抓取

推荐直接用批处理脚本：

```powershell
python tools/batch_archon_quests.py
python tools/generate_archon_quest_index.py
```

常用参数：

```powershell
python tools/batch_archon_quests.py --data-root data --output data/archon_quests.json --resume
python tools/generate_archon_quest_index.py --data-root data --output data/archon_quest_index.json
```

输出包括：

- `data/parsed/archon-quests/`
- `data/parsed/archon-quest-index/`
- `data/archon_quests.json`
- `data/archon_quest_index.json`

### 6.5 角色传说任务 / 部族纪闻整类抓取

推荐直接用批处理脚本：

```powershell
python tools/batch_character_quests.py
python tools/generate_character_quest_index.py
```

常用参数：

```powershell
python tools/batch_character_quests.py --data-root data --output data/character_quests.json --resume
python tools/generate_character_quest_index.py --data-root data --output data/character_quest_index.json
```

输出包括：

- `data/parsed/character-quests/`
- `data/parsed/character-quest-index/`
- `data/character_quests.json`
- `data/character_quest_index.json`

### 6.6 提瓦特编年史整类抓取

主页面可以用专项入口自动探测：

```powershell
python main.py crawl chronicle-pages
```

如果要把当前代码约定的国家/地区页面一并抓完，建议显式列标题：

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

### 6.7 北陆图书馆整类抓取

当前实现只对应北陆图书馆主页及其层级树：

```powershell
python main.py crawl north-library
```

## 7. 获取当前代码已支持的全部数据

建议按下面顺序执行。这样最容易保证上下文页已经就位。

### 7.1 标准实体

```powershell
$jobs = @(
    @{ Category = "武器"; ParseTarget = "weapon" },
    @{ Category = "圣遗物套装"; ParseTarget = "artifact" },
    @{ Category = "怪物"; ParseTarget = "monster" },
    @{ Category = "书籍"; ParseTarget = "book" },
    @{ Category = "食物"; ParseTarget = "food" },
    @{ Category = "野生生物"; ParseTarget = "wildlife" },
    @{ Category = "任务道具"; ParseTarget = "quest-item" },
    @{ Category = "道具"; ParseTarget = "item" },
    @{ Category = "材料"; ParseTarget = "material" },
    @{ Category = "名片"; ParseTarget = "namecard" },
    @{ Category = "秘境"; ParseTarget = "secret-item" }
)

foreach ($job in $jobs) {
    python main.py crawl category-pages $job.Category | Out-Null
    $titles = python main.py store query category_members $job.Category | ConvertFrom-Json
    foreach ($title in $titles) {
        python main.py parse $job.ParseTarget $title | Out-Null
    }
}
```

### 7.2 角色

```powershell
python main.py crawl members "角色" | Out-Null
$titles = python main.py store query category_members "角色" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py crawl page $title | Out-Null
    python main.py crawl page "$($title)语音" | Out-Null
    python main.py parse character $title | Out-Null
}
```

### 7.3 活动任务

```powershell
python main.py crawl event-quests | Out-Null
$titles = python main.py store query category_members "活动事件" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py parse event-quest $title | Out-Null
}
```

### 7.4 魔神任务

```powershell
python tools/batch_archon_quests.py
python tools/generate_archon_quest_index.py
```

### 7.5 角色传说任务 / 部族纪闻

```powershell
python tools/batch_character_quests.py
python tools/generate_character_quest_index.py
```

### 7.6 提瓦特编年史

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

### 7.7 北陆图书馆

```powershell
python main.py crawl north-library
```

## 8. 可选批处理与验证脚本

### 8.1 抓取 + 重解析 + 验证 + 测试

以下脚本适合这 12 类实体：

- `characters`
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

用法示例：

```powershell
python tools/crawl_reparse_all.py --entity weapons --entity artifacts --limit 15
python tools/parse_all_categories.py --entity foods --entity materials --limit 50
```

注意：

- 这两个脚本使用 `--limit`，更适合抽样验证、阶段性批处理或离线重解析。
- 如果目的是“完整抓全某个分类”，优先使用第 6 节和第 7 节的显式全量流程。

### 8.2 查看本地结果

```powershell
python main.py store query parsed/weapons "霜结的誓金枝"
python main.py store list parsed/weapons
python main.py store exists pages "哥伦比娅"
```

## 9. 当前已知限制

- `python -m get_genshin_wiki` 不是当前有效入口，因为仓库内没有 `get_genshin_wiki/__main__.py`。
- `parse character` 不会自动联网抓 `语音` 页；要完整语音数据，需要先抓 `"<角色名>语音"`。
- `parse archon-quest` 在缺少 `魔神任务` 列表页时，章节上下文可能不完整。
- 活动任务当前没有专门的“全量批解析脚本”，需要 `crawl event-quests` 后自行循环 `parse event-quest`。
- 编年史当前只有“主页面自动探测”，国家/地区页仍依赖显式标题列表。
- 角色传说任务 / 部族纪闻当前没有 CLI 级 `parse character-quest` 子命令。

## 10. 假设说明

本指南在整理时采用以下假设：

- 统一以“当前代码真实支持的命令和脚本”为准，不再沿用旧 worktree 的仓库路径。
- 对“全部数据”的说明，以“当前已经有实现的数据族”定义，而不是沿用历史愿景清单。
- 对于没有专用全量脚本的数据族，优先给出可直接执行的 PowerShell 循环，而不是停留在概念说明。
