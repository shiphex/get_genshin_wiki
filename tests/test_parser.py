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

# 测试用角色 wikitext，包含多种模板和分类格式
SAMPLE_WIKITEXT = """{{角色属性|名字=哥伦比娅|元素=冰|武器=法器}}
哥伦比娅是愚人众执行官之一。

{{角色天赋|名称=低语之歌|描述=造成冰元素伤害}}
{{角色天赋|名称=终章和声|描述=提升队伍伤害}}
{{命之座|名称=白羽之冕|效果=提高元素爆发等级}}

==角色故事==
她来自至冬。

[[Category:角色]]
[[分类:至冬]]
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
        self.assertIn("角色属性", result.templates)
        # 验证章节分割
        self.assertEqual("角色故事", result.sections[1].title)
        self.assertEqual("她来自至冬。", result.sections[1].text)

    def test_parse_character_page_extracts_character_specific_fields(self) -> None:
        """
        测试 parse_character_page 正确提取角色特有字段。
        """
        result = self.parser.parse_character_page(self.payload)

        # 属性从角色属性模板提取
        self.assertEqual("冰", result.attributes["元素"])
        self.assertEqual("法器", result.attributes["武器"])
        # 天赋：两个角色天赋模板
        self.assertEqual(2, len(result.talents))
        # 命座：一个命之座模板
        self.assertEqual(1, len(result.constellations))
        self.assertEqual("白羽之冕", result.constellations[0]["名称"])

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


if __name__ == "__main__":
    unittest.main()
