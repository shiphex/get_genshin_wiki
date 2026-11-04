# 实体版本与离线更新 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this approved plan task-by-task.

**Goal:** 给全部实体增加顶层所属版本，并离线验证、备份和覆盖正式派生数据。

**Architecture:** 共享版本提取器解析主体元数据，模型负责序列化。独立离线工具从冻结缓存生成业务和完整恢复输出，验收后事务式替换目标。

**Tech Stack:** Python 3.11+, mwparserfromhell, pytest, JSON/JSONL.

**Spec:** 用户在本轮明确要求实施的《实体版本补全与离线解析更新方案》。

## Global Constraints

- 全程离线；原始 pages/category_members/categories、历史 ZIP 和其他 recovery 实验不改。
- 只增加实体顶层“所属版本”，缺失/无效/冲突为空；多版本保持原序，数字与月版本不互转。
- 不向子项添加版本，不改变对白、旁白或分支；其他业务差异须阻断，用户明确授权且由独立改动前解析器基线复现的既有差异除外。
- 保持角色两种 schema、完整页面身份、任务索引和顺序，不修改软件版本和 RAG。

## Review Focus

- 嵌套 Wiki 查询破坏 AST 参数边界，明确版本须受限回退并留下证据。
- 嵌套子项/食谱版本不得填充父实体，技术示例与占位符不得误识别。
- 版本之外业务差异、同名任务身份和聚合记录须逐项检查。
- 覆盖前并发变更及替换失败须保留正式结果并支持回滚。
- 恢复重跑须保持来源、分支、清单和确定性，不能将丰富角色格式覆盖精简格式。

## Task 1: 版本提取与模型

**Files:** 新建 get_genshin_wiki/versions.py、tests/test_versions.py；修改 parser.py、models.py。

**Interfaces:** extract_version(title, wikitext) 返回 value/status/evidence 的 VersionResolution；实体 version 默认空，to_dict/to_storage_dict 根字段统一“所属版本”。

- [x] 先写版本、父子隔离、双角色格式、魔神序列化和真实材料回退测试，观察失败。
- [x] 实现共享提取和所有主体模型接入；运行新增测试和全套测试。

## Task 2: 离线刷新工具

**Files:** 新建 tools/refresh_parsed_offline.py、tests/test_refresh_parsed_offline.py。

**Interfaces:** run_refresh(data_root, apply=False, work_root=None) 默认暂存，--apply 备份后替换；reuse offline_guard/run_recovery。

- [x] 先写离线、上下文、差异拒绝、同名汇总、回滚及并发检查测试，观察失败。
- [x] 枚举正式命名空间，以冻结本地来源重解析；重建全量 recovery 两遍核对确定性；生成版本证据和缺失报告。
- [x] 全部检查通过后备份并覆盖指定业务、两汇总和 full-offline-20261104；更新报告，失败回滚。

## Task 3: 全量验收及说明

- [x] 全套 pytest、已知旁白验证、实际离线全量暂存检查。
- [x] 验证无额外业务变化、输入哈希、文本与分支稳定，应用并复核正式产物。
- [x] 更新 README、统一指南、恢复指南、架构、CLAUDE 与验证报告。

## Execution record

- 继续在用户指定的现有 develop/v2.3 工作区实施，保留已有未提交修改，不创建额外 worktree；后续按用户要求清理临时文件、整理忽略规则并提交推送。
- Task 1: complete — 基线225测试/18子测试；新增41项先失败后通过，追加布局标签和损坏武器回退2项并通过。
- Task 2: 工具初始10项先失败后通过；追加落盘验证/源路径2项先失败后通过。独立审查指出示例回退、批次内并发和最终验收回滚3项，新增13项先失败后通过。
- 实际预检阻断661份非版本业务差异，未覆盖正式数据。用户明确选择“覆盖已核实的既有解析差异，并逐项留报告”。新增显式独立业务基线模式及2项先失败后通过的测试；未匹配基线的变化仍阻断。
- Pre-flight: 版本提取 → 主体模型/解析器 → 离线业务适配器 → full recovery；冻结输入指纹、双角色格式和任务页面身份一致。
- Task 2: complete — 70项新增回归通过；全套295 passed / 18 subtests passed。661项全部用8fde9a2原始parser/models离线复现并通过哈希基线接受，无新业务差异。
- Task 3: complete — 更新4829份业务及魔神汇总，完整恢复两遍与正式落盘一致；5478根版本、4810原文证据、837任务正文、523汇总记录及5963原始文件经独立复核通过。旁白抽样与F1–F4通过。完整数据备份与报告保留在.uv-cache/entity-versions/full-apply-20261104。
- 用户要求清理与发布：删除重复运行产物和缓存，保留备份ZIP/证据/有效基线；新增日志、临时文件和测试缓存忽略规则，冻结版本fixture禁用换行转换。
