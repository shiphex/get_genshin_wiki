# ARCHITECTURE.md

本文件描述当前项目架构，包括目录结构、模块职责、运行入口和数据落盘方式。

## 当前架构

```text
src/
├── alerts/                      # 结构化告警
│   ├── reporter.py              # Alert / AlertReporter
│   └── rules.py                 # 通用告警规则
├── content/                     # 按内容类型组织的业务层
│   ├── base.py                  # 运行结果基础类型
│   ├── registry.py              # namespace 注册表
│   ├── runtime.py               # 通用 crawl 运行时
│   ├── books/
│   │   ├── parser.py
│   │   ├── validator.py
│   │   └── writer.py
│   ├── arms/
│   │   ├── parser.py
│   │   ├── validator.py
│   │   └── writer.py
│   └── artifacts/
│       ├── parser.py
│       ├── validator.py
│       └── writer.py
├── crawler/
│   └── client.py                # MediaWikiClient
├── linkchecker/
│   ├── checker.py               # 链接检查器，依赖 content.registry
│   ├── comparator.py
│   └── models.py
├── parser/                      # 兼容层，保留旧导入路径
│   ├── book_parser.py
│   ├── arms_parser.py
│   └── artifacts_parser.py
├── storage/                     # 通用存储层 + 兼容层
│   ├── base_storage.py
│   ├── layout.py
│   ├── raw_store.py
│   ├── cleaned_store.py
│   ├── record_store.py
│   ├── failure_store.py
│   ├── manifest_store.py
│   ├── writer.py
│   ├── arms_writer.py
│   └── artifacts_writer.py
└── utils/
    ├── config.py
    └── logger.py

scripts/
├── crawl_books.py               # 书籍爬取入口
├── crawl_arms.py                # 武器爬取入口
├── crawl_artifacts.py           # 圣遗物爬取入口
├── check_links.py               # 链接更新检查入口
└── debug/                       # 手工调试脚本

tests/
├── fixtures/
│   └── html/
│       └── artifacts/           # 解析器真实/近真实样本
├── output/                      # 测试过程输出
├── test_book_parser.py
├── test_arms_parser.py
├── test_artifacts_parser.py
├── test_link_checker.py
└── test_storage_runtime.py

storage/
├── books|book/                  # 书籍数据（新结构优先，兼容旧目录）
├── arms|arm/                    # 武器数据
├── artifacts/                   # 圣遗物数据
└── links/                       # 链接快照
```

## 模块职责

### `src/content/`

- `registry.py` 维护 `books`、`arms`、`artifacts` 的统一注册信息，包括列表页标题、parser、validator、writer 和脚本入口。
- `runtime.py` 提供统一运行时：读取列表页、过滤已抓取/失败项、抓取详情页、执行校验、保存结构化数据、输出 manifest 和 alerts。
- `content/<namespace>/parser.py` 只负责 HTML 解析。
- `content/<namespace>/validator.py` 负责关键字段和结构告警。
- `content/<namespace>/writer.py` 负责把类型数据转换为 cleaned 文本，并复用通用存储层落盘。

### `src/storage/`

- `layout.py` 统一规划 `raw/cleaned/structured/failed/manifests/alerts` 目录。
- `record_store.py` 负责 JSONL 结构化记录。
- `raw_store.py` 保存原始 HTML，`cleaned_store.py` 将清洗文本按 namespace 聚合到单个 JSON 文件。
- `failure_store.py` 保存失败记录。
- `manifest_store.py` 保存每次运行摘要。
- `base_storage.py` 组装上述存储组件，并兼容旧目录中的 `*.jsonl` / `failed_*.txt` 读取。
- `cleanup.py` 提供按项目、文件类型、缓存、日志过滤的清理能力，供 `scripts/cleanup_storage.py` 调用。

### `src/alerts/`

- `rules.py` 提供最小告警规则：列表页为空、关键字段缺失、书籍卷数为 0、圣遗物部件数不足 5、写盘失败。
- `reporter.py` 负责聚合告警、写入 `alerts_<run_id>.json`、同时输出日志。

### `src/linkchecker/`

- `checker.py` 不再硬编码 parser/page title 映射，改为依赖 `content.registry`。
- `scripts/check_links.py` 通过 registry 读取对应的爬虫入口。

### 兼容层

- `src/parser/*.py` 和 `src/storage/*writer.py` 仅做导出适配，避免旧测试和旧脚本导入路径失效。

## 运行流程

1. `scripts/crawl_*.py` 加载配置与日志。
2. 调用 `src.content.runtime.run_crawl(namespace, config)`。
3. `runtime` 通过 `registry` 构造 parser / validator / writer。
4. 抓取列表页并解析链接。
5. 过滤已保存和已失败条目。
6. 逐条抓取详情页，解析后写入：
   - `raw/` 原始 HTML
   - `cleaned/<namespace>.json` 聚合后的清洗文本
   - `structured/<namespace>.jsonl` 结构化记录
7. 运行结束后写入：
   - `manifests/manifest_<run_id>.json`
   - `alerts/alerts_<run_id>.json`

## 存储语义

每个 namespace 在逻辑上都采用以下布局：

```text
storage/<namespace>/
├── raw/
├── cleaned/
│   └── <namespace>.json
├── structured/
│   └── <namespace>.jsonl
├── failed/
│   └── failed_<namespace>.txt
├── manifests/
└── alerts/
```

兼容说明：

- 若配置仍使用 `book_dir` / `arm_dir` / `artifact_dir`，新代码会继续在对应根目录下工作。
- 读取已保存/失败记录时，会兼容旧根目录中的 `books.jsonl`、`arms.jsonl`、`artifacts.jsonl` 以及对应 `failed_*.txt`。

## 配置约定

`configs/config.yaml` 与 `src/utils/config.py` 默认暴露以下存储键：

- `output_dir`
- `books_dir`
- `arms_dir`
- `artifacts_dir`
- `links_dir`
- `book_dir` / `arm_dir` / `artifact_dir`（兼容旧配置）

## 测试结构

- 解析器测试继续使用 `tests/test_*_parser.py`。
- `tests/fixtures/html/` 保存 HTML 样本。
- `tests/test_storage_runtime.py` 覆盖统一写盘布局、manifest 和 alerts 产物。
- `tests/test_cleanup_storage.py` 覆盖清理目标筛选和实际删除逻辑。
- 测试生成文件统一落到 `tests/output/`。
