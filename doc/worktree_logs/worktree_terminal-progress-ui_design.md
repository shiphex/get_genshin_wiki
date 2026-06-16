# 终端显示界面设计

## 目标

为长时间运行的抓取/解析命令设计轻量终端界面，例如：

- `python main.py all`
- `python main.py all weapons`
- `python main.py all characters`

界面必须信息丰富，同时避免引入复杂的显示库。

## 现有行为

当前 `all` 命令在 Python 中构建结果，并在最后打印 JSON。共享管道和特殊运行器已经足够产生进度事件：

- `python main.py all` 的实体顺序是固定的
- 标准实体处理器遍历具体的标题列表
- 特殊处理器遍历显式的条目列表或成员标题
- `_run_all_title_pipeline()` 是标题级进度的自然钩子

这意味着显示工作应集中在埋点和渲染上，而不是发明新的执行模型。

## 设计需求

1. `stdout` 必须保留用于最终 JSON 输出
2. 实时进度必须在 `stderr` 上渲染
3. 显示必须不依赖 `rich`、`textual`、`prompt_toolkit` 或类似库即可工作
4. 输出被重定向或 ANSI 不可用时，必须优雅降级
5. 尽可能同时显示顶层实体进度和条目级进度

## 建议架构

引入一个小的进度抽象：

```python
class ProgressSink(Protocol):
    def run_started(self, event: RunStarted) -> None: ...
    def item_started(self, event: ItemStarted) -> None: ...
    def item_finished(self, event: ItemFinished) -> None: ...
    def item_failed(self, event: ItemFailed) -> None: ...
    def run_finished(self, event: RunFinished) -> None: ...
```

具体实现：

- `NullProgressSink`：测试和非交互式使用的空操作默认实现
- `TerminalProgressSink`：交互式 `stderr` 渲染器
- （可选）`LineProgressSink`：当完整重绘不适用时，单行日志降级方案

## 渲染器规则

- 使用 `sys.stderr.isatty()` 检测 TTY
- 使用 `shutil.get_terminal_size()` 限制宽度
- 仅重绘仪表盘区域，不重绘整个回滚缓冲区
- 在状态变化时刷新，对高噪声循环可选限流
- 保留的历史记录量小，例如最近 5 个已完成项

## 显示布局

建议布局：

```text
[all] entity 4/17 | item 58/240 | 24.2% | elapsed 00:03:18
Current : weapons :: parse :: 霜结的誓金枝
Done    : [ok] 「渔获」 0.7s | [ok] 薙草之稻光 0.9s | [ok] 西风长枪 0.6s
Pending : next entity artifacts | next items 千岩长枪, 贯月矢, 匣里灭辰
Status  : persist=yes | page_limit=none | warnings=0 | failures=0
```

对于单实体运行，第一行变为：

```text
[weapons] 58/132 pages | 43.9% | elapsed 00:03:18
```

## 事件语义

每个条目事件应携带：

- `entity_id`
- `phase` 如 `discover`、`crawl`、`parse`、`persist`
- `title`
- `index`
- `total`
- `started_at`
- `finished_at`
- `status` 如 `ok`、`failed`、`skipped`、`resumed`

对于 `python main.py all`，渲染器还应接收顶层实体事件：

- 当前实体索引
- 实体总数
- 已完成实体摘要
- 待处理实体列表

## 待处理项策略

UI 必须显示待处理项，但应保持轻量：

- 在可行时，每个实体只计算一次具体标题队列
- 仅显示接下来几个待处理标题，而不是整个积压列表
- 对于动态发现流程，显示下一个已知项，并在队列确定后保持计数精确

## 集成点

建议的钩子位置：

- `handle_all_everything()` 中的解析器/运行器设置
- `_run_all_title_pipeline()` 中的共享标题循环
- 每个特殊 `all` 运行器在 `crawl_page`、解析和持久化操作前后
- 每个实体完成后的摘要生成

避免将终端渲染代码直接混入解析逻辑。运行器应触发事件；接收器应负责渲染。

## 兼容性规则

- 如果 `stderr` 不是 TTY，自动禁用仪表盘
- 如果 `stdout` 被重定向，最终 JSON 行为必须保持不变
- 如果将来需要标志，优先使用 `--progress` 和 `--no-progress`
- 键盘交互不在范围内

## 失败展示

失败应立即可见：

- 当前行切换为 `failed`
- 已完成历史记录保存错误状态
- 最终状态行包含失败计数
- 最终 JSON 输出仍然是完整机器可读细节的来源

## 验收检查清单

- 交互式 `all` 运行时出现实时仪表盘
- JSON 输出在 `stdout` 上保持机器可读
- 已完成、当前、进度和待处理状态均可见
- 渲染器在 PowerShell 中无需额外依赖即可工作
- 非交互式使用保持干净整洁
