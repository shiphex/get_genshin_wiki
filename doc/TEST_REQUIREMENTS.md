# TEST_REQUIRMENTS.md

本文件为项目的测试要求文档。

## 测试要求

### 临时文件管理

测试过程中生成的临时文件（如 HTML 页面、JSON 数据等）必须保存到 `tests/output/` 目录，不得留在项目根目录。

### 测试用例要求

- **解析器测试**：每类数据（书籍/角色/任务/剧情等）必须有对应的解析器测试文件，命名格式 `tests/test_*_parser.py`
- **测试覆盖**：单元测试覆盖 HTML 解析、数据模型转换、字段提取
- **回归测试**：修改解析逻辑后运行 `pytest` 确保不破坏已有功能

### 数据完整性验证

- 爬取后检查 JSONL 条目数量是否符合预期
- 验证必填字段（`title`、`url`、`fetched_at`、`content`）非空
- 检查重复条目并去重

### 运行测试命令

```bash
pytest                              # 运行所有测试
pytest tests/test_book_parser.py    # 运行书籍解析器测试
pytest tests/test_*parser*.py        # 运行所有解析器测试
```
