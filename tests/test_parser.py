"""
WikiTextParser 单元测试
=======================

测试 WikiTextParser 解析器的各项功能：
- 通用页面解析（标题、分类、章节、摘要、模板）
- 角色页面解析（属性、天赋、命座）
- 异常处理（无效 payload）

测试数据
--------
SAMPLE_WIKITEXT 包含：
- 角色属性模板
- 多个天赋模板
- 命座模板
- 章节（角色故事）
- 中英文分类链接
"""

from __future__ import annotations

import unittest

from get_genshin_wiki.exceptions import ParsingError
from get_genshin_wiki.parser import WikiTextParser
from tests.helpers import build_page_payload

# 测试用角色 wikitext，覆盖角色信息、故事、切换板和语音等复杂模式
SAMPLE_WIKITEXT = """{{角色资料
|名字=哥伦比娅
|称号=空月归乡
|全名=哥伦比娅·希珀塞莱尼娅
|所属=挪德卡莱
|出身=
|种族=月神
|介绍=于挪德卡莱诞生的{{注音|「月之少女」|月之少女}}。<br>亦是归乡的空月。
|神之眼描述=三相月临
|元素=水
|武器=法器
|命之座=御月鸽座
|特殊料理=皎月渺渺
|性别=女
|羁绊属性=月兆
|昵称/外号=少女、{{注音|「月之少女」|月之少女}}、{{黑幕|库塔尔（十字路的主人）}}、{{黑幕|<del>秘密身份</del>}}、小鸽子
|衣装名称=月纱
|归属=霜月、{{黑幕|<del>愚人众</del>}}
|职业={{黑幕|<del>愚人众十一执行官 第三席</del>}}
}}
哥伦比娅是愚人众执行官之一。

{{角色天赋|名称=低语之歌|描述=造成水元素伤害|类别=普通攻击|元素=水}}
{{角色天赋|名称=终章和声|描述=提升队伍伤害|类别=元素爆发|元素=水}}
{{命之座|名称=白羽之冕|效果=提高元素爆发等级|描述=星光照向归乡之路}}
{{角色/故事
|角色详细=白天还是夜晚？<br>那当然是夜晚。
|角色故事1=最先听到的是歌声。<br><br>♪睡吧，睡吧，我的小鸽子♪
|角色故事2=回忆像月光一样漫长。
|冒险笔记名称=月光织就的眼罩
|冒险笔记内容=对哥伦比娅来说，世界的「真实」只有在闭起眼睛时才能看到。<br>她相信梦境会说真话。
|其他=三相月临
|其他故事=在获得「三月的权能」之后，她开始思考自己该如何使用它。
|结尾=终
}}
{{角色展示
|壹·人物={{切换板|显示内容}}月下白鸽，何以为家？<br><br>冬夜不会仁慈。{{切换板|内容结束}}{{切换板|折叠内容}}她在霜雪中抛弃了帷巢。{{切换板|内容结束}}
|贰·故事={{切换板|默认显示|她的过去}}{{切换板|显示内容}}[[file:角色哥伦比娅官方故事图3.jpg|thumb|240px|哥伦比娅官方故事图]]<br>过去像潮汐一样回响。{{切换板|内容结束}}{{切换板|默认折叠|她的回忆}}{{切换板|折叠内容}}回忆总在月下浮现。{{切换板|内容结束}}
}}

==角色故事==
她来自至冬。<br><br>她听见了月光。

[[Category:角色]]
[[分类:至冬]]
"""

VOICE_PAGE_WIKITEXT = """{{面包屑|哥伦比娅|角色语音}}{{角色导航}}{{语音tab样式}}
<div class="resp-tabs-container">
<div class="resp-tab-content" style="display:block;">
{{角色/语音1|语音类型=闲聊·歌|语音内容=我的歌并不为谁而唱。<br>但如果有人驻足。|语音内容日语=歌は誰のためでもない。}}
{{角色/语音|语音类型=下雨的时候|语音内容=雨幕之后，月亮会更亮。|语音内容英语=The moon shines brighter after the rain.}}
</div>
<div class="resp-tab-content" style="display:none;">
{{角色/语音|语音类型=无效示例|语音内容日语=無視する}}
</div>
</div>
"""

REALISTIC_SECTION_WIKITEXT = """{{角色
|名称=哥伦比娅
|介绍=于挪德卡莱诞生的「月之少女」。
|元素属性=水
|武器类型=法器
}}
{{角色/故事
|角色详细=白天还是夜晚？<br>那当然是夜晚。
|角色故事1=最先听到的是歌声。
|角色故事1解锁条件=好感2级
}}
==角色相关==
===官方介绍===
====壹·人物====
{{切换板|开始}}
{{切换板|默认显示|角色介绍1}}
{{切换板|默认折叠|角色介绍2}}
{{切换板|显示内容}}月下白鸽，何以为家？<br><br>冬夜不会仁慈。{{切换板|内容结束}}
{{切换板|折叠内容}}她在霜雪中抛弃了帷巢。{{切换板|内容结束}}
{{切换板|结束}}
====贰·故事====
{{切换板|开始}}
{{切换板|默认显示|她的过去}}
{{切换板|默认折叠|她的回忆}}
{{切换板|显示内容}}过去像潮汐一样回响。{{切换板|内容结束}}
{{切换板|折叠内容}}回忆总在月下浮现。{{切换板|内容结束}}
{{切换板|结束}}
"""

DIRECT_SECTION_WIKITEXT = """{{角色
|名称=温迪
|介绍=如风般自由的吟游诗人。
|元素属性=风
|武器类型=弓
}}
==角色相关==
===官方介绍===
====壹·人物====
如风般自由的吟游诗人，驻于牧歌之城。<br>
====贰·故事====
来路不明的吟游诗人。<br>像风一般捉摸不透。
"""


VOICE_PAGE_WIKITEXT = """{{面包屑|哥伦比娅|角色语音}}{{角色导航}}{{语音tab样式}}
<div class="resp-tabs-container">
<div class="resp-tab-content" style="display:block;">
{{角色/语音1|语音类型=闲聊·歌|语音内容=我的歌并不为谁而唱。<br>但如果有人驻足。|语音内容日语=歌は誰のためでもない。}}
{{角色/语音|语音类型=下雨的时候|语音内容=雨幕之后，月亮会更亮。|语音内容英语=The moon shines brighter after the rain.}}
</div>
<div class="resp-tab-content" style="display:none;">
{{角色/语音|语音类型=无效示例|语音内容日语=無視する}}
</div>
</div>
"""

REALISTIC_SECTION_WIKITEXT = """{{角色
|名称=哥伦比娅
|介绍=于挪德卡莱诞生的「月之少女」。
|元素属性=水
|武器类型=法器
}}
{{角色/故事
|角色详细=白天还是夜晚？<br>那当然是夜晚。
|角色故事1=最先听到的是歌声。
|角色故事1解锁条件=好感2级
}}
==角色相关==
===官方介绍===
====壹·人物====
{{切换板|开始}}
{{切换板|默认显示|角色介绍1}}
{{切换板|默认折叠|角色介绍2}}
{{切换板|显示内容}}月下白鸽，何以为家？<br><br>冬夜不会仁慈。{{切换板|内容结束}}
{{切换板|折叠内容}}她在霜雪中抛弃了帷巢。{{切换板|内容结束}}
{{切换板|结束}}
====贰·故事====
{{切换板|开始}}
{{切换板|默认显示|她的过去}}
{{切换板|默认折叠|她的回忆}}
{{切换板|显示内容}}过去像潮汐一样回响。{{切换板|内容结束}}
{{切换板|折叠内容}}回忆总在月下浮现。{{切换板|内容结束}}
{{切换板|结束}}
"""

DIRECT_SECTION_WIKITEXT = """{{角色
|名称=温迪
|介绍=如风般自由的吟游诗人。
|元素属性=风
|武器类型=弓
}}
==角色相关==
===官方介绍===
====壹·人物====
如风般自由的吟游诗人，驻于牧歌之城。<br>
====贰·故事====
来路不明的吟游诗人。<br>像风一般捉摸不透。
"""

# 测试用书籍 wikitext - 使用实际的模板格式
SAMPLE_BOOK_WIKITEXT = """{{书籍|名称=白夜国馆藏|体裁=史书|国家=稻妻}}
白夜国馆藏是一部记录稻妻历史的书籍。

{{书籍|卷1名=常世国龙蛇传|卷1获取地点=稻妻城「八重堂」编辑黑田购买获得|卷1描述=取材自海祇岛民间故事的小说|卷1内容=造化藏奥妙，日月行吉凶。}}
{{书籍|卷2名=鬼人正传|卷2获取地点=完成「鸣海渚祭」活动获得|卷2描述=讲述了珊瑚宫一段不为人知的历史|卷2内容=第一章内容...}}
"""

SAMPLE_ARCHON_LIST_WIKITEXT = """== 序章：捕风的异乡人 ==
=== 第一幕：捕风的异乡人 ===
* [[鸟瞰风物]]
* [[异常的权柄]]

== 第四章：白露与黑潮的序诗 ==
=== 第六幕：你存在的时空 ===
* [[如月长存]]
"""

SAMPLE_ARCHON_WIKITEXT = """{{任务
|任务名称=鸟瞰风物
|任务描述=从坠星山谷启程，你和派蒙走走看看，一路前行。
|系列任务=捕风的异乡人
|前置任务=流浪者的足迹
|后续任务=异常的权柄
|任务流程=* 前往低语森林
* 寻找安柏
|出场人物=安柏、派蒙
}}
== 任务剧情 ==
安柏：前面的区域，之后再来探索吧。
旅行者：好，我们继续前进。
选项：我们出发吧。
风带来了远方的种子。
派蒙：嘿嘿，冒险才刚开始呢！
"""

SAMPLE_ARCHON_ICON_LIST_WIKITEXT = """== [[序章]] 捕风的异乡人 ==
'''本部分会依次解锁并接取'''
{{图标|任务|蒙德|1|序章 第一幕|捕风的异乡人}}
{{图标|任务|蒙德|2|序章 第二幕|为了没有眼泪的明天}}
{{图标|任务|蒙德|3|序章 第三幕|巨龙与自由之歌}}

== [[第一章]] 辞行久远之躯 ==
'''前3幕任务分别在23级、25级、28级解锁，第四幕在完成世界任务[[迫近的客星]]后解锁'''
{{图标|任务|璃月|1|第一章 第一幕|浮世浮生千岩间}}
{{图标|任务|璃月|2|第一章 第二幕|辞行久远之躯}}
{{图标|任务|璃月|3|第一章 第三幕|迫近的客星}}
'''[[拾枝者·戴因斯雷布]]'''
{{图标|任务|蒙德|4|第一章 第四幕|我们终将重逢}}
"""

SAMPLE_ARCHON_TEMPLATE_OPTION_WIKITEXT = """{{任务
|任务名称=鸟瞰风物
|任务名称英文=Bird's Eye View
|任务描述=从坠星山谷启程，你和派蒙走走看看，一路前行。
|系列任务=捕风的异乡人
|前置任务=完成魔神任务 序章·第一幕「[[流浪者的足迹]]」
|并行任务=序章·第一幕「[[林间相会]]」
|后续任务=序章·第一幕「[[异常的权柄]]」
|任务流程=* 前往低语森林
* 寻找安柏
|出场人物=安柏、派蒙
}}
== 任务剧情 ==
安柏：前面的区域，之后再来探索吧。
旅行者：好，我们继续前进。
{{选项|选项1=我们出发吧。|选择1=*风带来了远方的种子。|选项2=再等等。}}
派蒙：啊哦，冒险才刚开始呢！
"""

SAMPLE_ARCHON_MOON_SONG_LIST_WIKITEXT = """== [[第五章]] 炽烈的还魂诗 ==
{{图标|任务|纳塔|6|第五章 第六幕|你存在的时空}}
== [[空月之歌]] ==
{{图标|任务|挪德卡莱|1|空月之歌 序奏|归途}}
{{图标|任务|挪德卡莱|2|空月之歌 第一幕|雪浪与苍林之舞}}
"""

SAMPLE_ARCHON_MOON_SONG_QUEST_WIKITEXT = """{{任务
|任务名称=月亮升起的地方
|任务描述=月光铺就前路。
|任务地区=挪德卡莱
|任务条件=完成魔神任务：空月之歌·序奏「[[归途]]」
|系列任务=空月之歌,雪浪与苍林之舞
|前置任务=*[[归途]]
|任务流程=*踏上新的旅程
}}
==任务剧情==
===踏上新的旅程===
*派蒙：那我们就出发吧。
{{剧情选项
|选项1=走吧。
|剧情1=*旅行者：嗯。
}}
"""

SAMPLE_NORTH_LIBRARY_WIKITEXT = """北陆图书馆导言<br>第二行

=<center>提瓦特</center>=
一级正文
==[[提瓦特编年史]]==
二级正文
===穿越星海===
三级正文
====史莱姆====
四级正文
<big>'''时间'''</big>
项目正文<br>第二行
*普通条目
*'''周期'''
条目正文
<big>'''{{颜色|火1|火}}'''</big>
颜色项目正文

[[Category:北陆图书馆]]
"""

SPECIALIZED_PAGE_CASES = [
    {
        "title": "花果草糖",
        "method": "parse_food_page",
        "wikitext": """{{食物
|类型=正常料理
|介绍=挪德卡莱的糖果。<br>选用挪德卡莱本土的花花草草与浆果为原料。
|完美介绍=挪德卡莱的糖果。舌尖接触到晶莹的糖果。
|失败介绍=挪德卡莱的糖果。尝起来又咸又涩。
|所需食材=宿影花*2<br>冬凌草*2<br>夏槲果*2<br>白灵果*2
|特殊料理角色=[[哥伦比娅]]
}}
==食谱信息==
食谱获取方式 挪德卡莱·那夏镇[[卡嘉|「斯佩兰扎」]]购买
==特殊料理==
皎月渺渺
特殊料理角色 哥伦比娅
""",
        "assertions": {
            "名称": "花果草糖",
            "类型": "正常料理",
            "介绍": {
                "普通料理": "挪德卡莱的糖果。\n选用挪德卡莱本土的花花草草与浆果为原料。",
                "完美料理": "挪德卡莱的糖果。舌尖接触到晶莹的糖果。",
                "失败料理": "挪德卡莱的糖果。尝起来又咸又涩。",
            },
            "所需食材": "宿影花*2\n冬凌草*2\n夏槲果*2\n白灵果*2",
            "食谱获取方式": "挪德卡莱·那夏镇「斯佩兰扎」购买",
            "特殊料理": "皎月渺渺",
            "特殊料理角色": "哥伦比娅",
        },
    },
    {
        "title": "无奇巨斧鱼",
        "method": "parse_wildlife_page",
        "wikitext": """{{野生生物
|类型=游鱼
|种类=巨斧鱼类
|描述=形貌独特的鱼类。<br>与斧枪鱼有着一定的亲缘关系。
|出现地点=挪德卡莱
|能否捕捉=不能
|钓鱼鱼饵=飞蝇假饵
|钓鱼时间=全天
|钓鱼地点=挪德卡莱
}}""",
        "assertions": {
            "名称": "无奇巨斧鱼",
            "类型": "游鱼",
            "种类": "巨斧鱼类",
            "描述": "形貌独特的鱼类。\n与斧枪鱼有着一定的亲缘关系。",
            "出现地点": "挪德卡莱",
            "能否捕捉": "不能",
            "钓鱼信息": {
                "钓鱼鱼饵": "飞蝇假饵",
                "钓鱼时间": "全天",
                "钓鱼地点": "挪德卡莱",
            },
        },
    },
    {
        "title": "装有信件的漂流瓶",
        "method": "parse_quest_item_page",
        "wikitext": """{{任务道具
|类型=书籍
|描述=无意中钓上来的漂流瓶。瓶口的塞子已经出现了破损。
|相关任务=[[潮汐之忆]]
|获取方式=「月中王国」活动稻妻钓鱼获得
}}
==内容==
爹咧！娘咧！孩儿不孝！
孩儿真是猪油蒙了心。
""",
        "assertions": {
            "名称": "装有信件的漂流瓶",
            "类型": "书籍",
            "描述": "无意中钓上来的漂流瓶。瓶口的塞子已经出现了破损。",
            "相关任务": "潮汐之忆",
            "获取方式": "「月中王国」活动稻妻钓鱼获得",
            "内容": "爹咧！娘咧！孩儿不孝！\n孩儿真是猪油蒙了心。",
        },
    },
    {
        "title": "奇特的「留影机」",
        "method": "parse_item_page",
        "wikitext": """{{道具
|类型=小道具
|来源=[[「福至五彩」]]活动获得
|用途=[[「福至五彩」]]活动期间拍摄特定照片兑换礼盒。
|介绍=在[[「福至五彩」]]活动期间使用时，能储存当前具有特定色彩的事物的影像。<br>季同从枫丹引进的新式留影机。
}}""",
        "assertions": {
            "名称": "奇特的「留影机」",
            "类型": "小道具",
            "来源": "「福至五彩」活动获得",
            "用途": "「福至五彩」活动期间拍摄特定照片兑换礼盒。",
            "介绍": "在「福至五彩」活动期间使用时，能储存当前具有特定色彩的事物的影像。\n季同从枫丹引进的新式留影机。",
        },
    },
    {
        "title": "混沌枢纽",
        "method": "parse_material_page",
        "wikitext": """{{材料
|类型=武器培养素材
|来源=精英怪物掉落<br>40级以上遗迹机兵掉落
|介绍=来自不再活动的古代遗迹机关。<br>在无法维持机关构装体的结局之后留下。
|用途=武器突破<br>炼金合成
}}""",
        "assertions": {
            "名称": "混沌枢纽",
            "类型": "武器培养素材",
            "来源": "精英怪物掉落\n40级以上遗迹机兵掉落",
            "介绍": "来自不再活动的古代遗迹机关。\n在无法维持机关构装体的结局之后留下。",
            "用途": "武器突破\n炼金合成",
        },
    },
    {
        "title": "蒙德·望楼",
        "method": "parse_namecard_page",
        "wikitext": """{{名片
|获取方式=达成「[[魔山风息]]」下所有成就时获取。
|描述=在被塞了一些奇奇怪怪的东西后，「切片辖域·陶」更加不像是个保存库了。
}}""",
        "assertions": {
            "名称": "蒙德·望楼",
            "获取方式": "达成「魔山风息」下所有成就时获取。",
            "描述": "在被塞了一些奇奇怪怪的东西后，「切片辖域·陶」更加不像是个保存库了。",
        },
    },
    {
        "title": "月童的库藏",
        "method": "parse_secret_item_page",
        "wikitext": """{{秘境
|秘境类型=圣遗物秘境
|秘境介绍=那是早已被月下的凡人们所遗忘的遥远世代。<br>终北的子嗣们曾在此筑起高塔。
|难度4掉落=冒险阅历<br>[[风起之日]]<br>[[晨星与月的晓歌]]
}}""",
        "assertions": {
            "名称": "月童的库藏",
            "类型": "圣遗物秘境",
            "介绍": "那是早已被月下的凡人们所遗忘的遥远世代。\n终北的子嗣们曾在此筑起高塔。",
            "掉落": {"圣遗物1": "风起之日", "圣遗物2": "晨星与月的晓歌"},
        },
    },
]

SPECIALIZED_REQUIRED_KEYS = {
    "parse_food_page": {
        "top_level": {"名称", "类型", "介绍", "所需食材", "食谱获取方式", "特殊料理", "特殊料理角色"},
        "nested": {"介绍": {"普通料理", "完美料理", "失败料理"}},
    },
    "parse_wildlife_page": {
        "top_level": {"名称", "类型", "种类", "描述", "出现地点", "能否捕捉", "钓鱼信息"},
        "nested": {"钓鱼信息": {"钓鱼鱼饵", "钓鱼时间", "钓鱼地点"}},
    },
    "parse_quest_item_page": {
        "top_level": {"名称", "类型", "描述", "相关任务", "获取方式", "内容"},
        "nested": {},
    },
    "parse_item_page": {
        "top_level": {"名称", "类型", "来源", "用途", "介绍"},
        "nested": {},
    },
    "parse_material_page": {
        "top_level": {"名称", "类型", "来源", "介绍", "用途"},
        "nested": {},
    },
    "parse_namecard_page": {
        "top_level": {"名称", "获取方式", "描述"},
        "nested": {},
    },
    "parse_secret_item_page": {
        "top_level": {"名称", "类型", "介绍", "掉落"},
        "nested": {"掉落": {"圣遗物1", "圣遗物2"}},
    },
}



class WikiTextParserTests(unittest.TestCase):
    """WikiTextParser 单元测试类。"""

    def setUp(self) -> None:
        """创建解析器实例和测试 payload。"""
        self.parser = WikiTextParser()
        self.payload = build_page_payload("哥伦比娅", SAMPLE_WIKITEXT, page_id=7)
        self.voice_payload = build_page_payload("哥伦比娅语音", VOICE_PAGE_WIKITEXT, page_id=17)

    def test_parse_page_extracts_templates_categories_sections_and_summary(self) -> None:
        """
        测试 parse_page 正确提取页面的各个组成部分。
        """
        result = self.parser.parse_page(self.payload)

        self.assertEqual("哥伦比娅", result.title)
        self.assertEqual(7, result.page_id)
        # 中英文分类链接应合并去重并排序
        self.assertEqual(["至冬", "角色"], result.categories)
        self.assertIn("哥伦比娅是愚人众执行官之一。", result.summary)
        self.assertIn("角色资料", result.templates)
        # 验证章节分割
        self.assertEqual("角色故事", result.sections[1].title)
        self.assertEqual("她来自至冬。\n\n她听见了月光。", result.sections[1].text)

    def test_parse_character_page_extracts_deep_character_fields(self) -> None:
        """
        测试 parse_character_page 正确提取角色特有字段。
        """
        result = self.parser.parse_character_page(self.payload, voice_payload=self.voice_payload)

        # 属性从角色属性模板提取
        self.assertEqual("水", result.attributes["元素"])
        self.assertEqual("法器", result.attributes["武器"])
        self.assertEqual(["空月归乡"], result.titles)
        self.assertEqual("哥伦比娅·希珀塞莱尼娅", result.full_name)
        self.assertEqual("挪德卡莱", result.homeland)
        self.assertEqual("月神", result.race)
        self.assertEqual("于挪德卡莱诞生的月之少女。\n亦是归乡的空月。", result.introduction)
        self.assertEqual("三相月临", result.god_eye_description)
        self.assertEqual("水", result.element)
        self.assertEqual("法器", result.weapon_type)
        self.assertEqual("御月鸽座", result.constellation)
        self.assertEqual("皎月渺渺", result.special_dish)
        self.assertEqual("女", result.gender)
        self.assertEqual("月兆", result.bond_attribute)
        self.assertEqual(["少女", "月之少女", "十字路的主人", "小鸽子"], result.nicknames)
        self.assertEqual(["月纱"], result.outfits)
        self.assertEqual(["霜月", "愚人众"], result.affiliation)
        self.assertEqual("愚人众十一执行官 第三席", result.profession)

        # 天赋：两个角色天赋模板
        self.assertEqual(2, len(result.talents))
        self.assertEqual("普通攻击", result.talent_records[0].category)
        self.assertEqual("水", result.talent_records[0].element)

        # 命座：一个命之座模板
        self.assertEqual(1, len(result.constellations))
        self.assertEqual("白羽之冕", result.constellations[0]["名称"])
        self.assertEqual("提高元素爆发等级", result.constellation_records[0].effect)

        # 角色故事与相关扩展内容
        self.assertEqual(["角色详细", "角色故事1", "角色故事2"], [item.title for item in result.story_records])
        self.assertEqual("白天还是夜晚？\n那当然是夜晚。", result.story_records[0].content)
        self.assertEqual(
            "最先听到的是歌声。\n\n♪睡吧，睡吧，我的小鸽子♪",
            result.story_records[1].content,
        )
        self.assertEqual(1, len(result.adventure_notes))
        self.assertEqual("月光织就的眼罩", result.adventure_notes[0].title)
        self.assertIn("世界的「真实」只有在闭起眼睛时才能看到。", result.adventure_notes[0].content)
        self.assertEqual("三相月临", result.power_record.title)
        self.assertIn("她开始思考自己该如何使用它。", result.god_eye_story)

        # 切换板内容
        self.assertEqual(["角色介绍1", "角色介绍2"], [item.title for item in result.character_introductions])
        self.assertEqual("月下白鸽，何以为家？\n\n冬夜不会仁慈。", result.character_introductions[0].content)
        self.assertEqual(["她的过去", "她的回忆"], [item.title for item in result.story_sections])
        self.assertEqual("过去像潮汐一样回响。", result.story_sections[0].content)
        self.assertNotIn("哥伦比娅官方故事图", result.story_sections[0].content)

        # 角色语音从独立语音页提取，只取 display:block 且只取中文语音内容
        self.assertEqual(["闲聊·歌", "下雨的时候"], [item.title for item in result.voice_records])
        self.assertEqual("我的歌并不为谁而唱。\n但如果有人驻足。", result.voice_records[0].content)
        self.assertNotIn("歌は誰のためでもない。", result.voice_records[0].content)

        stored = result.to_storage_dict()
        self.assertEqual(
            ["角色", "角色故事", "冒险笔记", "权能", "壹·人物", "贰·故事", "角色语音"],
            list(stored.keys()),
        )
        self.assertEqual("哥伦比娅", stored["角色"]["名称"])
        self.assertEqual("挪德卡莱", stored["角色"]["所属"])
        self.assertEqual("霜月、愚人众", stored["角色"]["归属"])
        self.assertEqual("少女、月之少女、十字路的主人、小鸽子", stored["角色"]["昵称/外号"])
        self.assertEqual("白天还是夜晚？\n那当然是夜晚。", stored["角色故事"]["角色详细"])
        self.assertEqual("在获得「三月的权能」之后，她开始思考自己该如何使用它。", stored["权能"]["三相月临"])
        self.assertEqual("过去像潮汐一样回响。", stored["贰·故事"]["她的过去"])
        self.assertEqual("我的歌并不为谁而唱。\n但如果有人驻足。", stored["角色语音"]["闲聊·歌"])
        self.assertNotIn("title", stored)

    def test_parse_character_story_page_returns_story_focused_payload(self) -> None:
        """
        测试 parse_character_story_page 返回故事聚合结果。
        """
        result = self.parser.parse_character_story_page(self.payload, voice_payload=self.voice_payload)

        self.assertEqual("哥伦比娅", result["title"])
        self.assertEqual(3, len(result["story_records"]))
        self.assertEqual("月光织就的眼罩", result["adventure_notes"][0]["title"])
        self.assertEqual("她的过去", result["story_sections"][0]["title"])
        self.assertEqual("闲聊·歌", result["voice_records"][0]["title"])

    def test_parse_character_voice_page_extracts_records_from_voice_page(self) -> None:
        """
        测试 parse_character_voice_page 从 name语音 页面提取 display:block 中文语音。
        """
        result = self.parser.parse_character_voice_page(self.voice_payload)

        self.assertEqual(["闲聊·歌", "下雨的时候"], [item.title for item in result])
        self.assertEqual("我的歌并不为谁而唱。\n但如果有人驻足。", result[0].content)

    def test_parse_character_page_extracts_sections_and_categories_from_realistic_wikitext(self) -> None:
        """
        测试真实页面结构下的章节切换板提取与 payload 分类回退。
        """
        payload = build_page_payload("哥伦比娅", REALISTIC_SECTION_WIKITEXT, page_id=8)
        page = next(iter(payload["query"]["pages"].values()))
        page["categories"] = [{"title": "Category:角色"}, {"title": "Category:至冬"}]

        page_result = self.parser.parse_page(payload)
        character_result = self.parser.parse_character_page(payload)

        self.assertEqual(["至冬", "角色"], page_result.categories)
        self.assertEqual(["角色介绍1", "角色介绍2"], [item.title for item in character_result.character_introductions])
        self.assertEqual(["她的过去", "她的回忆"], [item.title for item in character_result.story_sections])
        self.assertEqual(["角色详细", "角色故事1"], [item.title for item in character_result.story_records])

    def test_parse_character_page_extracts_direct_intro_and_story_sections(self) -> None:
        """
        测试无切换板时，直接从壹·人物和贰·故事正文提取内容。
        """
        payload = build_page_payload("温迪", DIRECT_SECTION_WIKITEXT, page_id=9)

        result = self.parser.parse_character_page(payload)

        self.assertEqual(["角色介绍1"], [item.title for item in result.character_introductions])
        self.assertEqual("如风般自由的吟游诗人，驻于牧歌之城。", result.character_introductions[0].content)
        self.assertEqual(["贰·故事"], [item.title for item in result.story_sections])
        self.assertEqual("来路不明的吟游诗人。\n像风一般捉摸不透。", result.story_sections[0].content)

    def test_parse_character_page_discards_empty_story_sections_after_file_cleanup(self) -> None:
        """
        测试贰·故事子项在去除 file 链接后若为空，会被丢弃。
        """
        payload = build_page_payload(
            "哥伦比娅",
            """{{角色|名称=哥伦比娅|元素=水|武器=法器}}
{{角色展示
|贰·故事={{切换板|默认显示|仅图片}}{{切换板|显示内容}}[[file:story.jpg|thumb|240px|说明]]{{切换板|内容结束}}{{切换板|默认折叠|保留}}{{切换板|折叠内容}}仍有正文{{切换板|内容结束}}
}}""",
            page_id=10,
        )

        result = self.parser.parse_character_page(payload)

        self.assertEqual(["保留"], [item.title for item in result.story_sections])
        self.assertEqual("仍有正文", result.story_sections[0].content)

    def test_parse_monster_page_extracts_monster_specific_fields(self) -> None:
        """
        测试 parse_monster_page 正确提取怪物特有字段。
        """
        monster_wikitext = """{{怪物信息|怪物类别=周刷BOSS|怪物分类=值得铭记的强敌|怪物类型=其他|出现地点=蒙德·风起地|掉落素材=BOSS|BOSS素材=升扬样本·骑士,升扬样本·战车,升扬样本·王族}}
集魔女会诸家技艺而制成的集团军。

== 介绍 ==
这是怪物的介绍内容。

[[Category:怪物]]
[[分类:BOSS]]
"""
        payload = build_page_payload("门扉前的弈局", monster_wikitext, page_id=10)
        result = self.parser.parse_monster_page(payload)

        self.assertEqual("门扉前的弈局", result.title)
        self.assertEqual("周刷BOSS", result.monster_class)
        self.assertEqual("值得铭记的强敌", result.monster_category)
        self.assertEqual("其他", result.monster_type)
        self.assertEqual("蒙德·风起地", result.location)
        self.assertIn("升扬样本·骑士", result.drop_materials)
        self.assertIn("升扬样本·战车", result.drop_materials)
        self.assertIn("升扬样本·王族", result.drop_materials)

    def test_parse_monster_page_with_elite_monster(self) -> None:
        """
        测试 parse_monster_page 解析精英怪物（掉落素材不是 BOSS 类型）。
        """
        elite_wikitext = """{{怪物属性|怪物类别=精英|怪物分类=自律机关|怪物类型=战争机械|出现地点=稻妻|掉落素材=混沌机关,混沌枢纽,混沌真眼}}
为了适应特殊的目标，有着定制化外形与机能的异形机械。

[[Category:怪物]]
"""
        payload = build_page_payload("遗迹防卫者", elite_wikitext, page_id=11)
        result = self.parser.parse_monster_page(payload)

        self.assertEqual("遗迹防卫者", result.title)
        self.assertEqual("精英", result.monster_class)
        self.assertEqual("自律机关", result.monster_category)
        self.assertEqual("战争机械", result.monster_type)
        self.assertEqual("稻妻", result.location)
        self.assertIn("混沌机关", result.drop_materials)
        self.assertIn("混沌枢纽", result.drop_materials)
        self.assertIn("混沌真眼", result.drop_materials)

    def test_parse_specialized_pages_extract_expected_fields(self) -> None:
        """测试 7 类物品页面的专用解析器。"""
        for index, case in enumerate(SPECIALIZED_PAGE_CASES, start=100):
            with self.subTest(method=case["method"], title=case["title"]):
                payload = build_page_payload(case["title"], case["wikitext"], page_id=index)
                result = getattr(self.parser, case["method"])(payload).to_dict()
                required = SPECIALIZED_REQUIRED_KEYS[case["method"]]

                self.assertEqual(case["title"], result["名称"])
                self.assertEqual(required["top_level"], set(result.keys()))
                for field_name, nested_keys in required["nested"].items():
                    self.assertEqual(nested_keys, set(result[field_name].keys()))
                for field, expected in case["assertions"].items():
                    self.assertEqual(expected, result[field])

    def test_parse_specialized_pages_handles_real_world_template_variants(self) -> None:
        """测试真实页面中出现的字段别名和复杂模板。"""
        wildlife_payload = build_page_payload(
            "生物志：白鸽",
            """{{野生生物图鉴
|名称=白鸽
|类型=禽鸟
|种类=鸽
|描述=提瓦特常见的鸟类。<br><br>洁白可爱的白鸽。
|出现地点=绝云间北面
|能否捕捉=能
}}""",
            page_id=201,
        )
        wildlife_result = self.parser.parse_wildlife_page(wildlife_payload).to_dict()
        self.assertEqual("白鸽", wildlife_result["名称"])

        quest_item_payload = build_page_payload(
            "装有信件的漂流瓶",
            """{{任务道具
|名称=装有信件的漂流瓶
|类型=书籍<!-- 注释 -->
|描述=无意中钓上来的漂流瓶。
|获取方式=「月中王国」活动稻妻钓鱼获得
|书籍内容=爹咧！娘咧！<br>孩儿不孝！
}}""",
            page_id=202,
        )
        quest_item_result = self.parser.parse_quest_item_page(quest_item_payload).to_dict()
        self.assertEqual("书籍", quest_item_result["类型"])
        self.assertEqual("爹咧！娘咧！\n孩儿不孝！", quest_item_result["内容"])

        quest_item_markup_payload = build_page_payload(
            "《欢迎来到那夏镇！》",
            """{{任务道具
|名称={{PAGENAME}}
|类型=书籍
|描述=导览图。
|获取方式=任务获得
|书籍内容=[[file:欢迎来到那夏镇-插图.png|center]]<br><center>欢迎来到那夏镇！</center><br><tabber>
1=
正文第一段。<br><br>
|-|
2=
正文第二段。
</tabber>
}}""",
            page_id=2021,
        )
        quest_item_markup_result = self.parser.parse_quest_item_page(quest_item_markup_payload).to_dict()
        self.assertEqual("欢迎来到那夏镇！\n\n正文第一段。\n\n正文第二段。", quest_item_markup_result["内容"])

        material_payload = build_page_payload(
            "混沌枢纽",
            """{{素材图鉴
|名称=混沌枢纽
|类型=武器培养素材
|来源='''精英怪物掉落'''、
40级以上遗迹机兵掉落、
（帮助：[https://www.bilibili.com/video/BV1fq4y1X7WL 位置视频]）
|用处={{图标|混沌真眼}}（炼金合成）、
{{#arraymap:{{#ask:[[分类:武器]][[需求材料::~*{{PAGENAME}}*]]|format=sep|sort=稀有度|order=desc|link=none}}|,|@|{{图标|@}}（50/60级突破）<br>|}}
|用途=武器突破（50/60级突破）、{{图标|混沌真眼}}（炼金合成）
|介绍=来自不再活动的古代遗迹机关。<br>在无法维持机关构装体的结构性之后，其中蕴含的伟大技术与未知力量也失去意义了吧。
}}""",
            page_id=203,
        )
        material_result = self.parser.parse_material_page(material_payload).to_dict()
        self.assertEqual("混沌枢纽", material_result["名称"])
        self.assertEqual("武器培养素材", material_result["类型"])
        self.assertIn("精英怪物掉落", material_result["来源"])
        self.assertIn("武器突破", material_result["用途"])
        self.assertIn("炼金合成", material_result["用途"])
        self.assertIn("来自不再活动的古代遗迹机关。", material_result["介绍"])

        secret_item_payload = build_page_payload(
            "月童的库藏",
            """{{秘境副本
|秘境名称=月童的库藏
|秘境类型=圣遗物秘境
|秘境介绍=那是早已被月下的凡人们所遗忘的遥远世代。
|难度4掉落={{图标|圣遗物|教官|4}}{{图标|圣遗物|奇迹|4}}{{图标|圣遗物|风起之日|5}}{{图标|圣遗物|晨星与月的晓歌|5}}
}}""",
            page_id=204,
        )
        secret_item_result = self.parser.parse_secret_item_page(secret_item_payload).to_dict()
        self.assertEqual(
            {"圣遗物1": "风起之日", "圣遗物2": "晨星与月的晓歌"},
            secret_item_result["掉落"],
        )

        artifact_domain_without_difficulty4_payload = build_page_payload(
            "华池岩岫",
            """{{秘境副本
|秘境名称=华池岩岫
|秘境类型=圣遗物秘境
|秘境介绍=奥藏山中的秘境仍在等待新的挑战者。
|难度3掉落={{图标|圣遗物|赌徒|3|3}}{{图标|圣遗物|学士|3|3}}{{图标|圣遗物|染血的骑士道|5}}{{图标|圣遗物|昔日宗室之仪|5}}
|难度4掉落=
}}""",
            page_id=2041,
        )
        artifact_domain_without_difficulty4_result = self.parser.parse_secret_item_page(
            artifact_domain_without_difficulty4_payload
        ).to_dict()
        self.assertEqual(
            {"圣遗物1": "染血的骑士道", "圣遗物2": "昔日宗室之仪"},
            artifact_domain_without_difficulty4_result["掉落"],
        )

        talent_domain_payload = build_page_payload(
            "昏识塔",
            """{{秘境副本
|秘境名称=昏识塔
|秘境类型=天赋技能材料秘境
|秘境介绍=在遥远的过去，地上各处都曾有人竖起几乎能触达天顶的高塔。
|难度4掉落=
{{星期|1}}{{图标|材料|「诤言」的教导}}{{图标|材料|「诤言」的指引}}{{图标|材料|「诤言」的哲学|}}<hr>
{{星期|2}}{{图标|材料|「巧思」的教导}}{{图标|材料|「巧思」的指引}}{{图标|材料|「巧思」的哲学|}}<hr>
{{星期|3}}{{图标|材料|「笃行」的教导}}{{图标|材料|「笃行」的指引}}{{图标|材料|「笃行」的哲学|}}
}}""",
            page_id=205,
        )
        talent_domain_result = self.parser.parse_secret_item_page(talent_domain_payload).to_dict()
        self.assertEqual(
            {
                "天赋技能材料1": "「诤言」的教导、「诤言」的指引、「诤言」的哲学",
                "天赋技能材料2": "「巧思」的教导、「巧思」的指引、「巧思」的哲学",
                "天赋技能材料3": "「笃行」的教导、「笃行」的指引、「笃行」的哲学",
            },
            talent_domain_result["掉落"],
        )

        boss_domain_payload = build_page_payload(
            "待解「弈局」",
            """{{秘境副本
|秘境名称=待解「弈局」
|秘境类型=BOSS秘境
|秘境介绍=古老的棋局仍在等待最后一次落子。
|难度4掉落={{图标|材料|升扬样本·骑士}}{{图标|材料|升扬样本·战车}}{{图标|材料|升扬样本·王族}}{{图标|材料|燃愿玛瑙碎屑}}{{图标|圣遗物|战狂|4}}
}}""",
            page_id=206,
        )
        boss_domain_result = self.parser.parse_secret_item_page(boss_domain_payload).to_dict()
        self.assertEqual(
            {
                "材料1": "升扬样本·骑士",
                "材料2": "升扬样本·战车",
                "材料3": "升扬样本·王族",
            },
            boss_domain_result["掉落"],
        )

    def test_parse_archon_quest_list_page_extracts_chapter_act_hierarchy(self) -> None:
        """测试魔神任务列表页可提取章幕与任务顺序。"""
        payload = build_page_payload("魔神任务", SAMPLE_ARCHON_ICON_LIST_WIKITEXT, page_id=300)

        entries = self.parser.parse_archon_quest_list_page(payload)
        context = self.parser.build_archon_series_context(entries)

        self.assertEqual(
            [
                "捕风的异乡人",
                "为了没有眼泪的明天",
                "巨龙与自由之歌",
                "浮世浮生千岩间",
                "辞行久远之躯",
                "迫近的客星",
                "拾枝者·戴因斯雷布",
                "我们终将重逢",
            ],
            [entry["title"] for entry in entries],
        )
        self.assertEqual("序章", entries[0]["chapter"])
        self.assertEqual("捕风的异乡人", entries[0]["chapter_name"])
        self.assertEqual("第一幕", entries[0]["act"])
        self.assertEqual("第一章", entries[3]["chapter"])
        self.assertEqual("第三幕", entries[5]["act"])
        self.assertEqual("", entries[6]["act"])
        self.assertEqual(("序章", "第一幕", "捕风的异乡人", ""), context["捕风的异乡人"])
        self.assertEqual(("第一章", "第三幕", "辞行久远之躯", ""), context["迫近的客星"])
        self.assertEqual(("第一章", "第四幕", "辞行久远之躯", ""), context["我们终将重逢"])

    def test_parse_archon_quest_page_extracts_dialogues_and_series_context(self) -> None:
        """测试魔神任务页面解析会整合对话与章幕上下文。"""
        payload = build_page_payload("鸟瞰风物", SAMPLE_ARCHON_TEMPLATE_OPTION_WIKITEXT, page_id=301)
        series_context = {"捕风的异乡人": ("序章", "第一幕")}

        result = self.parser.parse_archon_quest_page(payload, series_context=series_context)
        serialized = result.to_dict()

        self.assertEqual("鸟瞰风物", result.title)
        self.assertEqual("Bird's Eye View", result.english_title)
        self.assertEqual("序章", result.chapter)
        self.assertEqual("第一幕", result.act)
        self.assertEqual("从坠星山谷启程，你和派蒙走走看看，一路前行。", result.description)
        self.assertEqual(["前往低语森林", "寻找安柏"], result.objectives)
        self.assertEqual("流浪者的足迹", result.prerequisites[0].title)
        self.assertEqual("序章", result.prerequisites[0].chapter)
        self.assertEqual("第一幕", result.prerequisites[0].act)
        self.assertEqual("林间相会", result.parallel_quests[0].title)
        self.assertEqual("异常的权柄", result.follow_up_quests[0].title)
        self.assertEqual(["安柏", "派蒙"], result.related_npcs)
        self.assertEqual(
            ["character", "traveler", "option", "narration", "option", "character"],
            [dialogue.dialogue_type for dialogue in result.dialogues],
        )
        self.assertEqual("安柏", result.dialogues[0].speaker)
        self.assertEqual("我们出发吧。", result.dialogues[2].text)
        self.assertEqual("风带来了远方的种子。", result.dialogues[3].text)
        self.assertEqual("再等等。", result.dialogues[4].text)
        self.assertTrue(all(dialogue.task_flow == "" for dialogue in result.dialogues))
        self.assertEqual(["前往低语森林", "寻找安柏"], serialized["任务流程"])
        self.assertEqual("", serialized["对话"][0]["所属任务流程"])

    def test_parse_archon_quest_list_page_handles_kongyuezhige_without_chapter_number(self) -> None:
        """测试空月之歌不会沿用第五章上下文。"""
        payload = build_page_payload("魔神任务", SAMPLE_ARCHON_MOON_SONG_LIST_WIKITEXT, page_id=302)

        entries = self.parser.parse_archon_quest_list_page(payload)
        context = self.parser.build_archon_series_context(entries)

        self.assertEqual(["你存在的时空", "归途", "雪浪与苍林之舞"], [entry["title"] for entry in entries])
        self.assertEqual("第五章", entries[0]["chapter"])
        self.assertEqual("空月之歌", entries[1]["chapter"])
        self.assertEqual("", entries[1]["chapter_name"])
        self.assertEqual("序奏", entries[1]["act"])
        self.assertEqual("空月之歌", entries[2]["chapter"])
        self.assertEqual("第一幕", entries[2]["act"])
        self.assertEqual(("空月之歌", "第一幕", "", ""), context["雪浪与苍林之舞"])

    def test_parse_archon_quest_page_extracts_nested_dialogues_names_and_renamed_roles(self) -> None:
        """测试嵌套任务剧情与剧情选项能被解析，并输出章节名称/幕名称/相关角色。"""
        payload = build_page_payload("月亮升起的地方", SAMPLE_ARCHON_MOON_SONG_QUEST_WIKITEXT, page_id=303)
        series_context = {
            "雪浪与苍林之舞": ("空月之歌", "第一幕", "", "雪浪与苍林之舞"),
            "归途": ("空月之歌", "序奏", "", "归途"),
        }

        result = self.parser.parse_archon_quest_page(payload, series_context=series_context)
        serialized = result.to_dict()

        self.assertEqual("空月之歌", result.chapter)
        self.assertEqual("", result.chapter_name)
        self.assertEqual("第一幕", result.act)
        self.assertEqual("雪浪与苍林之舞", result.act_name)
        self.assertEqual("空月之歌", result.prerequisites[0].chapter)
        self.assertEqual("序奏", result.prerequisites[0].act)
        self.assertEqual(["派蒙", "旅行者"], result.related_npcs)
        self.assertEqual(["character", "option", "traveler"], [dialogue.dialogue_type for dialogue in result.dialogues])
        self.assertEqual("走吧。", result.dialogues[1].text)
        self.assertEqual("嗯。", result.dialogues[2].text)
        self.assertEqual("踏上新的旅程", result.dialogues[0].task_flow)
        self.assertEqual("踏上新的旅程", result.dialogues[1].task_flow)
        self.assertEqual("", serialized["章节名称"])
        self.assertEqual("雪浪与苍林之舞", serialized["幕名称"])
        self.assertEqual(["派蒙", "旅行者"], serialized["相关角色"])
        self.assertEqual(["踏上新的旅程"], serialized["任务流程"])
        self.assertEqual("踏上新的旅程", serialized["对话"][0]["所属任务流程"])
        self.assertNotIn("相关NPC", serialized)

    def test_parse_north_library_page_builds_hierarchical_nodes(self) -> None:
        """测试北陆图书馆页面解析会保留标题层级、项目与条目结构。"""
        payload = build_page_payload("北陆图书馆", SAMPLE_NORTH_LIBRARY_WIKITEXT, page_id=301)

        result = self.parser.parse_north_library_page(payload)

        self.assertEqual("北陆图书馆", result.title)
        self.assertEqual("北陆图书馆导言\n第二行", result.summary)
        self.assertEqual(["北陆图书馆"], result.categories)
        self.assertEqual(1, len(result.nodes))

        first = result.nodes[0]
        second = first.children[0]
        third = second.children[0]
        fourth = third.children[0]
        item = fourth.children[0]
        titled_entry = item.children[1]
        color_item = fourth.children[1]

        self.assertEqual(("一级", "提瓦特", "一级正文"), (first.kind, first.title, first.text))
        self.assertEqual(("二级", "提瓦特编年史", "二级正文"), (second.kind, second.title, second.text))
        self.assertEqual(("三级", "穿越星海", "三级正文"), (third.kind, third.title, third.text))
        self.assertEqual(("四级", "史莱姆", "四级正文"), (fourth.kind, fourth.title, fourth.text))
        self.assertEqual(("项目", "时间", "项目正文\n第二行"), (item.kind, item.title, item.text))
        self.assertEqual(("条目", "", "普通条目"), (item.children[0].kind, item.children[0].title, item.children[0].text))
        self.assertEqual(("条目", "周期", "条目正文"), (titled_entry.kind, titled_entry.title, titled_entry.text))
        self.assertEqual(("项目", "火", "颜色项目正文"), (color_item.kind, color_item.title, color_item.text))

    def test_parse_north_library_page_falls_back_to_payload_categories(self) -> None:
        """测试北陆图书馆页面在无分类标记时会回退到 payload 分类。"""
        payload = build_page_payload("北陆图书馆", SAMPLE_NORTH_LIBRARY_WIKITEXT.replace("[[Category:北陆图书馆]]", ""), page_id=302)
        page = next(iter(payload["query"]["pages"].values()))
        page["categories"] = [{"title": "Category:需要帮助"}]

        result = self.parser.parse_north_library_page(payload)

        self.assertEqual(["需要帮助"], result.categories)

    def test_extract_page_metadata_raises_for_invalid_payload(self) -> None:
        """
        测试 extract_page_metadata 对无效 payload 抛出 ParsingError。
        """
        with self.assertRaises(ParsingError):
            self.parser.extract_page_metadata({"query": {"pages": {}}})

    def test_parse_weapon_page_extracts_weapon_fields(self) -> None:
        """
        测试 parse_weapon_page 正确提取武器特有字段。
        """
        SAMPLE_WEAPON_WIKITEXT = """{{武器属性|名字=霜结的誓金枝|类型=弓|介绍=由古老的白木打造而成的长弓|获取途径=[[限定祈愿]]|是否可锻造获取=否}}
{{武器突破|突破武器材料1=长夜燧火|突破高级材料1=焰剑|突破普通材料1=执凭}}
{{武器故事|故事=在遥古的岁月，曾有牧歌与繁花统治无忧的乡野。}}
[[Category:武器]]
"""
        payload = build_page_payload("霜结的誓金枝", SAMPLE_WEAPON_WIKITEXT, page_id=10)
        result = self.parser.parse_weapon_page(payload)

        self.assertEqual("霜结的誓金枝", result.title)
        self.assertEqual("弓", result.weapon_type)
        self.assertEqual("由古老的白木打造而成的长弓", result.description)
        self.assertEqual(["长夜燧火"], result.ascension_weapon_materials)
        self.assertEqual(["焰剑"], result.ascension_premium_materials)
        self.assertEqual(["执凭"], result.ascension_common_materials)
        self.assertEqual("限定祈愿", result.obtaining_method)

    def test_parse_artifact_set_page_extracts_artifact_fields(self) -> None:
        """
        测试 parse_artifact_set_page 正确提取圣遗物套装特有字段。
        """
        SAMPLE_ARTIFACT_WIKITEXT = """{{圣遗物属性|套装名称=风起之日|获取方式={{圣遗物套装/获取途径|BOSS|(四星)击杀首领或周本BOSS}}|生之花名称=风起之日|生之花描述=生之花描述文本|生之花故事=生之花故事文本|死之羽名称=风之羽|死之羽描述=死之羽描述文本}}
[[Category:圣遗物]]
"""
        payload = build_page_payload("风起之日", SAMPLE_ARTIFACT_WIKITEXT, page_id=20)
        result = self.parser.parse_artifact_set_page(payload)

        self.assertEqual("风起之日", result.title)
        self.assertEqual(5, len(result.pieces))
        # 生之花
        flower_piece = next(p for p in result.pieces if p.slot == "生之花")
        self.assertEqual("风起之日", flower_piece.name)
        self.assertEqual("生之花描述文本", flower_piece.description)
        self.assertEqual("生之花故事文本", flower_piece.story)

    def test_parse_book_page_extracts_book_fields(self) -> None:
        """
        测试 parse_book_page 正确提取书籍特有字段。
        """
        book_payload = build_page_payload("白夜国馆藏", SAMPLE_BOOK_WIKITEXT, page_id=8)
        result = self.parser.parse_book_page(book_payload)

        self.assertEqual("白夜国馆藏", result.title)
        self.assertEqual("史书", result.genre)
        self.assertEqual("稻妻", result.country)
        self.assertEqual(2, len(result.volumes))
        self.assertEqual("常世国龙蛇传", result.volumes[0].name)
        self.assertEqual("稻妻城「八重堂」编辑黑田购买获得", result.volumes[0].location)


if __name__ == "__main__":
    unittest.main()
