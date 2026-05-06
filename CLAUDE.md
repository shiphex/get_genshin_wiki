# CLAUDE.md

## 项目说明

本项目设计目标是获取 Genshin Impact 游戏的 Wiki 数据，数据将用于大模型训练与微调。

## 最终需要获取的数据

**包括但不限于**(部分列举出来的数据可能不会获取)：

``` json
["角色", "武器", "圣遗物套装", 
 "食物", "任务道具", "冒险道具", 
 "材料", "活动材料", "精炼材料",
 "书籍", "怪物", "野生生物", "动物", 
 "NPC", "北陆图书馆", "提瓦特编年史（公元纪）", 
 "世界任务", "主线", "任务", 
 "传说任务", "多重系列任务", "委托任务",
 "天赋培养素材", "活动系列任务", "活动任务",
 "系列任务", "隐藏任务", "魔神任务",
 "武器强化素材", "武器突破素材", "圣遗物强化素材"]
```

## 项目遵循的规范与开发依赖

- 遵循 `robots.txt` 规则
- 使用 `mediawiki API` 获取列表、页面 `json` 数据
- 使用 `mwparserfromhell` 解析 `json` 数据


## 项目参考

项目参考位于 `refer` 路径下，请勿**调用、修改、删除**其中的文件。

| 文件 |   说明   |
|------|---------|
| `test_get_lists.py` | 测试获取 Genshin Impact 游戏的 Wiki 列表，该列表记录了该 wiki 中数据的分类 |
| `test_get_list_contents.py` | 测试获取 Genshin Impact 游戏的 Wiki 列表中的数据，这些数据是对应列表中的每一个项目 |
| `test_get_page_json.py` | 测试获取 Genshin Impact 游戏的 Wiki 每一个项目页面 `json` 数据 |
| `test_parse_character_json.py` | 测试解析 Genshin Impact 游戏的 Wiki 的`角色`项目页面 `json` 数据，提取出角色的属性、技能等信息，**但数据极其不完善** |
| `test_get_templates.py` | 测试获取 Genshin Impact 游戏的 Wiki 中所有的模板，并解析模板的参数，这些模板是用于创建角色、装备等项目的模板，**但存在一些信息未使用模板导致无法解析** |  

项目参考仅提供设计指引，因参考代码并不完善，尤其是 `refer\test_parse_character_json.py` 、 `refer\test_get_templates.py` 并未达成预期效果。