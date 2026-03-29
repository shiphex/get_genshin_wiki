# ARCHITECTURE.md

本文件描述项目架构，包括项目目录结构、模块职责、文件组织等。

## 项目架构

```
src/                          # 可复用模块（库）
├── crawler/                  # MediaWiki API 客户端
│   └── client.py             # MediaWikiClient
├── parser/                   # HTML 解析器（按数据类型分）
│   ├── book_parser.py        # 书籍解析器
│   └── arms_parser.py        # 武器解析器
├── storage/                  # 数据写入模块（Python 包）
│   ├── writer.py             # BookStorage
│   └── arms_writer.py        # ArmStorage
├── utils/                    # 通用工具（配置、日志）
│   ├── config.py
│   └── logger.py
└── old_file/                 # 旧版文件，已废弃

scripts/                      # 入口脚本（供人工执行）
├── crawl_books.py            # 爬取书籍入口
├── crawl_arms.py             # 爬取武器入口
└── debug/                    # 调试脚本（不常使用）
    ├── test_book_list.py
    ├── test_single_book.py
    ├── test_arms_list.py
    ├── test_single_arm.py
    ├── test_single_arm_save.py
    └── ...

tests/                        # pytest 测试（自动化）
├── test_book_parser.py       # 书籍解析器测试
├── test_arms_parser.py       # 武器解析器测试
└── output/                   # 测试临时文件

storage/                      # 爬取数据存储（根目录）
├── book/
│   ├── books.jsonl
│   ├── failed_books.txt
│   └── cleaned/
└── arm/
    ├── arms.jsonl
    ├── arms.json
    └── failed_arms.txt

configs/                      # 配置文件
doc/
├── plan/                     # 开发方案文档
└── operation_guide/          # 操作指南
```

### 路径职责说明

| 路径 | 内容 | 说明 |
|------|------|------|
| `src/` | 可复用模块 | crawler、parser、storage、utils |
| `scripts/` | 人工执行入口 | `crawl_*.py` 入口脚本 |
| `scripts/debug/` | 调试脚本 | test_/save_ 脚本，不常使用 |
| `tests/` | pytest 测试 | `test_*_parser.py`，仅自动化测试 |
| `storage/` | 数据目录 | 爬取输出的数据文件 |

**注意**：`src/storage/` 是 Python 包（代码），`storage/` 是数据目录（文件），两者同名但处于不同命名空间，不冲突。