# CLAUDE.md

## 项目目标

当前发布版本：`2.2.0`。版本元数据与锁文件保持一致，发布说明见 `docs/releases/V2.2.0.md`。

本项目用于抓取并解析 bilibili 原神 Wiki（`https://wiki.biligame.com/ys/`）的数据，输出原始页面 payload 与结构化 JSON，供后续数据清洗、检索、训练和验证使用。

当前仓库已经不是单一“角色解析器”，而是一个多数据族抓取与解析仓库。已落地支持的范围包括：

- 角色
- 武器
- 圣遗物套装
- 怪物
- 书籍
- 食物
- 野生生物
- 任务道具
- 道具
- 材料
- 名片
- 秘境
- 提瓦特编年史
- 北陆图书馆
- 活动任务
- 魔神任务
- 角色传说任务 / 部族纪闻

## 当前推荐文档入口

- 统一操作入口：`docs/guide/unified_operation_guide.md`
- 架构说明：`docs/project_architecture.md`
- 分项指南：`docs/guide/*.md`
- 历史开发记录：`docs/worktree_logs/*.md`
- 冻结快照恢复：`docs/guide/snapshot_recovery_guide.md`
- 发布说明：`docs/releases/*.md`

说明：

- `docs/guide/*.md` 中有不少历史分项说明，但统一执行路径与命令应以 `unified_operation_guide.md` 为准。
- `docs/worktree_logs/` 是历史 worktree 日志，不应继续作为“当前怎么操作”的权威来源。

## 代码结构认知

### 核心包

- `get_genshin_wiki/client.py`
  - MediaWiki API 访问、分页、限流、重试、`robots.txt` 校验。
- `get_genshin_wiki/crawler.py`
  - 通用抓取编排与专项分类探测。
- `get_genshin_wiki/parser.py`
  - 通用页面解析与各实体解析器。
- `get_genshin_wiki/storage.py`
  - `JsonFileStore`，负责本地 JSON 命名空间存储。
- `get_genshin_wiki/cli.py`
  - `crawl / parse / all / store` 四组命令。
- `get_genshin_wiki/recovery/`
  - 来源定位、可见文字证据、场景与分支提取、兼容投影及独立校验。

### 运行入口

- `main.py`
  - 当前最稳妥的统一 CLI 入口。
- `tools/*.py`
  - 批处理、索引生成、抽样验证、重解析脚本。

### 参考与测试

- `refer/`
  - 参考实现和探索脚本，只能参考，不应作为生产代码改造目标。
- `tests/`
  - 覆盖 CLI、crawler、parser、storage、批处理脚本与索引生成。

## 命令与数据规范

### 统一命令写法

文档或脚本示例优先使用：

```powershell
python main.py ...
```

原因：

- 该写法不依赖额外的 console script 安装。
- 仓库当前没有 `get_genshin_wiki/__main__.py`，因此不应再写 `python -m get_genshin_wiki ...`。

环境准备使用 `uv sync --frozen --group dev`，再激活 `.venv`；也可使用 `uv run python main.py ...`。当前项目为源码运行的 virtual project，uv sync 不安装项目 console script，不应将其写成默认可用入口。

### 存储规范

- 17 类实体的根对象统一输出 `所属版本` 字符串；角色普通和精简格式均支持。多版本原序顿号连接，数字/月版本不互转，缺失/无效/冲突为空；子项不新增版本。
- `versions.py` 只提取主体元数据，不从正文、食谱版本或更新时间推断；损坏模板的原文回退须保留参数位置证据并限制主体范围。
- `tools/refresh_parsed_offline.py` 完全离线刷新现有记录；默认只暂存，`--apply` 验证并备份后覆盖正式 parsed、两任务汇总及 `recovery/full-offline-20261104`。版本之外的业务变化阻断应用；原始缓存、其他实验、历史 ZIP 和 RAG 不改。
- 用户确认同步旧解析数据时，可显式使用 `--baseline-business-root`，仅接受与同输入、已核验哈希的独立解析器基线完全一致的既有差异；逐项保留前后值，不放宽新回归或已有版本冲突检查。

- 原始页面统一进入 `data/pages/`
- 分类成员统一进入 `data/category_members/`
- 解析结果统一进入 `data/parsed/<namespace>/`
- 文件名格式统一为 `{规范化标题}__{sha1前10位}.json`
- 角色任务批处理、独立索引与离线恢复使用完整原页面标题作存储键，保留 `source_title`、`page_id`，任务名称只用于展示；缺少身份的旧汇总需重解析。
- 离线恢复使用新的 `data/recovery/<实验目录>/`，保留权威文本单元和未知节点，不覆盖现有数据。

### 全量处理规范

- 标准实体现在优先使用 `python main.py all <entity>`；保留“抓分类页 + 循环 parse”的显式流程作为调试 / 回归手段。
- 魔神任务优先使用 `python main.py all archon-quests`；角色传说任务 / 部族纪闻使用 `python tools/batch_character_quests.py`。统一 CLI 的 `all character-quests` 仅复用部分批处理辅助函数，仍按展示名去重和判断 resume，不能保证同名页面身份。
- 活动任务、编年史、北陆图书馆现在也都有 `python main.py all ...` 统一入口；文档中仍要写清楚它们依赖的额外上下文页或内置标题列表。

## 文档维护要求

更新项目能力时，至少同步检查以下文档是否需要改：

- `docs/guide/unified_operation_guide.md`
- `docs/project_architecture.md`
- 与该能力直接相关的 `docs/guide/*.md`
- `CLAUDE.md`

写文档时必须遵守：

- 以当前代码实现为准，不复述已经过时的 worktree 路径。
- 不把“规划中的能力”写成“已经支持的能力”。
- 如果某条命令依赖额外上下文页，例如角色语音页、魔神任务列表页、活动主页，必须写清楚。

## 当前已知现状

- `parse character` 会尝试读取本地 `"<角色名>语音"` 页面，但不会自动联网补抓。
- `parse archon-quest` 在本地存在 `魔神任务` 列表页时，章节/幕上下文更完整。
- `python main.py all event-quests` 会补抓关联活动主页并完成全量解析；单页调试仍可继续使用 `crawl event-quests` 与 `parse event-quest`。
- `python main.py all north-library` 与 `crawl north-library` 共用同一条“抓取 + 解析 + 持久化”逻辑；当前仍没有独立 `parse north-library` 子命令。
- `python main.py all character-quests` 已提供全量入口，但当前仍没有 CLI 级 `parse character-quest` 单页子命令，单页调试依赖 Python API。

## 当前测试状态

本分支已修复 `tests/test_cli.py` 的无效 import 括号，恢复完整测试收集，并新增冻结来源恢复测试。当前状态必须以实际执行 `python -m pytest -q` 为准；最终验收记录见 `docs/reports/snapshot_recovery_2026-10-10.md`。

V2.2.0 的验证基线为 122 passed / 18 subtests passed。文档更新不能自动将历史 TODO 或未支持规则标为已验收。

## 冻结快照恢复

- `WikiTextParser.recover_page` 返回带原文位置、场景和分支的文本。
- `tools/recover_snapshot.py --offline` 只读解析本地快照，不初始化 crawler 或联网补依赖。
- `text_units.jsonl` 是来源与分支的权威输出；旧业务数组是兼容投影。
- 折叠剧情、HTML 对话边界和章节前导对白由共享恢复层处理；不要改用会删除模板的纯文本章节作为剧情来源。
- 未标记的折叠换行片段保留为旁白并诊断；旧 parsed 和汇总必须重解析，不能使用 resume 跳过。0605 验收见 `docs/reports/fold_dialogue_2026-10-30.md`。
- 第一轮 0605 语义验收已被 12 页独立审计否决，后续补修与限制以 `docs/reports/fold_dialogue_audit_fix.md` 为准，不能把全套测试通过写成全库语义无遗漏。
- 台词附着黑幕单独保存为 recovery annotation，excluded_spans / speaker_excluded_spans 用于重放和保留来源；业务对话不混入说明。文档明细保留为旁白，空冒号后缀不静默返回。
- 阅读动作、文档物件标签和有配对引号的整句引用按行识别为旁白，保留标签全文；不将混合折叠整体改为文档。不完整角色名引号保留并诊断，见 `docs/reports/document_ui_fix_2026-11-04.md`。
- 输入与现有 RAG 不修改；输出写新的 `data/recovery/` 目录，未知规则和缺来源必须保留。
- 剧情旁白在恢复层用 `narration_kind` 区分 narrative/document/interface/unknown，文档连续段落用 document_id 关联；旁白没有角色身份。未知分类保留诊断和未知来源，业务格式不增加字段，见 `docs/reports/story_narration_fix_2026-11-04.md`。
- 使用与限制见 `docs/guide/snapshot_recovery_guide.md`。

## 约束

- 抓取逻辑必须遵守 `robots.txt`。
- 不要把 `refer/` 中的脚本当成生产接口。
- 不要新增和当前代码不匹配的文档入口或虚构命令。
