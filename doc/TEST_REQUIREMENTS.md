# TEST_REQUIREMENTS.md

本文件为项目的测试要求文档。

## 测试要求

### 临时文件管理

测试过程中生成的临时文件（如 HTML 页面、JSON 数据等）必须保存到 `tests/output/` 目录，不得留在项目根目录。

### 测试用例要求

#### 解析器测试

每类数据（书籍/武器/圣遗物等）必须有对应的解析器测试文件，命名格式 `tests/test_*_parser.py`。

测试覆盖：
- HTML 解析正确性
- 数据模型转换（to_dict 输出）
- 字段提取完整性
- 段落边界处理（书籍使用 `\n\n` 分隔）

#### 告警规则测试

每类数据对应的告警规则必须有测试验证：
- `empty_list_page` - 列表页抓取数量为 0
- `empty_book_volumes` - 书籍卷数为 0
- `invalid_artifact_piece_count` - 圣遗物部件数不足 5
- `writer_failure` - 数据写入失败

测试文件：`tests/test_alerts_rules.py`

#### 运行摘要/Manifest 测试

每次爬取生成的 manifest 必须包含以下字段：
- `run_id` - 运行唯一标识
- `namespace` - 内容类型命名空间
- `started_at` / `finished_at` - 运行时间
- `source_page` - 来源页面
- `fetched_count` - 抓取数量
- `saved_count` - 成功保存数量
- `failed_count` - 失败数量
- `warning_count` - 警告数量
- `parser_version` - 解析器版本
- `config_snapshot` - 配置快照

测试文件：`tests/test_storage_runtime.py`

#### 存储落盘测试

验证 raw/cleaned/structured 三层存储是否正确创建：
- `storage/<namespace>/raw/` - 原始 HTML
- `storage/<namespace>/cleaned/` - 清洗后文本
- `storage/<namespace>/structured/` - 结构化 JSONL
- `storage/<namespace>/failed/` - 失败记录
- `storage/<namespace>/manifests/` - 运行摘要
- `storage/<namespace>/alerts/` - 告警记录

测试文件：`tests/test_storage_layout.py`

#### 集成测试

测试完整爬取流程：
1. 列表页解析（extract_*_links）
2. 单详情页解析（parse_*_page）
3. 数据落盘（save）
4. Manifest 生成

测试文件：`tests/test_*_integration.py`（如存在）

### 数据完整性验证

- 爬取后检查 JSONL 条目数量是否符合预期
- 验证必填字段（`title`、`url`、`fetched_at`、`content`）非空
- 检查重复条目并去重
- 验证段落边界：书籍 volumes.content 使用 `\n\n` 分隔段落

### 运行测试命令

```bash
# 运行所有测试
pytest

# 运行书籍解析器测试
pytest tests/test_book_parser.py -v

# 运行武器解析器测试
pytest tests/test_arms_parser.py -v

# 运行圣遗物解析器测试
pytest tests/test_artifacts_parser.py -v

# 运行所有解析器测试
pytest tests/test_*parser*.py -v

# 运行告警规则测试
pytest tests/test_alerts*.py -v

# 运行存储相关测试
pytest tests/test_storage*.py -v

# 运行特定测试文件
pytest tests/test_book_parser.py -v -k "test_parse"
```

### 测试夹具管理

真实页面样本应保存到 `tests/fixtures/html/<namespace>/` 目录下，用于：
- 回归测试
- 页面结构变化检测
- 解析器行为验证

夹具文件命名建议：
- `list_page.html` - 列表页样本
- `detail_<name>.html` - 详情页样本

### 回归测试要求

修改解析逻辑后必须运行回归测试，确保：
1. 书籍段落边界保持 `\n\n` 分隔
2. 圣遗物列表提取不依赖 `visible-xs` 以外的假设
3. 武器解析各字段正确提取
4. 所有告警规则正确触发
5. Manifest 包含所有必填字段