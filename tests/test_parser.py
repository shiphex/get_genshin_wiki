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
