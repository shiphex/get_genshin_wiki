# 怪物数据获取指南

本指南说明如何使用本项目获取原神怪物数据。

## 环境准备

```bash
# 激活虚拟环境
cd E:\Workplace\Learn_project\get_genshin_wiki-monsters
.\.venv\Scripts\Activate.ps1
```

## 获取步骤

### 1. 获取怪物分类列表

```bash
python main.py crawl categories --prefix 怪物
```

### 2. 获取怪物分类成员列表

```bash
python main.py crawl members 怪物
```

### 3. 抓取单个怪物页面

```bash
python main.py crawl page "门扉前的弈局"
python main.py crawl page "遗迹防卫者"
python main.py crawl page "丘丘人"
```

### 4. 解析怪物页面

```bash
# 解析并储存结果（默认保存到 data/parsed/monsters/）
python main.py parse monster "门扉前的弈局"
python main.py parse monster "遗迹防卫者"

# 仅查看解析结果，不保存
python main.py parse monster "丘丘人" --no-persist
```

## 输出格式

解析结果为 JSON 格式，包含以下字段：

| 字段 | 说明 |
|------|------|
| `title` | 怪物名称 |
| `monster_class` | 怪物类别（如：周刷BOSS、精英、普通敌人） |
| `monster_category` | 怪物分类（如：值得铭记的强敌、自律机关） |
| `monster_type` | 怪物类型（如：其他、战争机械） |
| `location` | 出现地点 |
| `drop_materials` | 掉落素材列表 |
| `description` | 怪物介绍，换行使用 `\n` 表示 |

## 存储位置

- 原始页面：`data/pages/`
- 解析结果：`data/parsed/monsters/`

## 示例输出

```json
{
  "title": "门扉前的弈局",
  "monster_class": "周刷BOSS",
  "monster_category": "值得铭记的强敌",
  "monster_type": "其他",
  "location": "蒙德·风起地、（待解「弈局」）",
  "drop_materials": ["升扬样本·骑士", "升扬样本·战车", "升扬样本·王族"],
  "description": "集魔女会诸家技艺而制成的集团军。\n虽然全都是既有技术..."
}
```

## 注意事项

- 遵循 `robots.txt` 规则
- 请求有频率限制，避免短时间内大量请求
- `<br>` 标签在 description 中会被替换为换行符 `\n`
