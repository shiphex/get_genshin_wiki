# crawl_artifacts.md

本文件为圣遗物爬取相关资料文档，包含圣遗物爬取的目标、实际架构、组件关系和目录结构。

## 圣遗物爬取目标

- 圣遗物图鉴所在网页[圣遗物图鉴](https://wiki.biligame.com/ys/%E5%9C%A3%E9%81%97%E7%89%A9%E5%9B%BE%E9%89%B4)
- 圣遗物列表所在网页[圣遗物图鉴]中圣遗物都属于`<div class="visible-xs">`类
  - 例如：`</a><div class="visible-xs"><a href="/ys/%E6%99%A8%E6%98%9F%E4%B8%8E%E6%9C%88%E7%9A%84%E6%99%93%E6%AD%8C" title="晨星与月的晓歌">晨星与月的晓歌</a></div>`可跳转`晨星与月的晓歌`的链接地址`https://wiki.biligame.com/ys/%E6%99%A8%E6%98%9F%E4%B8%8E%E6%9C%88%E7%9A%84%E6%99%93%E6%AD%8C`，该链接地址为每件圣遗物的详情页
- 每套圣遗物的详情页，如[如雷的盛怒](https://wiki.biligame.com/ys/%E5%A6%82%E9%9B%B7%E7%9A%84%E7%9B%9B%E6%80%92)、[晨星与月的晓歌](https://wiki.biligame.com/ys/%E6%99%A8%E6%98%9F%E4%B8%8E%E6%9C%88%E7%9A%84%E6%99%93%E6%AD%8C)，该网页链接可在'圣遗物图鉴'网页中找到
- 获取圣遗物的相关信息：
  - 套装名称
  - 稀有度
  - TAG
  - 实装版本
  - 2件套效果
  - 4件套效果
  - 生之花（名称 + 描述）
  - 死之羽（名称 + 描述）
  - 时之沙（名称 + 描述）
  - 空之杯（名称 + 描述）
  - 理之冠（名称 + 描述）
  - 获取途径
  - 圣遗物故事（每件圣遗物独立的 lore）

## 部分信息获取方式

以圣遗物`晨星与月的晓歌`为例，获取其相关信息的网页代码如下：

### 套装名称

存在网页代码如：
```html
<div class="icon">
<div class="autoimg"><img alt="晨星与月的晓歌生之花.png"...></div>
...
</div>
<div class="name">晨星与月的晓歌</div>
```
可获得圣遗物套装名称：`晨星与月的晓歌`

### 稀有度

稀有度通过星级图片确定：
```html
<div class="star">
<img alt="圣遗物套装-4星.png"...>&nbsp;&nbsp;~&nbsp;&nbsp;<img alt="圣遗物套装-5星.png"...>
</div>
```
该圣遗物稀有度为 4-5 星（通过图片名称 `4星.png`、`5星.png` 确定范围）

### TAG

文本位于：
```html
<div class="tag"><b>TAG：</b>伤害、后台触发、月曜</div>
```
可获得 TAG：`伤害`、`后台触发`、`月曜`  
TAG按`、`区分，分条保存

### 实装版本

文本位于：
```html
<div class="tag" style="margin:0"><b>实装版本：</b>月之四</div>
```
可获得实装版本：`月之四`

### 2件套效果、4件套效果

文本位于：
```html
<table class="effect">
<tbody>
<tr>
<td>2件套</td>
<td>元素精通提高80点。
</td>
</tr>
<tr>
<td>4件套</td>
<td>装备者处于队伍后台时，造成的月曜反应伤害提升20%；队伍的月兆等级至少为满辉时，造成的月曜反应伤害进一步提升40%。上述效果将在装备者位于场上3秒后移除。
</td>
</tr>
</tbody>
</table>
```
可获得 2件套效果：`元素精通提高80点。`
可获得 4件套效果：`装备者处于队伍后台时，造成的月曜反应伤害提升20%；队伍的月兆等级至少为满辉时，造成的月曜反应伤害进一步提升40%。上述效果将在装备者位于场上3秒后移除。`

### 圣遗物部件（5件套）

每件圣遗物都有独立的名称和描述，格式如下：

**生之花：**
```html
<div class="icon">
<div class="autoimg"><img alt="晨星与月的晓歌生之花.png"...></div>
<div class="main"><div class="up">献与月的华梦</div><div class="down">生之花</div></div>
</div>
```
可获得：`生之花 - 献与月的华梦`

**死之羽：**
```html
<div class="icon">
<div class="autoimg"><img alt="晨星与月的晓歌死之羽.png"...></div>
<div class="main"><div class="up">献与月的离光</div><div class="down">死之羽</div></div>
</div>
```
可获得：`死之羽 - 献与月的离光`

**时之沙：**
```html
<div class="icon">
<div class="autoimg"><img alt="晨星与月的晓歌时之沙.png"...></div>
<div class="main"><div class="up">献与月的终时</div><div class="down">时之沙</div></div>
</div>
```
可获得：`时之沙 - 献与月的终时`

**空之杯：**
```html
<div class="icon">
<div class="autoimg"><img alt="晨星与月的晓歌空之杯.png"...></div>
<div class="main"><div class="up">献与月的酹祭</div><div class="down">空之杯</div></div>
</div>
```
可获得：`空之杯 - 献与月的酹祭`

**理之冠：**
```html
<div class="icon">
<div class="autoimg"><img alt="晨星与月的晓歌理之冠.png"...></div>
<div class="main"><div class="up">献与月的银冕</div><div class="down">理之冠</div></div>
</div>
```
可获得：`理之冠 - 献与月的银冕`

### 获取途径

获取途径位于 `<div class="get">` 区域，包含多个获取源：
```html
<div class="get">
<div class="title">获取方式</div>
<div class="item">
<div class="access">
<div class="head"><img alt="圣遗物套装-获取途径-副本.png"...></div>
<div class="mid"></div>
<div class="title">副本</div>
<div class="content">（4星）：祝圣秘境：月童的库藏 Ⅰ至Ⅳ概率掉落。</div>
</div>
<div class="access">
<div class="head"><img alt="圣遗物套装-获取途径-副本.png"...></div>
<div class="mid"></div>
<div class="title">副本</div>
<div class="content">（5星）：祝圣秘境：月童的库藏 Ⅲ至Ⅳ概率掉落。</div>
</div>
</div>
</div>
```

获取途径整理按下列格式保存：
- 副本（如：`（5星）：祝圣秘境：月童的库藏 Ⅲ至Ⅳ概率掉落。`将按以下格式保存）
  - 副本类型：祝圣秘境
  - 副本名称：月童的库藏
  - 副本等级：Ⅲ、Ⅳ
- NPC
  - NPC姓名
  - 获取方式
- 探索奖励
- 精英怪物
- BOSS

### 圣遗物故事（lore）

每件圣遗物都有独立的 lore 文本，位于 `<div class="relic">` 区域中的 `<div class="resp-tabs-container">`：

```html
<div class="relic">
<div class="resp-tabs">
<div class="resp-tabs-list">
<div class="bili-list-style">
<div class="icon">
<div class="autoimg"><img alt="晨星与月的晓歌生之花.png"...></div>
<div class="main"><div class="up">献与月的华梦</div><div class="down">生之花</div></div>
</div>
</div>
<!-- 4 more pieces... -->
</div>
<div class="intext">
<div class="title">圣遗物故事</div>
<div class="resp-tabs-container">
<div class="resp-tab-content" style="display: none;">
<div class="story">曾经有一个时代，牵引着原初天球的银轮，其数量依旧为三。<br>
<p>那时，高天所降下的律法尚未结集，人理的边界尚未划定。<br>
...
</p>
</div><br><br>
<div class="item">古时为空月女神塑像的工匠，为彰显神明华美的容姿而精心雕琢的花饰。</div>
</div>
<!-- 4 more resp-tab-content for other pieces... -->
</div>
</div>
</div>
```

每个 `<div class="resp-tab-content">` 包含：
- `<div class="story">` - 主要 lore 文本（`<br />` 和 `<p>` 标签需换行处理）
- `<div class="item">` - 圣遗物道具描述

**换行规则**：
- 单个 `<br />` → `\n`
- 连续 `<br /><br />` → `\n\n`
- `<p>` 标签前后的换行处理方式与 `<br />` 类似

**注意**：不同部件的故事分别保存在不同部件的信息之下

---

## 存储位置

获取到的圣遗物信息保存到 `storage/artifacts/` 文件夹下

## 圣遗物爬取方案

计划的方案迭代储存在 `doc\plan` 文件夹下，当前暂无方案版本