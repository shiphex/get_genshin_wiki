# 冻结快照离线恢复

该入口只恢复已保存的 WikiText，不初始化 crawler、MediaWikiClient 或模型，不请求渲染 API、不下载媒体。`--offline` 必须提供；uv 自身也必须使用 `--offline`。

## 运行

在仓库根目录执行。先在联网环境准备好依赖并验证版本；如需要转移到离线机器，应按其操作系统准备兼容的完整环境或缓存：

```powershell
uv sync --frozen --group dev
uv run --no-sync python tools/recover_snapshot.py --help
```

随后执行完全离线恢复。将 `snapshot_input` 替换为包含 `pages/` 的快照根目录，将清单路径替换为对应的原始哈希基线；输出目录必须是新的空目录：

```powershell
uv run --offline --no-sync python tools/recover_snapshot.py --input-root "snapshot_input" --output-root "data/recovery/run-001" --offline --manifest "snapshot_manifest.json"
```

准备阶段的 uv sync 可以联网；恢复阶段必须保留 uv 的 `--offline` 和恢复入口的 `--offline`，不得联网补齐缺失依赖。`--manifest` 是可选的外部哈希基线；不提供时仍核对运行前后的全部输入文件哈希，但无法确认输入与交接基线相同。也可激活已准备好的 `.venv`，直接用 `python tools/recover_snapshot.py ... --offline` 执行。

输出目录必须是新的空目录，不能位于输入内、包围输入，或落入 raw/pages/parsed/category_members 存储目录。输出中途失败后应保留该目录并换一个目录重试；未生成最终摘要不能视为验收完成。

## 输出契约

| 文件 | 用途 |
|---|---|
| `text_units.jsonl` | 权威文本单元，保留原文、来源、场景和分支 |
| `scenes.jsonl` | 场景、字段上下文、重复标题及合法空段落 |
| `parsed/`、`character_quests.json` | 兼容业务投影，按完整原页面标题命名 |
| `pages.jsonl` | 每个输入页面的处置及来源引用 |
| `dependencies.jsonl` | 重定向、辅助语音页和缓存引用页的消费关系 |
| `candidates.jsonl` | 独立枚举的原文中文候选节点及逐项处置 |
| `issues.jsonl` | 缺来源、未知规则、循环、歧义和原始源块 |
| `summary.json`、`summary.md` | 保真、结构检查、恢复收益和剩余问题 |
| `input_manifest.json`、`output_manifest.json` | 输入及输出 SHA-256 清单，输出清单不包含自身 |

单元字段：`unit_id`、`type`、`text`、`speaker`、`scene_id`、`branch_path`、`branch_status`、`source`、`source_kind`。类型为 `dialogue/option/narration/voice/story/book/description/annotation`。来源性质为 `game_excerpt/wiki_editorial/unknown`，来源性质未知的介绍文字不能自动当作官方游戏摘录。

`source` 保存页面 ID、完整标题、输入相对文件名、WikiText SHA-256、已有 revision ID，以及原始解码字符串中的 `[start, end)` 字符范围。缺 revision ID 保持 null。`speaker_source` 单独保留说话者原文；`consumed_by` 保留同一个来源被其他页面消费的上下文。ID 和排序由来源身份及位置确定，不用时间或随机值。

`source` 是重放原文的完整范围；`text_spans` 是实际参与可见文字的叶节点范围，独立校验器按它们统计导出证据，不能把颜色名和未渲染参数计成正文。`display_status=partial` 表示显示模板仍有未知参数；参数源块保留在问题清单。场景另保存 `title_source`。

语义补修后，台词附着的黑幕候选注释单独保存为 `annotation`，不进入业务对话数组。
它们保留原文来源、场景、分支，`annotation_status=unresolved` 表示不能自动把所有黑幕
认定为 Wiki 说明。主单元新增可选 `excluded_spans`，列出从台词显示中分离、另行保存的
原始范围；应使用 `replay_unit()` 重放，不能仅对整个 source 范围调用 `display_text()`。
说话者中的明确编者请求对应 `speaker_excluded_spans`，而儿童等不确定限定词保留并诊断。
仅有黑幕的发言和书籍等非对白隐藏正文不直接删除。

任务对话中的明确阅读动作、文档物件标签，以及冒号位于配对引号内的整句引用，
按旁白保留完整标签和正文。恢复单元的可选 `classification_reason` 记录这类行级判断；
同一折叠或选项分支内的真实对白继续单独识别。署名注释的判断只使用冒号后的正文，
避免把完整黑幕正文误拆为注释。不完整角色名引号仍保留发言并标记
`speaker_status=unresolved` / `unbalanced_speaker_quote`，不猜测修正原文。
第二轮语义补修与范围见 [文档/UI 补修报告](../reports/document_ui_fix_2026-11-04.md)。

剧情内非角色文本仍为 `type=narration`，恢复层增加 `narration_kind`：

| 值 | 使用依据 |
|---|---|
| `narrative` | 显式“旁白”或剧情中的任务描述模板 |
| `document` | 文档折叠、文档物件标签、公告板语境中的通告行，或明确展示的阅读正文 |
| `interface` | 阅读、调查等交互动作提示 |
| `unknown` | 无标记、引用性质不明或 Wiki 编者补充，保留并诊断 |

所有旁白的 `speaker=null`、`speaker_status=not_applicable`；显式“旁白”标签的
原文范围另存 `narration_label_source`。文档连续段落以 `document_id` 和
`document_title` 关联，不跨真实对白、不同分支或文档作用域。嵌套的展示折叠
继承最近的明确文档语境；公告板标题只辅助识别通告标签，不改变同处真人对白。

`narration_kind` 不决定出处：`source_kind` 单独记录。未知叙述为 `unknown`，
双冒号编者文本为 `wiki_editorial`；附着黑幕候选注释继续独立存为 annotation。
纯黑幕正文保留并诊断。未知分类产生 `unclassified_narration`，不能当成已完成语义验收。
业务四字段及活动任务的中文类型值保持兼容，细分类别只从恢复 API / 新 JSONL 读取。
执行与抽样范围见 [剧情旁白修正](../reports/story_narration_fix_2026-11-04.md)。

业务 JSON 的字段和四种对话类型保持不变；直接消费权威 JSONL 的程序需要支持新的
annotation 类型和来源排除范围，并将 annotation 与游戏对白分开处理。

`branch_path=[]` 是已确认的线性归属，`null` 是未解决归属。每一层选择/tab/条件记录组 ID、选项 ID、原文标签及可重放的来源范围。未明确的连接、性别、角色姓名不会补写。旧数组仍可兼容使用；下游必须从权威 JSONL 按来源、场景、分支和消费上下文切分。

## 校验和限制

- 独立校验器重新遍历原文，未使用正文提取或显示清理函数来枚举候选节点；删除导出证据不会使源节点消失。
- 每个候选节点处置为 exported、metadata、non_story、needs_source 或 unsupported；未知业务字段不会自动被归为元信息。
- 保守恢复比例为 exported / (exported + unsupported + needs_source)。这覆盖已保存来源中的候选节点，包含尚未裁定的 Wiki 内容；不是全游戏剧情覆盖率。节点比例与中文字符比例分别报告。
- 媒体引用和未缓存依赖无法推算缺失正文长度，必须查看缺来源清单；不能用图片文件名推断图片文字。
- 已确认显示规则包括颜色、注音、明确 HTML 包装、折叠/折叠框、人物对话及剧情参数。未知模板原块保留；带参数的未知缓存模板不会猜测绑定关系。
- 缓存模板只在明确剧情消费上下文中提取可支持的正文，排除 noinclude 文档、样式和脚本；无关联示例不生成剧情。
- 缓存消费先应用 onlyinclude/noinclude 可见性，再提取业务内容；重复消费合并全部场景和分支上下文。无业务消费者的模板页仍留在源清单中，不直接当作游戏正文。
- `data/` 沿用 Git 忽略规则。派生数据留在本地，提交代码、测试、文档、spec 和短报告；不切换现有 RAG。

## 从 V2.1 升级

V2.2.0 的离线恢复、角色任务批处理与独立索引使用完整原标题存储和引用，展示名称仍保留。旧汇总若缺少 `source_title` 或页面身份，需从冻结来源重新解析；不要按展示名把同名页面合并。输出始终放入新目录，旧 parsed 和原始快照保留。统一 CLI 的 `all character-quests` 仍有展示名去重和 resume 限制，不用于这一身份验收。

旧对话数组只作兼容投影。新来源与分支的权威输出是 `text_units.jsonl`，RAG 接入应按来源、场景、分支及 `consumed_by` 上下文独立验收。

运行测试：`python -m pytest -q`。真实测试页面是冻结快照的 19 份原始 payload 副本，输入原件不参与修改；测试对它们的文件和 WikiText 哈希逐项核对。
