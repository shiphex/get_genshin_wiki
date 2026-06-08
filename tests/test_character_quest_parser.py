from __future__ import annotations

import unittest

from get_genshin_wiki.parser import WikiTextParser
from tests.helpers import build_page_payload

CHARACTER_QUEST_LIST_WIKITEXT = """== 传说任务和部族纪闻 ==
=== 蒙德 ===
[[File:任务-传说任务-安柏.png|120px]]
[[风、勇气和翅膀|小兔之章 第一幕]] [[风、勇气和翅膀]]
=== 璃月 ===
[[File:任务-传说任务-钟离.png|120px]]
[[盐花|古闻之章 第一幕]] [[盐花]]
=== 纳塔 ===
==== 部族纪闻 ====
===== 流泉之众 =====
[[File:任务-传说任务-「流泉之众」.png|120px]]
[[寻找神秘岛的人|流泉所归之处 第一幕]] [[寻找神秘岛的人]]
[[File:任务-传说任务-玛拉妮.png|120px]]
[[神秘岛之旅|流泉所归之处 第三幕]] [[神秘岛之旅]]
== 邀约事件 ==
[[班尼特]]
"""

CHARACTER_QUEST_WIKITEXT = """{{任务
|任务名称=漩涡之遗
|任务地区=璃月
|任务类型=传说任务
|任务描述=偶遇钟离之后，你决定加入这支考古小队。
|出场人物=[[钟离]]、[[克列门特]]、[[宛烟]]
}}
==任务相关==
===系列任务===
* [[古闻之章]]
* [[盐花]]
===前置任务===
* [[旧日之影]]
===后续任务===
* [[深锁之迹]]
===任务流程===
* 前往孤云阁
* 与众人交谈
==任务剧情==
===前往孤云阁===
* 派蒙：我们真的要去孤云阁吗？
* 旅行者：先过去看看。
===与众人交谈===
* 克列门特：学者也该学会冒险。
{{剧情选项
|选项1=（作为学者，确实有点奇怪……）
|剧情1=* 钟离：无妨，先听他说完。<br>之后再作判断。
|选项2=（不，就是想借考古的名义发财吧……）
}}
落败的鳍游龙四散逃走了。
[[Category:任务]]
[[Category:传说任务]]
"""

TRIBAL_QUEST_WIKITEXT = """{{任务
|任务名称=值得托付之人
|任务地区=纳塔
|任务类型=部族纪闻
|任务描述=你与玛拉妮一起踏上了最后的神秘岛之旅。
|出场人物=[[玛拉妮]]、[[派蒙]]
|相关活动=「流泉所归之处」
}}
==任务相关==
===系列任务===
* [[流泉所归之处]]
* [[神秘岛之旅]]
===前置任务===
* [[最好的伙伴]]
===后续任务===
* [[终章之后]]
===任务流程===
* 前往出发地点
==任务剧情==
===前往出发地点===
* 玛拉妮：终于到了出发的时候。
* 旅行者：我们走吧。
[[Category:任务]]
[[Category:部族纪闻]]
"""

PREVIOUS_CHARACTER_QUEST_WIKITEXT = """{{任务
|任务名称=旧日之影
|任务地区=璃月
|任务类型=传说任务
|任务描述=继续跟随钟离调查盐之魔神的旧事。
|出场人物=[[钟离]]、[[派蒙]]
}}
==任务相关==
===系列任务===
* [[古闻之章]]
* [[盐花]]
===后续任务===
* [[漩涡之遗]]
===任务流程===
* 跟随钟离
==任务剧情==
===跟随钟离===
* 钟离：往前走吧。
[[Category:任务]]
[[Category:传说任务]]
"""

MODERN_CHARACTER_QUEST_LIST_WIKITEXT = """== 传说任务和部族纪闻 ==
=== {{图标|蒙德}} ===
{{图标|任务|迪卢克|1|夜枭之章 第一幕|暗夜英雄的不在场证明（系列任务）}}
{{图标|任务|可莉|1|四叶草之章 第一幕|真正的宝物}}
=== {{图标|纳塔}} ===
==== 部族纪闻 ====
==== [[流淌着色彩的回忆|烟谜主]] ====
{{图标|任务|「烟谜主」|2|流淌着色彩的回忆 第二幕|传说中的「色彩」}}
{{图标|任务|自定义|3|流淌着色彩的回忆 第三幕|七彩之战的真相|任务-传说任务-茜特菈莉}}
==== [[尤潘基的回火|悬木人]] ====
{{图标|任务|「悬木人」|1|尤潘基的回火 第一幕|维茨特兰的神秘访客}}
{{图标|任务|「悬木人」|2|尤潘基的回火 第二幕|英雄的仪式}}
{{图标|任务|自定义|3|尤潘基的回火 第三幕|基尼奇的交易|任务-传说任务-基尼奇}}
== 邀约事件 ==
"""

MODERN_TRIBAL_QUEST_WIKITEXT = """{{DISPLAYTITLE:基尼奇的交易}}
{{任务
|任务名称=基尼奇的交易
|任务地区=纳塔
|任务类型=部族纪闻
|任务描述=你们正打算前往特立尼达长老的住处，一位意外人士却抢先找到了你们…
|相关活动=[[尤潘基的回火]]
|出场人物=基尼奇、特立尼达、瓦伊纳
|任务条件=完成部族纪闻「[[英雄的仪式]]」
|开放等级=40
|系列任务=尤潘基的回火,基尼奇的交易
|任务编号=03
|前置任务=*[[英雄的仪式]]
|后续任务=*[[我，游火人]]
|任务流程=*前往特立尼达长老家
*与基尼奇会合
*与基尼奇到一边走走
}}
==任务剧情==
===前往特立尼达长老家===
*基尼奇：旅行者，派蒙。
[[分类:任务]]
[[分类:部族纪闻]]
"""

MODERN_COMMA_CHAPTER_LIST_WIKITEXT = """== 传说任务和部族纪闻 ==
=== {{图标|纳塔}} ===
==== 部族纪闻 ====
==== [[花之归尘，羽之将坠|花羽会]] ====
{{图标|任务|「花羽会」|1|花之归尘，羽之将坠 第一幕|特拉洛坎的失翼者}}
{{图标|任务|「花羽会」|2|花之归尘，羽之将坠 第二幕|试炼前夜}}
{{图标|任务|自定义|3|花之归尘，羽之将坠 第三幕|枪与翼|任务-传说任务-恰斯卡}}
== 邀约事件 ==
"""

MODERN_COMMA_CHAPTER_QUEST_WIKITEXT = """{{任务
|任务名称=对决之刻
|任务地区=纳塔
|任务类型=部族纪闻
|任务描述=你即将参与最后的对决。
|相关活动=[[花之归尘，羽之将坠]]
|出场人物=恰斯卡、派蒙
|系列任务=花之归尘，羽之将坠,枪与翼
|前置任务=*[[亡命追缉]]
|任务流程=*前往决斗场
}}
==任务剧情==
===前往决斗场===
*恰斯卡：准备好了吗？
[[分类:任务]]
[[分类:部族纪闻]]
"""


class CharacterQuestParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = WikiTextParser()

    def test_parse_character_quest_list_page_extracts_story_and_tribal_entries(self) -> None:
        payload = build_page_payload("传说任务", CHARACTER_QUEST_LIST_WIKITEXT, page_id=401)

        entries = self.parser.parse_character_quest_list_page(payload)
        context = self.parser.build_character_quest_series_context(entries)

        self.assertEqual(
            ["风、勇气和翅膀", "盐花", "寻找神秘岛的人", "神秘岛之旅"],
            [entry["title"] for entry in entries],
        )
        self.assertEqual("小兔之章", entries[0]["chapter_name"])
        self.assertEqual("第一幕", entries[0]["act"])
        self.assertEqual("钟离", entries[1]["related_character"])
        self.assertEqual("部族纪闻", entries[2]["quest_type"])
        self.assertEqual("流泉之众", entries[2]["related_character"])
        self.assertEqual("第三幕", context["神秘岛之旅"]["act"])
        self.assertEqual("玛拉妮", context["神秘岛之旅"]["related_character"])

    def test_parse_character_quest_page_extracts_context_dialogues_and_options(self) -> None:
        list_payload = build_page_payload("传说任务", CHARACTER_QUEST_LIST_WIKITEXT, page_id=402)
        payload = build_page_payload("漩涡之遗", CHARACTER_QUEST_WIKITEXT, page_id=403)
        series_context = self.parser.build_character_quest_series_context(
            self.parser.parse_character_quest_list_page(list_payload)
        )

        result = self.parser.parse_character_quest_page(payload, series_context=series_context)
        serialized = result.to_dict()

        self.assertEqual("漩涡之遗", result.title)
        self.assertEqual("璃月", result.region)
        self.assertEqual("传说任务", result.quest_type)
        self.assertEqual("钟离", result.related_character)
        self.assertEqual("古闻之章", result.chapter_name)
        self.assertEqual("第一幕", result.act)
        self.assertEqual("盐花", result.act_name)
        self.assertEqual("盐花", result.related_quest)
        self.assertEqual("旧日之影", result.previous_quest)
        self.assertEqual("深锁之迹", result.next_quest)
        self.assertEqual(["前往孤云阁", "与众人交谈"], result.objectives)
        self.assertEqual(
            ["character", "traveler", "character", "option", "option", "character", "narration"],
            [dialogue.dialogue_type for dialogue in result.dialogues],
        )
        self.assertEqual("前往孤云阁", result.dialogues[0].task_flow)
        self.assertEqual("（作为学者，确实有点奇怪……）", result.dialogues[3].text)
        self.assertEqual("无妨，先听他说完。\n之后再作判断。", result.dialogues[5].text)
        self.assertEqual("落败的鳍游龙四散逃走了。", result.dialogues[6].text)
        self.assertEqual("盐花", serialized["所属任务"])

    def test_parse_character_quest_page_resolves_tribal_context_via_parent_act(self) -> None:
        list_payload = build_page_payload("传说任务", CHARACTER_QUEST_LIST_WIKITEXT, page_id=404)
        payload = build_page_payload("值得托付之人", TRIBAL_QUEST_WIKITEXT, page_id=405)
        series_context = self.parser.build_character_quest_series_context(
            self.parser.parse_character_quest_list_page(list_payload)
        )

        result = self.parser.parse_character_quest_page(payload, series_context=series_context)

        self.assertEqual("部族纪闻", result.quest_type)
        self.assertEqual("纳塔", result.region)
        self.assertEqual("流泉所归之处", result.chapter_name)
        self.assertEqual("第三幕", result.act)
        self.assertEqual("神秘岛之旅", result.act_name)
        self.assertEqual("神秘岛之旅", result.related_quest)
        self.assertEqual("玛拉妮", result.related_character)
        self.assertEqual("最好的伙伴", result.previous_quest)
        self.assertEqual("终章之后", result.next_quest)
        self.assertEqual("玛拉妮", result.dialogues[0].speaker)

    def test_parse_character_quest_list_page_supports_icon_template_entries(self) -> None:
        payload = build_page_payload("传说任务", MODERN_CHARACTER_QUEST_LIST_WIKITEXT, page_id=406)

        entries = self.parser.parse_character_quest_list_page(payload)
        context = self.parser.build_character_quest_series_context(entries)

        self.assertEqual(
            ["暗夜英雄的不在场证明", "真正的宝物", "传说中的「色彩」", "七彩之战的真相", "维茨特兰的神秘访客", "英雄的仪式", "基尼奇的交易"],
            [entry["title"] for entry in entries],
        )
        self.assertEqual("夜枭之章", entries[0]["chapter_name"])
        self.assertEqual("第一幕", entries[0]["act"])
        self.assertEqual("暗夜英雄的不在场证明", entries[0]["act_name"])
        self.assertEqual("部族纪闻", entries[2]["quest_type"])
        self.assertEqual("茜特菈莉", context["七彩之战的真相"]["related_character"])
        self.assertEqual("第三幕", context["基尼奇的交易"]["act"])

    def test_parse_character_quest_page_uses_template_series_and_list_context_for_modern_pages(self) -> None:
        list_payload = build_page_payload("传说任务", MODERN_CHARACTER_QUEST_LIST_WIKITEXT, page_id=407)
        payload = build_page_payload("基尼奇的交易（任务）", MODERN_TRIBAL_QUEST_WIKITEXT, page_id=408)
        series_context = self.parser.build_character_quest_series_context(
            self.parser.parse_character_quest_list_page(list_payload)
        )

        result = self.parser.parse_character_quest_page(payload, series_context=series_context)

        self.assertEqual("基尼奇的交易", result.title)
        self.assertEqual("纳塔", result.region)
        self.assertEqual("部族纪闻", result.quest_type)
        self.assertEqual("尤潘基的回火", result.chapter_name)
        self.assertEqual("第三幕", result.act)
        self.assertEqual("基尼奇的交易", result.act_name)
        self.assertEqual("基尼奇的交易", result.related_quest)
        self.assertEqual("英雄的仪式", result.previous_quest)
        self.assertEqual("我，游火人", result.next_quest)

    def test_parse_character_quest_page_preserves_chapter_names_with_chinese_comma(self) -> None:
        list_payload = build_page_payload("传说任务", MODERN_COMMA_CHAPTER_LIST_WIKITEXT, page_id=409)
        payload = build_page_payload("对决之刻", MODERN_COMMA_CHAPTER_QUEST_WIKITEXT, page_id=410)
        series_context = self.parser.build_character_quest_series_context(
            self.parser.parse_character_quest_list_page(list_payload)
        )

        result = self.parser.parse_character_quest_page(payload, series_context=series_context)

        self.assertEqual("花之归尘，羽之将坠", result.chapter_name)
        self.assertEqual("第三幕", result.act)
        self.assertEqual("枪与翼", result.act_name)
        self.assertEqual("枪与翼", result.related_quest)


if __name__ == "__main__":
    unittest.main()
