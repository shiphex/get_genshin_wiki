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

    def test_extract_page_metadata_raises_for_invalid_payload(self) -> None:
        """
        测试 extract_page_metadata 对无效 payload 抛出 ParsingError。
        """
        with self.assertRaises(ParsingError):
            self.parser.extract_page_metadata({"query": {"pages": {}}})


if __name__ == "__main__":
    unittest.main()
