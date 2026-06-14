# Feature Spec: Simplify Crawl-Parse-Store Pipeline

> 原始文件名：`git-worktree-spec.md`，原位于仓库根目录。
>
> 此文件由 Git Worktree Design Skill 自动产生，供 AI Agent 作为开发指引。

## 分支资讯

| 项目 | 值 |
|------|-----|
| 分支名称 | `feature/simplify-pipeline` |
| 基于分支 | `main` (`e9b7b7c`) |
| Worktree 路径 | `E:\Workplace\Learn_project\get_genshin_wiki-simplify-pipeline` |
| 建立时间 | 2026-06-14 |

## 目标

新增 `python main.py all` 顶层命令，消除当前需要手动写 PowerShell 循环或多步执行的工作流。

**之前**（以武器为例）：

```powershell
python main.py crawl category-pages "武器"
$titles = python main.py store query category_members "武器" | ConvertFrom-Json
foreach ($title in $titles) {
    python main.py parse weapon $title | Out-Null
}
```

**之后**：

```powershell
python main.py all weapons
```

| 命令 | 效果 |
|------|------|
| `python main.py all weapons` | 抓取并解析全部武器 |
| `python main.py all characters` | 抓取并解析全部角色（含语音页） |
| `python main.py all event-quests` | 抓取并解析全部活动任务（含活动主页） |
| `python main.py all chronicles` | 抓取并解析全部编年史页面 |
| `python main.py all north-library` | 抓取并解析北陆图书馆 |
| `python main.py all archon-quests` | 抓取并解析全部魔神任务（含列表页 + 索引） |
| `python main.py all character-quests` | 抓取并解析全部角色传说任务 / 部族纪闻 + 索引 |
| `python main.py all` | 抓取并解析全部 17 类数据 |

## 实作范围

### Phase 1: CLI 框架

- [x] 在 `get_genshin_wiki/cli.py` 中新增 `all` 子命令组
- [x] 定义所有 entity 子命令：`weapons`、`artifacts`、`monsters`、`books`、`foods`、`wildlife`、`quest-items`、`items`、`materials`、`namecards`、`secret-items`、`characters`、`event-quests`、`chronicles`、`north-library`、`archon-quests`、`character-quests`
- [x] 每个子命令支持 `--page-limit` 和 `--no-persist`
- [x] `archon-quests` 和 `character-quests` 额外支持 `--resume`
- [x] 无子命令时（`python main.py all`）执行全量流水线

### Phase 2: 流水线 handler 实现

- [x] 新增 `handle_all_standard_entity()`，通用 handler，复用 `tools/reparse_and_store.py` 的 `ENTITY_CONFIGS`
- [x] 新增 `handle_all_characters()`，包含语音页抓取
- [x] 新增 `handle_all_event_quests()`，包含活动主页抓取
- [x] 新增 `handle_all_chronicles()`，硬编码编年史标题列表
- [x] 新增 `handle_all_north_library()`，复用现有一体命令逻辑
- [x] 新增 `handle_all_archon_quests()`，复用 `tools/batch_archon_quests.py` 逻辑
- [x] 新增 `handle_all_character_quests()`，复用 `tools/batch_character_quests.py` 逻辑
- [x] 新增 `handle_all_everything()`，串联全部实体

### Phase 3: 代码复用

- [x] 从 `tools/reparse_and_store.py` 导入 `ENTITY_CONFIGS`（或将其抽取到 `get_genshin_wiki/` 包中）
- [x] 复用现有 `CliRuntime` / handler 模式
- [x] 提取共用的 `crawl -> parse` 循环逻辑为私有 helper

### Phase 4: 文档更新

- [x] 更新 `doc/guide/unified_operation_guide.md`
- [x] 更新 `doc/project_architecture.md`
- [x] 更新 `CLAUDE.md`

## 验收标准

- `python main.py all weapons --page-limit 5` 完成抓取 -> 解析 -> 存储全流程
- `python main.py all characters --page-limit 3` 自动抓语音页并解析
- `python main.py all event-quests --page-limit 5` 自动抓活动主页并解析
- `python main.py all --help` 显示所有可用 entity
- `python main.py all` 接 `--page-limit` 可跑通全量流水线
- 所有现有 `crawl` / `parse` / `store` 命令行为不变
- 文档已更新

## 技术约束

- 不引入新依赖
- 复用 `tools/reparse_and_store.py` 的 `ENTITY_CONFIGS`，不重复定义映射表
- 复用现有 `CliRuntime` 与 handler 函数签名
- 保持现有 CLI 签名、存储路径、文件命名规则不变
- 标准实体使用 `robots.txt` 校验（通过 `client.assert_api_allowed()`）

## 跨分支备注

- 本次仅 1 个 feature 分支，无并行依赖
- 建议在 `feature/add-version-region` 之后合并（两者都改 `cli.py`，但本分支改动更小且不冲突）

## 建议验证命令

```powershell
# 验证帮助输出
python main.py all --help

# 验证单类（小样本）
python main.py all weapons --page-limit 3

# 验证角色（含语音）
python main.py all characters --page-limit 2

# 验证全量（小样本）
python main.py all --page-limit 2
```
