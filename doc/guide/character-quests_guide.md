# 角色传说任务与部族纪闻数据获取指南

本指南对应 `feature/character-quests` worktree，说明如何使用当前分支中的实现抓取、解析并归档原神 Wiki 中的角色传说任务和部族纪闻数据。

## 环境准备

要求：

- Python `>= 3.11`
- 可访问 bilibili Wiki API

推荐在仓库根目录执行：

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

如果只安装最小依赖，也可以执行：

```bash
pip install mwparserfromhell requests
```

## 推荐流程

### 1. 批量抓取并解析

当前分支的主入口是批量脚本 `tools/batch_character_quests.py`。该脚本会自动：

- 探测实际可用的 Wiki 分类（`传说任务`、`部族纪闻`）
- 抓取列表页 `传说任务`
- 抓取分类成员页面
- 跳过 `系列任务` / `多重系列任务` 页面，只保留叶子任务页
- 解析任务记录并写入本地存储
- 生成按系列分组的索引

```bash
python tools/batch_character_quests.py
```

可选参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--data-root` | 数据根目录 | `data/` |
| `--output` | 汇总输出文件 | `data/character_quests.json` |
| `--list-title` | 列表页标题 | `传说任务` |
| `--resume` | 断点续跑，跳过已写入汇总文件的任务 | 关闭 |

示例：

```bash
python tools/batch_character_quests.py --resume
python tools/batch_character_quests.py --data-root data/dev --output data/dev/character_quests.json
```

### 2. 生成叶子任务索引

`tools/generate_character_quest_index.py` 会输出按任务粒度展开的独立索引文件，适合下游检索或检查前置/后续关系：

```bash
python tools/generate_character_quest_index.py
```

可选参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--data-root` | 数据根目录 | `data/` |
| `--output` | 索引输出文件 | `data/character_quest_index.json` |
| `--list-title` | 列表页标题 | `传说任务` |

## 手动调试流程

当前 CLI 没有暴露 `parse character-quest` 子命令。需要单页调试时，建议先抓取页面，再通过 Python API 解析。

### 1. 抓取列表页和目标页

```bash
python main.py crawl page "传说任务"
python main.py crawl page "漩涡之遗"
```

如果要手动抓取分类成员：

```bash
python main.py crawl members "传说任务"
python main.py crawl members "部族纪闻"
```

### 2. 在 Python 中解析单页

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

## 输出位置

- 分类探测结果：`data/categories/character-quests__*.json`
- 分类成员列表：`data/category_members/传说任务__*.json`、`data/category_members/部族纪闻__*.json`
- 原始页面 payload：`data/pages/<标题>__<hash>.json`
- 叶子任务解析结果：`data/parsed/character-quests/<任务名>__<hash>.json`
- 分组索引：`data/parsed/character-quest-index/传说任务__<hash>.json`
- 批量汇总输出：`data/character_quests.json`
- 独立叶子索引：`data/character_quest_index.json`

`JsonFileStore` 使用 `{规范化标题}__{sha1前10位}.json` 命名，避免中文标题重名或非法文件名字符冲突。

## 解析结果结构

叶子任务页会序列化为 `CharacterQuestRecord.to_dict()` 对应的结构：

```json
{
  "任务名称": "漩涡之遗",
  "任务地区": "璃月",
  "任务类型": "传说任务",
  "相关角色": "钟离",
  "出场人物": ["钟离", "克列门特", "宛烟"],
  "所属章": "古闻之章",
  "所属幕": "第一幕",
  "所属幕名称": "盐花",
  "所属任务": "盐花",
  "前置任务": "旧日之影",
  "后续任务": "深锁之迹",
  "任务描述": "偶遇钟离之后，你决定加入这支考古小队。",
  "任务流程": ["前往孤云阁", "与众人交谈"],
  "对话": [
    {
      "说话者": "派蒙",
      "内容": "我们真的要去孤云阁吗？",
      "类型": "character",
      "所属任务流程": "前往孤云阁"
    }
  ]
}
```

对话字段说明：

| 字段 | 说明 |
|------|------|
| `说话者` | 角色名；旁白可能为空 |
| `内容` | 对话或叙述文本，`<br>` 会转成 `\n` |
| `类型` | `character` / `traveler` / `option` / `narration` |
| `所属任务流程` | 对话归属的流程标题 |

## 索引文件说明

### 批量脚本写入的分组索引

`data/parsed/character-quest-index/` 中的索引按系列任务分组，每条记录包含：

- `title`
- `chapter_name`
- `act`
- `act_name`
- `region`
- `quest_type`
- `related_character`
- `tasks`

其中 `tasks` 是该组下叶子任务的有序列表。

### 独立叶子索引

`data/character_quest_index.json` 中的 `index` 数组按叶子任务展开，每条记录包含：

- `title`
- `region`
- `quest_type`
- `chapter_name`
- `act`
- `act_name`
- `related_quest`
- `related_character`
- `前置任务`
- `后续任务`

## 当前实现的行为与限制

- 覆盖范围是列表页 `== 传说任务和部族纪闻 ==` 章节，不包含 `邀约事件`
- 列表解析同时兼容传统链接写法和 `{{图标|任务|...}}` 写法
- 对 `（任务）`、`（系列任务）` 结尾的标题会做归一化，避免同一任务重复落盘
- `--resume` 依据规范化后的任务标题跳过已存在记录
- 批量脚本不会把系列页本身写入 `parsed/character-quests`，只写叶子任务页
- 奖励数据不在当前提取范围内
- 如果需要命令行单页解析能力，需要后续为 CLI 单独补 `parse character-quest` 子命令
