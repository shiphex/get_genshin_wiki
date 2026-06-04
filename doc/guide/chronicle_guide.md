# 提瓦特编年史（公元纪）数据获取操作指南

本指南说明如何使用本项目获取原神 Wiki 中的提瓦特编年史数据。

## 环境准备

```bash
# 激活虚拟环境
cd E:\Workplace\Learn_project\get_genshin_wiki-teyvat-chronicle
source .venv/Scripts/activate
```

## 基本流程

### 1. 爬取编年史页面

自动探测编年史分类并爬取页面：

```bash
python main.py crawl chronicle-pages
```

也可手动爬取单个编年史页面：

```bash
python main.py crawl page "提瓦特编年史（公元纪）"
python main.py crawl page "提瓦特编年史"
```

页面原始数据保存在 `data/pages/` 目录。

### 2. 解析为结构化章节树

```bash
python main.py parse chronicle "提瓦特编年史（公元纪）"
python main.py parse chronicle "提瓦特编年史"
```

解析结果保存在 `data/parsed/chronicles/` 目录，格式为 JSON。

### 3. 爬取并解析国家/地区编年史

各国家和地区的编年史数据可通过页面名直接抓取：

```bash
# 各国
python main.py crawl page "蒙德"
python main.py parse chronicle "蒙德"

python main.py crawl page "璃月"
python main.py parse chronicle "璃月"

python main.py crawl page "稻妻"
python main.py parse chronicle "稻妻"

python main.py crawl page "须弥"
python main.py parse chronicle "须弥"

python main.py crawl page "枫丹"
python main.py parse chronicle "枫丹"

python main.py crawl page "纳塔"
python main.py parse chronicle "纳塔"

python main.py crawl page "至冬"
python main.py parse chronicle "至冬"

python main.py crawl page "坎瑞亚"
python main.py parse chronicle "坎瑞亚"

# 其他地区
python main.py crawl page "白夜国"
python main.py parse chronicle "白夜国"

python main.py crawl page "星球"
python main.py parse chronicle "星球"

python main.py crawl page "宇宙"
python main.py parse chronicle "宇宙"
```

## 批量操作

### 批量爬取并解析所有编年史页面

```python
import sys
sys.path.insert(0, '.')

from get_genshin_wiki.cli import main, build_runtime

runtime = build_runtime()

# 所有编年史页面列表
chronicle_pages = [
    '提瓦特编年史', '提瓦特编年史（公元纪）',
    '蒙德', '璃月', '稻妻', '须弥', '枫丹',
    '纳塔', '至冬', '坎瑞亚',
    '白夜国', '星球', '宇宙',
]

for title in chronicle_pages:
    payload = runtime.crawler.crawl_page(title, persist=True)
    result = runtime.parser.parse_chronicle_page(payload)
    runtime.store.write('parsed/chronicles', title, result.to_dict())
    print(f'已解析: {title}')
```

## 输出结构

编年史采用"书籍式章节树"格式，按标题层级组织。

### JSON 顶层结构

```json
{
  "title": "提瓦特编年史",
  "intro": "",
  "sections": [
    {
      "title": "太古",
      "level": 3,
      "content": "",
      "items": [],
      "subsections": [
        {
          "title": "原初",
          "level": 4,
          "content": "",
          "items": [],
          "subsections": [
            {
              "title": "原初之人",
              "level": 5,
              "content": "遥远时空的故事里。巨人盘古的血液化作江河...",
              "items": [],
              "subsections": []
            }
          ]
        }
      ]
    }
  ],
  "categories": [],
  "page_id": 4972
}
```

### 编年史章节对应法则

| 目录标题等级 | `action=raw` 中对应格式 | 说明 |
|-------------|------------------------|------|
| 三级 | `=== 太古 ===` | 编年史中的大章节 |
| 四级 | `==== 原初 ====` | 大章节下的子章节 |
| 五级 | `===== 原初之人 =====` | 子章节下的细节目录 |
| 项目 | `'''时间'''` | 加粗标记的具体项目 |
| 条目 | `* 条目内容` | 项目下的条目列表 |
| 正文 | 各级标题后面的内容 | 章节/项目的正文内容 |

### 各页面章节数量参考

| 页面 | 三级章节 | 子章节 |
|------|---------|--------|
| 提瓦特编年史 | 11 | 31 |
| 提瓦特编年史（公元纪） | 1 | 0 (6 个年份项目) |
| 蒙德 | 34 | 80 |
| 璃月 | 17 | 64 |
| 稻妻 | 16 | 46 |
| 须弥 | 20 | 41 |
| 枫丹 | 10 | 34 |
| 纳塔 | 13 | 48 |
| 至冬 | 12 | 55 |
| 坎瑞亚 | 9 | 39 |
| 白夜国 | 4 | 5 |
| 星球 | 10 | 0 |
| 宇宙 | 2 | 0 |

## CLI 命令汇总

```bash
# 查看帮助
python main.py --help
python main.py crawl chronicle-pages --help
python main.py parse chronicle --help

# 编年史分类探测与抓取
python main.py crawl chronicle-pages
python main.py crawl chronicle-pages --page-limit 10

# 单页爬取
python main.py crawl page "页面名"

# 编年史解析
python main.py parse chronicle "页面名"
python main.py parse chronicle "页面名" --no-persist

# 指定数据根目录
python main.py --data-root data/my_chronicle_data crawl chronicle-pages
python main.py --data-root data/my_chronicle_data parse chronicle "提瓦特编年史（公元纪）"
```
