# 角色数据获取操作指南

> 精简操作手册，2026-05-07

## 环境依赖

```bash
pip install mwparserfromhell requests
```

## 快速开始

### 方式一：CLI 命令

```bash
# 抓取并解析角色主页面
python -m get_genshin_wiki.cli parse character <角色名>

# 批量抓取（需先配置角色列表）
python -X utf8 tools/crawl_validate_characters.py
```

### 方式二：Python API

```python
from get_genshin_wiki import WikiCrawler, JsonFileStore

# 初始化爬虫
crawler = WikiCrawler()

# 抓取角色页面
page = crawler.get_page("<角色名>")
story_page = crawler.get_page("<角色名>语音")

# 解析
from get_genshin_wiki.parser import parse_character_page
record = parse_character_page(page, voice_page=story_page)
```

## 数据结构

```
data/
├── pages/              # 原始页面 JSON
│   ├── <角色名>__<hash>.json
│   └── <角色名>语音__<hash>.json
├── parsed/
│   ├── characters/     # 角色解析结果
└── reports/           # 完整性报告
```

## 完整性校验

```bash
python -X utf8 tools/crawl_validate_characters.py
```

输出报告位于 `data/reports/character-integrity-report__*.json`，包含 `requested_count`、`ok_count`、`critical_count`、`warning_count`。

## 解析字段说明

| 字段组 | 来源 | 说明 |
|------|------|------|
| `角色` | 主页面 | 角色主信息，包含名称、称号、所属、归属、元素属性、武器类型等表格字段 |
| `角色故事` | 主页面 | `角色详细` 与 `角色故事1..n` |
| `冒险笔记` | 主页面 | `冒险笔记名称` -> `冒险笔记内容` |
| `权能` | 主页面 | 以 `神之眼描述` 为子项名的权能文本 |
| `壹·人物` | 主页面 | `角色介绍1..n` |
| `贰·故事` | 主页面 | 切换板标题 -> 故事正文 |
| `角色语音` | 语音页 | 角色语音（独立页面 `name语音`） |

角色解析结果统一写入 `data/parsed/characters/<角色名>__*.json`，落盘结构为：

```json
{
  "角色": {},
  "角色故事": {},
  "冒险笔记": {},
  "权能": {},
  "壹·人物": {},
  "贰·故事": {},
  "角色语音": {}
}
```
