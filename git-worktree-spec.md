# Feature Spec: 冻结快照剧情恢复

## 分支资讯

- 分支：`feature/snapshot-story-recovery`
- 基线：`develop/v2.2` / `fb801552c4125614e324d4b5e676c87ba7c86b6f`
- Worktree：`E:\Workplace\Learn_project\get_genshin_wiki-snapshot-recovery`
- 日期：2026-10-10（Asia/Singapore）

## 目标

仅从冻结快照恢复中文剧情，保留来源、场景和原文明示的分支，输出新的派生数据；不修改输入、genshin_agent 或现有 RAG。

## 实作范围

- [x] 恢复测试基线，并建立 19 个真实案例与受控边界回归测试。
- [x] 修复原页面身份、存储、聚合、resume、排序和索引引用。
- [x] 共用来源定位与显示清理，支持剧情容器、场景及空段落。
- [x] 在兼容展平前提取选项、tabber、嵌套选择和条件分支。
- [x] 新增完全离线的 tools/recover_snapshot.py，记录依赖消费及缺失来源。
- [x] 独立扫描候选节点，报告每个页面和节点的处置。
- [ ] 两次全量运行、来源重放、输出一致性、输入哈希和完整测试验收。
- [ ] 交付本地派生数据、版本化报告和文档。

## 验收标准

- 四个幕间小憩保持独立来源；月夜，泊船码头恢复实际对白、旁白和空场景。
- 19 个真实案例与嵌套选择、重复台词、重名场景、依赖缺失、重定向循环及歧义测试通过。
- 导出单元可回查原文并确定性重放；来源范围是解码 WikiText 的零基半开字符范围。
- 权威 text_units.jsonl 保留来源、场景和分支；兼容业务数组不作为分支权威。
- 同输入两次输出文本单元、ID 和顺序一致；11,439 份输入文件哈希不变。
- 每个页面和候选节点都有处置；未知节点、规则和依赖不静默丢弃。
- 完整测试通过，HTTP、socket 和模型访问在离线测试中失败。

## 技术约束

- 输入：`E:\Workplace\Learn_project\genshin_agent\data\raw\genshin_wiki_data_20260605`，只读。
- 交接与案例：`E:\Workplace\Learn_project\genshin_agent\rag\experiments\recovery`，只读。
- 哈希清单：`E:\Workplace\Learn_project\genshin_agent\rag\data\recovery_handoff\genshin_wiki_data_20260605\snapshot_manifest.json`，只读。
- 最终输出：原项目 `data/recovery/genshin_wiki_data_20260605`；不覆盖非空目录。
- 复用 WikiTextParser、mwparserfromhell、业务模型及 JsonFileStore（仅用于输出）。
- 不联网、不调用 LLM、不初始化 crawler，不猜人物身份或补写正文。
- 区分游戏原文、Wiki 整理、元信息和非剧情；不得仅凭战斗词或百分数过滤。
- 缺少 revision ID 保持 null；未知分支使用 null，已确认线性路径使用 []。
- 派生数据留在本地且被 Git 忽略；版本化代码、测试、spec、文档和报告。

## 跨分支备注

本分支顺序实现；不依赖 feature/llm-data-format，不合并、不推送。RAG 接入另起任务。

## 执行记录

- 2026-10-10：创建独立 worktree；Git 元数据写权限使用已批准的升级操作。
- Ruling: 以本文件作为计划和进度账本，沿用仓库指定的 spec 工作流，避免并行维护相互冲突的计划文件。
- 基线：修正 tests/test_cli.py 的无效导入括号，完整测试 77 passed / 18 subtests passed。
- RED：26 个新增测试在实现前失败；同名页面聚合仅得到 1 条，来源 API 与离线入口尚不存在。
- 页面身份：存储、聚合、resume 和索引的 11 个相关测试通过。
- Ruling: 月夜，泊船码头原文有 6 个段落内容参数；兼容业务流程验收按实际 6 段，权威场景另保留描述及章节简述，不人为增加第 7 个流程。
- Task 1-6 complete: 完整测试 115 passed / 18 subtests passed，包含来源重放、独立源清单删除证据实验、HTTP/DNS 禁止、缓存模板及参数未知边界。
- 全量首轮：5,946 页、172,181 单元、来源重放 0 失败；规则后续完善，最终输出待同版本两次全量验收。
- Ruling: uv 使用 --offline --no-project 调用原项目已安装的 Python 环境，避免在新 worktree 联网安装依赖；指南提供有本地环境时的 --no-sync 写法。
- 来源和分支边界完善后：116 passed / 18 subtests passed；14 个真实任务另有首尾台词及精确位置的原文字面断言。
