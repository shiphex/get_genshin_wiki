# COMMON_COMMANDS.md

本文件为项目的常用命令文档。

## 基本命令

```bash
# 进入虚拟环境
source .get_wiki/Scripts/activate  # Linux/Mac
# 或
.get_wiki\Scripts\activate  # Windows

# 安装依赖
uv pip install -e ".[dev]"

# 运行测试
pytest

# 运行单个测试文件
pytest tests/test_book_parser.py
```

## 书籍爬取命令

书籍爬取命令 @doc\operation_guide\2026-03-27_书籍爬取操作指南.md ，包括进入虚拟环境、安装依赖、运行测试等。

