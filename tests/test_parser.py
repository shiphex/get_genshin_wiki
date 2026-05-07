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

# 测试用书籍 wikitext - 使用实际的模板格式
SAMPLE_BOOK_WIKITEXT = """{{书籍|名称=白夜国馆藏|体裁=史书|国家=稻妻}}
白夜国馆藏是一部记录稻妻历史的书籍。

{{书籍|卷1名=常世国龙蛇传|卷1获取地点=稻妻城「八重堂」编辑黑田购买获得|卷1描述=取材自海祇岛民间故事的小说|卷1内容=造化藏奥妙，日月行吉凶。}}
{{书籍|卷2名=鬼人正传|卷2获取地点=完成「鸣海渚祭」活动获得|卷2描述=讲述了珊瑚宫一段不为人知的历史|卷2内容=第一章内容...}}
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
