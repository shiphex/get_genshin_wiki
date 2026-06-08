# Feature Spec: 角色传说任务与部族纪闻

> 此文件由 Git Worktree Design Skill 自动产生，供 AI Agent 作为开发指引。

## 分支资讯

| 项目 | 值 |
|------|-----|
| 分支名称 | `feature/character-quests` |
| 基于分支 | `main` |
| Worktree 路径 | `E:\Workplace\Learn_project\get_genshin_wiki-character-quests` |
| 建立时间 | 2026-06-08 |

## 目标

爬取并解析原神 Wiki 中的角色传说任务和部族纪闻数据，包括任务名称、相关角色、章节/幕、任务流程、对话、旁白等信息。数据储存模式参考 `feature/archon-quests`（魔神任务）和 `feature/event-quests`（活动任务）分支。

### 数据结构层级

```
传说任务列表页（`https://wiki.biligame.com/ys/传说任务`）
  └─ 章（章名）
       └─ 幕（幕名）
            ├─ 任务1
            │   ├─ 任务描述
            │   └─ 对话
            │       ├─ 角色/NPC/派蒙 对白
            │       ├─ 旅行者 对白
            │       ├─ 选项（玩家选择分支）
            │       └─ 旁白/场景叙述
            ├─ 任务2
            │   ├─ 任务描述
            │   └─ 对话（同上结构）
            └─ 任务n ...
```

### 需要获取的内容

1. 以「漩涡之遗」为例：  
| 验收 | 项目 | 子项 | 内容 | 注释 |
|------|------|------|------|-----|
| [ ] | 任务 | 名称 | 漩涡之遗 | 最小子任务名称 |
| [ ] | 任务 | 任务地区 | 璃月 |  |
| [ ] | 任务 | 任务类型 | 传说任务 |  |
| [ ] | 所属任务 |  | 盐花 | `系列任务=`后的文本，格式为`章名称，幕名称`的幕名称 |
| [ ] | 所属章 | 名称 | 古闻之章 | `系列任务=`后的文本，格式为`章名称，幕名称`的章名称；也可在`https://wiki.biligame.com/ys/盐花`中`副标题=`后的文本，格式为`章名称 幕编号` |
| [ ] | 所属幕 | 编号 | 第一幕 | 可在`https://wiki.biligame.com/ys/盐花`中`副标题=`后的文本中，格式为`章名称 幕编号` |
| [ ] | 所属幕 | 名称 | 盐花 |  |
| [ ] | 前置任务 |  | 旧日之影 |  |
| [ ] | 后续任务 |  | 深锁之迹 |  |
| [ ] | 任务描述 |  | 偶遇钟离之后，你得知愚人众克列门特正在组建考古小队，除了自告奋勇加入的考古学家宛烟之外，钟离也被聘请成为顾问。虽然你信不过愚人众，但在钟离的邀请下，你还是加入了这支考古小队，而你们的第一个调查目标，则是「漩涡之魔神」奥赛尔。 |  |
| [ ] | 任务n | 任务描述 | （任务目标/描述文本） | 每个幕包含多个任务，n 从 1 开始 |
| [ ] | 任务n | 任务流程 | ===与言笑对话=== | 每个任务有多个流程，流程名位于两个`===`中间 |
| [ ] | 对话 | 角色/NPC | （非旅行者的角色对白） | 包含派蒙、NPC 等角色的台词 |
| [ ] | 对话 | 旅行者 | （旅行者的对白） | 区分旅行者与其他角色的对话 |
| [ ] | 对话 | 选项 | （玩家可选择的多个回复） | 因玩家选择不同导致的分支对话 |
| [ ] | 对话 | 旁白 | （场景叙述、动作描写） | 无说话者的叙述文本 |



*注意*：
- 通过 `https://wiki.biligame.com/ys/传说任务` 下 `==传说任务和部族纪闻==`中的子项目，逐级检索章、幕、任务
- 所有对话按顺序记录，包括角色/NPC对白、旅行者对白、玩家选项分支、旁白
- 所有项目都需要提取验收
- 数据源为 `https://wiki.biligame.com/ys/传说任务`，内容为中文
- 优先使用 `mwparserfromhell` 解析 wikitext，无法处理时使用正则或手动解析
- 对话内容中的 `<br>` 替换为 `\n`
- 奖励数据**不需要**提取，但**任务描述**需要提取

## 实作范围

- [x] 确定 Wiki 分类名称（`传说任务` 和 `部族纪闻`，需实际探测确认）
- [x] 在 `models.py` 新增 `CharacterQuestRecord` 数据模型（参考 `ArchonQuestRecord` / `EventQuestRecord`），包含：
  - 任务名称 (title)
  - 任务类型 (quest_type) — 区分传说任务/部族纪闻/邀约任务
  - 相关角色 (related_character)
  - 任务描述 (description)
  - 章节/幕 (chapter / act)
  - 前置任务 / 后续任务
  - 任务流程 (objectives / steps)
  - 对话 (dialogues, 参考 `ArchonQuestDialogue`)
- [x] 在 `parser.py` 实现列表页与详情页解析方法：
  - `parse_character_quest_list_page()` — 解析列表页
  - `parse_character_quest_page()` — 解析详情页
- [x] 创建 `tools/batch_character_quests.py` — 批量抓取与解析脚本
- [x] 创建 `tools/generate_character_quest_index.py` — 索引生成脚本
- [x] 编写测试用例验证解析结果

## 验收标准

- 能够成功抓取传说任务和部族纪闻分类下的所有页面
- 解析结果包含任务章节结构、对话、奖励等结构化信息
- 数据可正确序列化为 JSON 并持久化到 `data/` 目录
- 批量脚本 `batch_character_quests.py` 可正常运行

## 技术约束

- 遵循 `robots.txt` 规则
- 使用 `mediawiki API` 获取列表、页面 `json` 数据
- 使用 `mwparserfromhell` 解析 wikitext
- 复用现有 `WikiCrawler`、`MediaWikiClient`、`JsonFileStore` 基础设施
- 复用 `QuestRewardRecord` 辅助模型
- 数据存储 namespace: `parsed/character-quests`、`parsed/character-quest-index`

## 跨分支备注

- 与 `feature/archon-quests`（魔神任务）、`feature/event-quests`（活动任务）共享 QuestRecord 设计模式
- 合并时需注意 `models.py` 的 `QuestRewardRecord` 是否已存在（主分支可能已包含）
- 无强依赖关系，可独立开发与合并
