# 书籍数据获取操作指南

本指南说明如何使用本项目获取原神书籍数据。

## 环境准备

```bash
# 激活虚拟环境
cd E:\Workplace\Learn_project\get_genshin_wiki-books
.\.venv\Scripts\Activate.ps1

# 或使用 bash
source .venv/Scripts/activate
```

## 基本流程

### 1. 查看书籍列表

```bash
python main.py crawl members "书籍"
```

### 2. 爬取单本书籍页面

```bash
python main.py crawl page "白夜国馆藏"
```

页面数据保存在 `data/pages/` 目录。

### 3. 解析书籍为结构化数据

```bash
python main.py parse book "白夜国馆藏"
```

解析结果保存在 `data/parsed/books/` 目录，格式为 JSON。

## 批量操作

### 批量爬取并解析

```python
import json
import sys
import io
sys.path.insert(0, '.')

from get_genshin_wiki.cli import main, build_runtime

runtime = build_runtime()

# 获取书籍列表
old_stdout = sys.stdout
sys.stdout = io.StringIO()
main(['crawl', 'members', '书籍'])
output = sys.stdout.getvalue()
sys.stdout = old_stdout
books = json.loads(output)

# 爬取并解析前10本
for book_name in books[:10]:
    payload = runtime.crawler.crawl_page(book_name, persist=True)
    result = runtime.parser.parse_book_page(payload)
    runtime.store.write('parsed/books', book_name, result.to_dict())
    print(f'已解析: {book_name}')
```

## 输出结构

解析后的 JSON 结构：

```json
{
  "title": "白夜国馆藏",
  "genre": "史书、工具书、小说",
  "country": "稻妻",
  "volumes": [
    {
      "name": "常世国龙蛇传",
      "description": "取材自海祇岛民间故事的小说...",
      "location": "稻妻城<「八重堂」编辑>黑田购买获得",
      "content": "造化藏奥妙，日月行吉凶。\n三隅隔昏暗..."
    }
  ],
  "categories": [],
  "page_id": 37920
}
```

## 国家代码映射

| 代码 | 国家 |
|------|------|
| 0 | 提瓦特 |
| 1 | 蒙德 |
| 2 | 璃月 |
| 3 | 稻妻 |
| 4 | 须弥 |
| 5 | 枫丹 |
| 6 | 纳塔 |
| 7 | 挪德卡莱 |
| 8 | 至冬 |

## CLI 命令汇总

```bash
# 查看帮助
python main.py --help
python main.py parse book --help

# 爬取
python main.py crawl page "书名"

# 解析
python main.py parse book "书名"
python main.py parse book "书名" --no-persist

# 指定命名空间
python main.py parse book "书名" --source-namespace pages --output-namespace parsed/books
```
