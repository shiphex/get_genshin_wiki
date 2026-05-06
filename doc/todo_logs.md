---
time: 2026-05-06
title: 重构 `get_genshin_wiki\cli.py`
designer: Zhou Hao
executor: /codex:rescue --model gpt-5.4 --effort xhigh
---
重构 `get_genshin_wiki\cli.py` ，从而可通过 `parser.add_argument` 函数指定爬取特定的项目，对储存的数据也可以执行特定的操作如存储、查询、更新、添加、删除等。

---
time: 2026-05-06
title: 设计项目架构
designer: Zhou Hao
executor: /codex:rescue --model gpt-5.4 --effort xhigh
---
## 设计项目架构

根据 `CLAUDE.md` 及 `refer` 路径下参考代码，设计项目架构，确定项目的目录结构、模块划分、测试方案、数据存储方式等。要求：
- 项目架构设计合理，能够满足项目的需求，同时具有良好的可维护性和可扩展性
- 代码分层式设计，让基础代码与业务代码分离，使基础代码复用性高，模块性好，基础代码与业务代码调用关系清晰
- 测试覆盖率达到 90% 以上，测试用例设计合理，能够覆盖各种边界情况和异常情况
- 数据存储方式合理，能够满足数据的存储、查询、更新、添加、删除等需求，同时保证数据的安全性和可靠性

项目架构设计文档保存在 `doc` 路径下，文件名为 `project_architecture.md`