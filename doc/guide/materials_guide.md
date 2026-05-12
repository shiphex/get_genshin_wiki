# 解析操作指南

本指南说明如何使用 CLI 解析 7 类物品数据。

## 环境要求

```bash
.venv\Scripts\python -m get_genshin_wiki <command>
```

## 解析命令

| 类别 | 命令 | 输出目录 |
|------|------|---------|
| 食物 | `parse food <名称>` | `parsed/foods/` |
| 野生生物 | `parse wildlife <名称>` | `parsed/wildlife/` |
| 任务道具/书籍 | `parse quest-item <名称>` | `parsed/quest-items/` |
| 道具 | `parse item <名称>` | `parsed/items/` |
| 材料 | `parse material <名称>` | `parsed/materials/` |
| 名片 | `parse namecard <名称>` | `parsed/namecards/` |
| 秘境 | `parse secret-item <名称>` | `parsed/secret-items/` |

## 常用操作

**解析单个页面：**
```bash
python -m get_genshin_wiki parse food "花果草糖"
```

**指定源目录（默认 pages）：**
```bash
python -m get_genshin_wiki parse food "花果草糖" --source-namespace pages
```

**不保存，仅输出 JSON：**
```bash
python -m get_genshin_wiki parse food "花果草糖" --no-persist
```

**指定输出目录：**
```bash
python -m get_genshin_wiki parse food "花果草糖" --output-namespace parsed/my-foods
```

## 数据流程

```
Wiki API → crawl page → pages/ → parse <type> → parsed/<type>/
```

1. `crawl page <名称>` 抓取页面到 `pages/` 目录
2. `parse <type> <名称>` 从 `pages/` 读取并解析，输出到 `parsed/<type>/`

## 秘境掉落结构

秘境根据类型输出不同的掉落字段：

- **圣遗物秘境**：输出 `圣遗物1`、`圣遗物2`
- **天赋技能材料秘境**：输出 `天赋技能材料1`、`天赋技能材料2`、`天赋技能材料3`

## 查看已解析数据

```bash
python -m get_genshin_wiki store query parsed/foods "花果草糖"
python -m get_genshin_wiki store list parsed/foods
```