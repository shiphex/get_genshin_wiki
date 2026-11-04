# 北陆图书馆数据获取操作指南

本指南说明如何使用本项目获取原神 Wiki 北陆图书馆百科数据。

## 环境依赖

```bash
pip install mwparserfromhell requests
```

## 快速开始

### CLI 命令

一键爬取、解析并持久化北陆图书馆数据：

```bash
python -m get_genshin_wiki.cli crawl north-library
```

命令自动完成以下步骤：
1. 探测 Wiki 上对应分类名称（如 `北陆图书馆`）
2. 通过 MediaWiki API 获取页面原始 wikitext
3. 解析为层级树结构（标题/项目/条目）
4. 将结果持久化为 JSON

### 自定义页面标题

```bash
python -m get_genshin_wiki.cli crawl north-library --title "北陆图书馆"
```

### 仅查看不持久化

```bash
python -m get_genshin_wiki.cli crawl north-library --no-persist
```

## Python API

```python
from get_genshin_wiki import WikiCrawler, WikiTextParser

crawler = WikiCrawler()
parser = WikiTextParser()

# 探测分类并爬取页面
result = crawler.crawl_north_library("北陆图书馆")
payload = result["payload"]

# 解析为结构化数据
record = parser.parse_north_library_page(payload)
record.library_category = result["category_name"]
record.category_candidates = result["category_candidates"]

# 查看节点树
for node in record.nodes:
    print(f"[{node.kind}] {node.title}: {node.text[:50]}...")
```

## 输出结构

解析结果保存在 `data/parsed/north-library/` 目录，JSON 结构如下：

```json
{
  "title": "北陆图书馆",
  "page_id": 301,
  "summary": "北陆图书馆导言\n第二行",
  "categories": ["北陆图书馆"],
  "library_category": "北陆图书馆",
  "category_candidates": ["北陆图书馆", "北陆图书馆攻略"],
  "nodes": [
    {
      "kind": "一级",
      "title": "提瓦特",
      "text": "一级正文",
      "children": [
        {
          "kind": "二级",
          "title": "提瓦特编年史",
          "text": "二级正文",
          "children": [
            {
              "kind": "三级",
              "title": "穿越星海",
              "text": "三级正文",
              "children": [
                {
                  "kind": "四级",
                  "title": "史莱姆",
                  "text": "四级正文",
                  "children": [
                    {
                      "kind": "项目",
                      "title": "时间",
                      "text": "项目正文\n第二行",
                      "children": [
                        { "kind": "条目", "title": "", "text": "普通条目", "children": [] },
                        { "kind": "条目", "title": "周期", "text": "条目正文", "children": [] }
                      ]
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

## 层级解析规则

| 节点类型 | wikitext 格式 | 层级深度 |
|---------|---------------|---------|
| 一级标题 | `=<center>标题</center>=` | 1 |
| 二级标题 | `==标题==` | 2 |
| 三级标题 | `===标题===` | 3 |
| 四级标题 | `====标题====` | 4 |
| 项目 | `'''项目名'''` | 5 |
| 条目 | `*条目内容` | 6 |
| 正文 | 各层级后的普通文本 | 依附于最近标题 |

## CLI 命令汇总

```bash
# 查看帮助
python -m get_genshin_wiki.cli --help
python -m get_genshin_wiki.cli crawl north-library --help

# 爬取与解析
python -m get_genshin_wiki.cli crawl north-library
python -m get_genshin_wiki.cli crawl north-library --title "北陆图书馆"

# 指定输出命名空间
python -m get_genshin_wiki.cli crawl north-library --output-namespace parsed/north-library
```
