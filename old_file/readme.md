# 文件结构
``` text
get_genshin_wiki/
├── configs/
│   ├── config.yaml          # 配置文件
│   └── .env.example         # 环境变量模板
├── data/                    # 数据输出目录
├── scripts/
│   └── crawl_sample.py     # 示例爬取脚本
├── src/
│   ├── crawler/
│   │   └── client.py       # MediaWiki API 客户端
│   ├── parser/
│   │   └── wikitext_parser.py  # Wikitext/HTML 解析器
│   ├── cleaner/
│   │   └── text_cleaner.py # 文本清洗模块
│   ├── storage/
│   │   └── writer.py       # 数据存储（JSONL/SQLite）
│   ├── schema/
│   │   └── models.py       # 数据模型定义
│   └── utils/
│       ├── config.py       # 配置加载
│       ├── logger.py       # 日志工具
│       └── rate_limiter.py # 限速器
├── tests/
│   ├── test_cleaner.py
│   ├── test_config.py
│   ├── test_parser.py
│   └── test_schema.py
├── main.py                  # 入口文件
└── pyproject.toml           # 项目配置
```

