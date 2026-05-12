"""
WikiText 解析器
===============

本模块负责将 MediaWiki 页面的原始 wikitext 内容解析为结构化数据。

核心功能
--------
- 模板提取：解析页面中的模板及其参数
- 分类提取：识别 [[Category:xxx]] 和 [[分类:xxx]] 格式的分类链接
- 章节分割：按标题（== xxx ==）分割页面内容
- 角色解析：专门解析原神角色页面的属性、天赋、命座等

依赖
----
- mwparserfromhell : Python wikitext 解析库

使用示例
--------
    from get_genshin_wiki.parser import WikiTextParser

    parser = WikiTextParser()
    result = parser.parse_page(payload)
    print(result.title, result.categories)

    # 解析角色页面
    character = parser.parse_character_page(payload)
    print(character.attributes)
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Iterable

import mwparserfromhell

from .exceptions import ParsingError
from .models import (
    ArtifactPieceRecord,
    ArtifactSetRecord,
    CharacterRecord,
    MonsterRecord, ParsedPage,
    ParsedSection,
    WeaponRecord,
    FoodRecord,
    ItemRecord,
    MaterialRecord,
    NameCardRecord,
    QuestItemRecord,
    SecretItemRecord,
    WildlifeRecord,
    BookRecord, BookVolume,
    AdventureNotesRecord,
    CharacterRecord,
    CharacterStoryRecord,
    CharacterVoiceRecord,
    ConstellationRecord,
    TalentRecord,
)

# 分类链接匹配正则：[[Category:xxx]] 或 [[分类:xxx]]
_CATEGORY_PATTERN = re.compile(r"\[\[\s*(?:Category|分类)\s*:\s*([^\]|]+)")
# 分类链接本身（用于从正文中移除分类标记）
_CATEGORY_LINK_PATTERN = re.compile(r"\[\[\s*(?:Category|分类)\s*:[^\]]+\]\]")

_BR_TAG_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
_DEL_TAG_PATTERN = re.compile(r"<del>(.*?)</del>", re.IGNORECASE | re.DOTALL)
_PHONETIC_TEMPLATE_PATTERN = re.compile(
    r"\{\{\s*注音\s*\|\s*([^|{}]+?)\s*\|\s*([^{}|]+?)\s*\}\}",
    re.DOTALL,
)
_BLACKOUT_TEMPLATE_PATTERN = re.compile(
    r"\{\{\s*黑幕\s*\|\s*(.*?)\s*\}\}",
    re.IGNORECASE | re.DOTALL,
)
_PARENTHESIS_PATTERN = re.compile(r"[（(]([^（）()]+)[）)]")
_SWITCH_PANEL_CONTENT_PATTERN = re.compile(
    r"\{\{\s*切换板\s*\|\s*(?:显示内容|折叠内容)\s*\}\}(.*?)\{\{\s*切换板\s*\|\s*内容结束\s*\}\}",
    re.DOTALL,
)
_SWITCH_PANEL_TITLE_PATTERN = re.compile(
    r"\{\{\s*切换板\s*\|\s*(?:默认显示|默认折叠)\s*\|\s*([^{}|]+?)\s*\}\}",
    re.DOTALL,
)
_VOICE_BLOCK_PATTERN = re.compile(
    r"<div\b(?=[^>]*class=[\"']resp-tab-content[\"'])(?=[^>]*style=[\"']display\s*:\s*block;?[\"'])[^>]*>"
    r"(.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
_FILE_LINK_PATTERN = re.compile(r"\[\[\s*(?:File|file|文件)\s*:[^\]]+\]\]", re.IGNORECASE)
_LIST_SPLIT_PATTERN = re.compile(r"(?:\n|、|，|,)+")

# 角色属性模板关键词（用于识别角色信息模板）
_CHARACTER_TEMPLATE_KEYWORDS = ("角色属性", "角色信息", "角色资料", "角色")
_CHARACTER_TEMPLATE_EXCLUDES = ("故事", "天赋", "技能", "命座", "命之座", "语音", "切换板", "/")
# 天赋模板关键词
_TALENT_TEMPLATE_KEYWORDS = ("天赋", "技能")
# 命座模板关键词
_CONSTELLATION_TEMPLATE_KEYWORDS = ("命之座", "命座")
_BREAK_TAG_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HORIZONTAL_RULE_PATTERN = re.compile(r"<hr\s*/?>", re.IGNORECASE)
_BREAK_WITH_LINE_END_PATTERN = re.compile(r"(<br\s*/?>)\s*\n", re.IGNORECASE)
_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_ICON_TEMPLATE_PATTERN = re.compile(r"\{\{\s*图标\s*(?:\|([^{}|]+))?(?:\|([^{}|]+))?(?:\|[^{}]*)*}}")
_FILE_LINK_PATTERN = re.compile(r"\[\[\s*(?:文件|File|Image)\s*:[^\]]+\]\]", re.IGNORECASE)
_HTML_TAG_PATTERN = re.compile(r"</?[A-Za-z][^>]*>")
_TABBER_SEPARATOR_PATTERN = re.compile(r"(?m)^\|-\|\s*$")
_TABBER_LABEL_PATTERN = re.compile(r"(?m)^\d+\s*=\s*$")
_FILE_LINK_PREFIXES = ("文件:", "File:", "Image:", "Category:", "分类:")
# 书籍模板关键词
_BOOK_TEMPLATE_KEYWORDS = ("书籍", "书籍信息", "白夜国馆藏", "千世流樱", "浮世风流", "冒险家")

# 国家代码映射表
_COUNTRY_CODE_MAP: dict[str, str] = {
    "0": "提瓦特",
    "1": "蒙德",
    "2": "璃月",
    "3": "稻妻",
    "4": "须弥",
    "5": "枫丹",
    "6": "纳塔",
    "7": "挪德卡莱",
    "8": "至冬",
}


def _parse_country_code(value: str) -> str:
    """解析国家代码值，返回国家名称。

    处理两种格式：
    1. 纯数字代码：直接查表映射
    2. 带备注的数字：提取数字部分后查表映射

    参数
    ----
    value : str
        国家字段值，可能是 "3" 或 "3<!-- 备注 -->"

    返回
    ----
    str
        国家名称，映射失败则返回原始值
    """
    # 提取数字部分（处理带 HTML 注释的情况）
    match = re.match(r"^(\d+)", value.strip())
    if match:
        code = match.group(1)
        return _COUNTRY_CODE_MAP.get(code, value)
    return value
_STORY_TEMPLATE_KEYWORDS = ("角色/故事", "角色故事")

_TITLE_KEYS = ("称号", "称谓", "头衔")
_FULL_NAME_KEYS = ("全名", "本名")
_HOMELAND_KEYS = ("所属", "所属地区", "国家")
_ORIGIN_KEYS = ("出身",)
_AFFILIATION_KEYS = ("归属", "阵营", "所属组织")
_RACE_KEYS = ("种族",)
_INTRODUCTION_KEYS = ("介绍", "简介", "角色介绍")
_GOD_EYE_DESCRIPTION_KEYS = ("神之眼描述", "神之眼说明", "权能名称")
_ELEMENT_KEYS = ("元素属性", "元素")
_WEAPON_KEYS = ("武器类型", "武器")
_CONSTELLATION_KEYS = ("命之座", "星座")
_SPECIAL_DISH_KEYS = ("特殊料理", "特色料理")
_GENDER_KEYS = ("性别",)
_BOND_ATTRIBUTE_KEYS = ("羁绊属性",)
_NICKNAME_KEYS = ("昵称/外号", "昵称", "外号", "别名")
_OUTFIT_KEYS = ("衣装名称", "衣装", "服饰")
_PROFESSION_KEYS = ("职业",)
_INTRO_SECTION_KEYS = ("壹·人物",)
_STORY_SECTION_KEYS = ("贰·故事",)
_VOICE_SECTION_KEYS = ("角色语音",)


class WikiTextParser:
    """
    MediaWiki WikiText 解析器。

    将 MediaWiki API 返回的页面 payload 中的 wikitext 内容
    解析为结构化的 Python 对象。
    """

    def extract_page_metadata(self, payload: dict[str, Any]) -> tuple[str, int | str | None, str]:
        """
        从页面 payload 中提取元数据和 wikitext。

        参数
        ----
        payload : dict[str, Any]
            MediaWiki API 返回的页面原始 payload

        返回
        ----
        tuple[str, int | str | None, str]
            (页面标题, 页面ID, wikitext) 三元组

        异常
        ----
        ParsingError
            当 payload 格式异常或缺少必要字段时抛出
        """
        pages = payload.get("query", {}).get("pages", {})
        if not pages:
            raise ParsingError("payload.query.pages is empty")
        page = next(iter(pages.values()))
        revisions = page.get("revisions", [])
        if not revisions:
            raise ParsingError("page.revisions is empty")
        slots = revisions[0].get("slots", {})
        wikitext = slots.get("main", {}).get("*", "")
        if not wikitext:
            raise ParsingError("page main slot is empty")
        return page.get("title", ""), page.get("pageid"), wikitext

    def parse_templates(self, wikitext: str) -> dict[str, list[dict[str, str]]]:
        """
        提取页面中的所有模板及其参数。

        MediaWiki 模板格式：{{模板名|参数1=值1|参数2=值2}}

        参数
        ----
        wikitext : str
            页面原始 wikitext 内容

        返回
        ----
        dict[str, list[dict[str, str]]]
            模板字典，键为模板名，值为该模板的参数列表
            每个参数是一个 dict，键为参数名，值为参数值
        """
        code = mwparserfromhell.parse(wikitext)
        grouped: dict[str, list[dict[str, str]]] = {}
        # filter_templates(recursive=True) 会递归解析嵌套模板
        for template in code.filter_templates(recursive=True):
            name = str(template.name).strip()
            # 提取模板的所有参数
            params = {
                str(param.name).strip(): str(param.value).strip()
                for param in template.params
            }
            grouped.setdefault(name, []).append(params)
        return grouped

    def parse_categories(self, wikitext: str) -> list[str]:
        """
        提取页面中的分类链接。

        支持中英文 Category 语法：[[Category:xxx]] 和 [[分类:xxx]]

        参数
        ----
        wikitext : str
            页面原始 wikitext 内容

        返回
        ----
        list[str]
            分类名称列表（按字母排序，去重）
        """
        # findall 返回所有匹配的捕获组内容（即分类名）
        return sorted({match.strip() for match in _CATEGORY_PATTERN.findall(wikitext) if match.strip()})

    def parse_sections(self, wikitext: str) -> list[ParsedSection]:
        """
        按标题分割页面内容为章节。

        使用 mwparserfromhell 的 get_sections 方法，
        会保留 == 标题 == 格式的章节结构。

        参数
        ----
        wikitext : str
            页面原始 wikitext 内容

        返回
        ----
        list[ParsedSection]
            章节列表，第一个章节默认标题为"简介"
        """
        # 先移除分类链接标记，避免干扰章节解析
        sanitized_wikitext = _CATEGORY_LINK_PATTERN.sub("", wikitext)
        code = mwparserfromhell.parse(sanitized_wikitext)
        sections: list[ParsedSection] = []
        # get_sections(include_headings=True, flat=True) 返回扁平的章节列表
        for index, section in enumerate(code.get_sections(include_headings=True, flat=True)):
            heading_nodes = section.filter_headings()
            # 第一个无标题章节默认为"简介"
            title = "简介" if index == 0 or not heading_nodes else str(heading_nodes[0].title).strip()
            # 先替换换行标签，再 strip_code，避免 <br> 被提前吞掉
            text = mwparserfromhell.parse(self._normalize_line_breaks(str(section))).strip_code().strip()
            text = self._normalize_text(text)
            # 去除标题本身（如果文本以标题开头）
            if heading_nodes:
                heading_text = str(heading_nodes[0].title).strip()
                if text.startswith(heading_text):
                    text = text[len(heading_text):].lstrip()
            if text:
                sections.append(ParsedSection(title=title, text=self._normalize_text(text)))
        return sections

    def parse_page(self, payload: dict[str, Any]) -> ParsedPage:
        """
        解析通用 Wiki 页面。

        综合调用 extract_page_metadata、parse_sections、parse_categories、parse_templates。

        参数
        ----
        payload : dict[str, Any]
            MediaWiki API 返回的页面 payload

        返回
        ----
        ParsedPage
            包含页面完整解析结果的页面对象
        """
        title, page_id, wikitext = self.extract_page_metadata(payload)
        sections = self.parse_sections(wikitext)
        # 摘要为第一个章节的文本
        summary = sections[0].text if sections else ""
        categories = self.parse_categories(wikitext)
        if not categories:
            categories = self._extract_payload_categories(payload)
        return ParsedPage(
            title=title,
            page_id=page_id,
            summary=summary,
            categories=categories,
            sections=sections,
            templates=self.parse_templates(wikitext),
            wikitext=wikitext,
        )

    def parse_character_page(
        self,
        payload: dict[str, Any],
        voice_payload: dict[str, Any] | None = None,
    ) -> CharacterRecord:
        """
        解析原神角色页面。

        在通用页面解析基础上，额外提取：
        - 角色属性（从角色信息模板）
        - 天赋技能列表
        - 命座/星座列表

        参数
        ----
        payload : dict[str, Any]
            MediaWiki API 返回的页面 payload

        返回
        ----
        CharacterRecord
            包含角色结构化数据的对象
        """
        parsed_page = self.parse_page(payload)
        attributes = self._select_best_template(parsed_page.templates, _CHARACTER_TEMPLATE_KEYWORDS)
        talents = self._collect_matching_templates(parsed_page.templates, _TALENT_TEMPLATE_KEYWORDS)
        constellations = self._collect_matching_templates(parsed_page.templates, _CONSTELLATION_TEMPLATE_KEYWORDS)
        story_records = self._extract_story_records(parsed_page.templates)
        adventure_notes = self._extract_adventure_notes(parsed_page.templates)
        character_introductions = self._extract_character_introductions(parsed_page.templates)
        if not character_introductions:
            character_introductions = self._extract_character_introductions_from_wikitext(parsed_page.wikitext)
        story_sections = self._extract_story_sections(parsed_page.templates)
        if not story_sections:
            story_sections = self._extract_story_sections_from_wikitext(parsed_page.wikitext)
        voice_records = self._extract_voice_records(parsed_page.templates)
        if voice_payload is not None:
            voice_page_records = self.parse_character_voice_page(voice_payload)
            if voice_page_records:
                voice_records = voice_page_records
        talent_records = [self._build_talent_record(params) for params in talents if params]
        constellation_records = [self._build_constellation_record(params) for params in constellations if params]

        titles = self._extract_list_field(attributes, _TITLE_KEYS)
        full_name = self._extract_text_field(attributes, _FULL_NAME_KEYS)
        homeland = self._extract_text_field(attributes, _HOMELAND_KEYS)
        origin = self._extract_text_field(attributes, _ORIGIN_KEYS)
        affiliation = self._extract_list_field(attributes, _AFFILIATION_KEYS, context="affiliation")
        race = self._extract_text_field(attributes, _RACE_KEYS)
        introduction = self._extract_text_field(attributes, _INTRODUCTION_KEYS, fallback=parsed_page.summary)
        god_eye_description = self._extract_text_field(attributes, _GOD_EYE_DESCRIPTION_KEYS)
        element = self._extract_text_field(attributes, _ELEMENT_KEYS)
        weapon_type = self._extract_text_field(attributes, _WEAPON_KEYS)
        constellation_name = self._extract_text_field(attributes, _CONSTELLATION_KEYS)
        special_dish = self._extract_text_field(attributes, _SPECIAL_DISH_KEYS)
        gender = self._extract_text_field(attributes, _GENDER_KEYS)
        bond_attribute = self._extract_text_field(attributes, _BOND_ATTRIBUTE_KEYS)
        nicknames = self._extract_nicknames(attributes)
        outfits = self._extract_list_field(attributes, _OUTFIT_KEYS)
        profession = self._extract_text_field(attributes, _PROFESSION_KEYS, context="profession")
        power_record = self._extract_power_record(parsed_page.templates, god_eye_description)

        return CharacterRecord(
            title=parsed_page.title,
            page_id=parsed_page.page_id,
            summary=introduction or parsed_page.summary,
            attributes=attributes,
            talents=talents,
            constellations=constellations,
            titles=titles,
            full_name=full_name,
            homeland=homeland,
            origin=origin,
            affiliation=affiliation,
            race=race,
            introduction=introduction,
            god_eye_description=god_eye_description,
            god_eye_story="" if power_record is None else power_record.content,
            element=element,
            weapon_type=weapon_type,
            constellation=constellation_name,
            special_dish=special_dish,
            gender=gender,
            bond_attribute=bond_attribute,
            nicknames=nicknames,
            outfits=outfits,
            profession=profession,
            talent_records=talent_records,
            constellation_records=constellation_records,
            story_records=story_records,
            voice_records=voice_records,
            adventure_notes=adventure_notes,
            character_introductions=character_introductions,
            story_sections=story_sections,
            power_record=power_record,
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
        )

    def parse_weapon_page(self, payload: dict[str, Any]) -> WeaponRecord:
        """
        解析原神武器页面。

        在通用页面解析基础上，额外提取：
        - 武器类型、稀有度、基础攻击力
        - 被动效果
        - 突破材料序列
        - 获取途径
        - 锻造材料、精炼材料
        - 武器故事、介绍

        参数
        ----
        payload : dict[str, Any]
            MediaWiki API 返回的页面 payload

        返回
        ----
        WeaponRecord
            包含武器结构化数据的对象
        """
        parsed_page = self.parse_page(payload)
        # 从模板中筛选武器属性（参数最多的最完整）
        attributes = self._select_best_template(parsed_page.templates, ("武器属性", "武器信息", "武器", "武器图鉴"))

        # 同时从"武器突破"模板获取突破材料
        ascension_template = self._select_best_template(parsed_page.templates, ("武器突破",))
        if ascension_template:
            attributes = {**attributes, **ascension_template}

        # 提取各字段
        title = parsed_page.title
        weapon_type = attributes.get("类型", "")

        # 突破材料序列（多个参数，可能是列表）
        ascension_weapon_materials = self._extract_prefixed_list_field(attributes, "突破武器材料")
        ascension_premium_materials = self._extract_prefixed_list_field(attributes, "突破高级材料")
        ascension_common_materials = self._extract_prefixed_list_field(attributes, "突破普通材料")

        # 获取途径
        obtaining_method = self._parse_obtaining_method(attributes.get("获取途径", ""))

        # 锻造材料
        forging_blueprint = self._parse_forging_material(attributes) or "不可锻造获取"

        # 精炼材料
        refining_material = self._parse_refining_material(attributes) or "不可使用材料精炼"

        # 介绍和故事
        description = attributes.get("介绍", "")
        story = self._clean_br_tags(attributes.get("故事", ""))

        return WeaponRecord(
            title=title,
            weapon_type=weapon_type,
            description=description,
            ascension_weapon_materials=ascension_weapon_materials,
            ascension_premium_materials=ascension_premium_materials,
            ascension_common_materials=ascension_common_materials,
            obtaining_method=obtaining_method,
            forging_blueprint=forging_blueprint,
            refining_material=refining_material,
            story=story,
        )

    def parse_artifact_set_page(self, payload: dict[str, Any]) -> ArtifactSetRecord:
        """
        解析原神圣遗物套装页面。

        在通用页面解析基础上，额外提取：
        - 套装名称
        - 各部件信息（生之花、死之羽、时之沙、空之杯、理之冠）
        - 套装效果
        - 获取方式

        参数
        ----
        payload : dict[str, Any]
            MediaWiki API 返回的页面 payload

        返回
        ----
        ArtifactSetRecord
            包含圣遗物套装结构化数据的对象
        """
        parsed_page = self.parse_page(payload)
        # 从模板中筛选圣遗物属性（参数最多的最完整）
        attributes = self._select_best_template(parsed_page.templates, ("圣遗物属性", "圣遗物信息", "圣遗物套装"))

        title = parsed_page.title

        # 获取方式解析
        obtaining_method = self._parse_artifact_obtaining_method(attributes, parsed_page.templates)

        # 提取各部件信息
        pieces: list[ArtifactPieceRecord] = []
        slot_mapping = {
            "生之花": "生之花",
            "死之羽": "死之羽",
            "时之沙": "时之沙",
            "空之杯": "空之杯",
            "理之冠": "理之冠",
        }
        for slot_key, slot_name in slot_mapping.items():
            # 名称可能在 "生之花" 或 "生之花名称" 字段中
            piece_name = attributes.get(slot_key, "") or attributes.get(f"{slot_key}名称", "")
            piece = ArtifactPieceRecord(
                slot=slot_name,
                name=piece_name,
                description=attributes.get(f"{slot_key}描述", ""),
                story=attributes.get(f"{slot_key}故事", ""),
            )
            # 清理描述和故事中的<br>换行符
            piece.description = self._clean_br_tags(piece.description)
            piece.story = self._clean_br_tags(piece.story)
            pieces.append(piece)

        return ArtifactSetRecord(
            title=title,
            obtaining_method=obtaining_method,
            pieces=pieces,
        )

    def parse_monster_page(self, payload: dict[str, Any]) -> MonsterRecord:
        """
        解析原神怪物页面。

        提取怪物特有的信息：
        - 怪物名称
        - 怪物类别（如：周刷BOSS、精英等）
        - 怪物分类（如：值得铭记的强敌、自律机关等）
        - 怪物类型（如：其他、战争机械等）
        - 出现地点
        - 掉落素材
        - 介绍

        参数
        ----
        payload : dict[str, Any]
            MediaWiki API 返回的页面 payload

        返回
        ----
        MonsterRecord
            包含怪物结构化数据的对象
        """
        parsed_page = self.parse_page(payload)

        # 怪物属性模板关键词
        monster_template_keywords = ("怪物信息", "怪物属性", "怪物资料")
        attributes = self._select_best_template(parsed_page.templates, monster_template_keywords)

        # 提取怪物特有字段
        monster_class = attributes.get("怪物类别", attributes.get("类别", ""))
        monster_category = attributes.get("怪物分类", attributes.get("分类", ""))
        monster_type = attributes.get("怪物类型", attributes.get("类型", ""))
        location = attributes.get("出现地点", attributes.get("地点", ""))

        # 掉落素材处理：查找掉落素材模板
        drop_materials = self._extract_drop_materials(parsed_page.templates, attributes)
        # 过滤通用掉落项
        drop_materials = self._filter_drop_materials(drop_materials)

        # 清理位置字段的 wikitext 格式
        location = self._clean_wikitext(location)

        # 介绍为第一个章节的文本，换行使用 \n 表示
        raw_description = parsed_page.summary
        # 清理 wikitext 格式，保留实际换行符
        description = self._clean_wikitext(raw_description, preserve_newlines=True)

        return MonsterRecord(
            title=parsed_page.title,
            monster_class=monster_class,
            monster_category=monster_category,
            monster_type=monster_type,
            location=location,
            drop_materials=drop_materials,
            description=description,
        )

    def _split_drop_materials(self, text: str) -> list[str]:
        """
        将掉落素材文本分割为列表。

        支持多种分隔符：逗号（,）、中文逗号（，）、顿号（、）、<br>、换行符

        参数
        ----
        text : str
            原始素材文本

        返回
        ----
        list[str]
            分割后的素材列表
        """
        import re
        # 先统一分隔符
        text = re.sub(r"[,，、<br\s*/?>\n]+", "、", text)
        # 按、分割
        parts = text.split("、")
        return [p.strip() for p in parts if p.strip()]

    def _extract_drop_materials(
        self,
        templates: dict[str, list[dict[str, str]]],
        attributes: dict[str, str],
    ) -> list[str]:
        """
        从模板中提取掉落素材。

        参数
        ----
        templates : dict[str, list[dict[str, str]]]
            页面解析出的模板字典
        attributes : dict[str, str]
            怪物属性模板的参数

        返回
        ----
        list[str]
            掉落素材名称列表
        """
        drop_materials: list[str] = []

        # 优先从"掉落素材"字段提取
        drop_str = attributes.get("掉落素材", "")
        if drop_str:
            # 判断是否为 BOSS 类型
            if drop_str.strip() == "BOSS":
                # BOSS掉落素材：从 BOSS素材 字段提取
                boss_materials = attributes.get("BOSS素材", "")
                if boss_materials:
                    # 分割多个素材（使用 _split_drop_materials 处理各种分隔符）
                    for material in self._split_drop_materials(boss_materials):
                        if material and material != "摩拉":
                            drop_materials.append(material)
            else:
                # 直接使用掉落素材字段的值，清理模板标记
                cleaned = self._clean_wikitext(drop_str)
                for material in self._split_drop_materials(cleaned):
                    material = material.strip()
                    if material:
                        drop_materials.append(material)

        # 从"其他掉落"字段补充（如果掉落素材不是 BOSS）
        if drop_str.strip() != "BOSS":
            other_drops = attributes.get("其他掉落", "")
            if other_drops:
                cleaned = self._clean_wikitext(other_drops)
                for material in self._split_drop_materials(cleaned):
                    material = material.strip()
                    if material and material not in drop_materials:
                        drop_materials.append(material)

        # 如果仍未找到，尝试从"混沌"相关模板参数中提取
        if not drop_materials:
            for name, items in templates.items():
                if "混沌" in name or "掉落" in name:
                    for params in items:
                        for key, value in params.items():
                            if any(keyword in key for keyword in ["素材", "掉落", "material"]):
                                if value and value not in drop_materials:
                                    cleaned = self._clean_wikitext(value)
                                    if cleaned:
                                        drop_materials.append(cleaned)

        return drop_materials

    def _clean_wikitext(self, text: str, preserve_newlines: bool = False) -> str:
        """
        清理 wikitext 中的模板标记和特殊字符，提取纯净文本。

        参数
        ----
        text : str
            原始 wikitext 文本
        preserve_newlines : bool
            是否保留换行符，默认为 False

        返回
        ----
        str
            清理后的纯净文本
        """
        import re
        # 移除 {{图标|xxx}} 格式的模板，保留名称（只保留最后一个 | 后的内容）
        text = re.sub(r"\{\{图标\|([^}|]+)(?:\|[^}]*)?\}\}", r"\1", text)
        # 移除 {{PAGENAME}} 等模板
        text = re.sub(r"\{\{[^}]+\}\}", "", text)
        # 移除 [[分类:xxx]] 或 [[xxx|yyy]] 格式的分类链接
        text = re.sub(r"\[\[([^\]]+\|)?([^]]+)\]\]", r"\2", text)
        # 移除 <br> 等 HTML 标签，替换为分隔符
        text = re.sub(r"<br\s*/?>", "、", text)
        text = re.sub(r"<[^>]+>", "", text)
        if preserve_newlines:
            # 仅移除首尾空白，保留换行
            return text.strip()
        # 清理换行符和多余空白（替换为空格或分隔符）
        text = re.sub(r"\s+", "、", text)
        # 移除连续的分隔符
        text = re.sub(r"、+", "、", text)
        text = re.sub(r"^\s*[、]+\s*|\s*[、]+\s*$", "", text)
        return text.strip()

    def _filter_drop_materials(self, materials: list[str]) -> list[str]:
        """
        过滤掉落素材中的通用/无效项。

        参数
        ----
        materials : list[str]
            原始掉落素材列表

        返回
        ----
        list[str]
            过滤后的掉落素材列表
        """
        # 需要过滤的通用项
        generic_terms = {
            "精英怪物通用掉落",
            "普通敌人通用掉落",
            "摩拉",
        }
        filtered = []
        for material in materials:
            # 跳过空字符串
            if not material.strip():
                continue
            # 跳过通用掉落标记
            if material.strip() in generic_terms:
                continue
            filtered.append(material.strip())
        return filtered

    def parse_food_page(self, payload: dict[str, Any]) -> FoodRecord:
        """解析食物页面。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("类型",),
                ("介绍",),
                ("完美介绍", "美味介绍"),
                ("失败介绍", "奇怪介绍"),
                ("所需食材", "食材"),
            ),
        )
        recipe_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (("食谱获取方式",),),
        )
        special_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("特殊料理",),
                ("特殊料理角色",),
                ("特殊料理介绍",),
            ),
        )
        recipe_section = self._find_section_text(parsed_page.sections, ("食谱信息",))
        special_section = self._find_section_text(parsed_page.sections, ("特殊料理",))
        return FoodRecord(
            title=self._resolve_record_title(parsed_page, ("名称",), preferred_params=main_template),
            page_id=parsed_page.page_id,
            type=self._resolve_value(
                parsed_page.templates,
                ("类型",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            normal_description=self._resolve_value(
                parsed_page.templates,
                ("介绍", "正常料理介绍"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            perfect_description=self._resolve_value(
                parsed_page.templates,
                ("完美介绍", "美味介绍"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            failed_description=self._resolve_value(
                parsed_page.templates,
                ("失败介绍", "奇怪介绍"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            ingredients=self._resolve_value(
                parsed_page.templates,
                ("所需食材", "食材"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            recipe_obtain_method=self._coalesce(
                self._resolve_value(
                    parsed_page.templates,
                    ("食谱获取方式",),
                    preferred_params=recipe_template,
                    wikitext=parsed_page.wikitext,
                ),
                self._extract_labeled_value(recipe_section, ("食谱获取方式",)),
            ),
            special_dish=self._coalesce(
                self._resolve_value(
                    parsed_page.templates,
                    ("特殊料理",),
                    preferred_params=special_template,
                    wikitext=parsed_page.wikitext,
                ),
                self._extract_first_non_empty_line(special_section),
            ),
            special_dish_character=self._coalesce(
                self._resolve_value(
                    parsed_page.templates,
                    ("特殊料理角色",),
                    preferred_params=special_template,
                    wikitext=parsed_page.wikitext,
                ),
                self._resolve_value(
                    parsed_page.templates,
                    ("特殊料理角色",),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
                self._extract_labeled_value(special_section, ("特殊料理角色",)),
            ),
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
        )

    def parse_wildlife_page(self, payload: dict[str, Any]) -> WildlifeRecord:
        """解析野生生物页面。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("类型",),
                ("种类",),
                ("描述", "介绍"),
                ("出现地点", "分布地点", "分布"),
                ("能否捕捉", "是否可捕捉"),
                ("钓鱼鱼饵", "鱼饵"),
                ("钓鱼时间",),
                ("钓鱼地点",),
            ),
        )
        fishing_info = {
            "bait": self._resolve_value(
                parsed_page.templates,
                ("钓鱼鱼饵", "鱼饵"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            "time": self._resolve_value(
                parsed_page.templates,
                ("钓鱼时间",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            "location": self._resolve_value(
                parsed_page.templates,
                ("钓鱼地点",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
        }
        return WildlifeRecord(
            title=self._resolve_record_title(parsed_page, ("名称",), preferred_params=main_template),
            page_id=parsed_page.page_id,
            type=self._resolve_value(
                parsed_page.templates,
                ("类型",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            species=self._resolve_value(
                parsed_page.templates,
                ("种类",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            description=self._resolve_value(
                parsed_page.templates,
                ("描述", "介绍"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            locations=self._resolve_value(
                parsed_page.templates,
                ("出现地点", "分布地点", "分布"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            capturable=self._resolve_value(
                parsed_page.templates,
                ("能否捕捉", "是否可捕捉"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            fishing_info={key: value for key, value in fishing_info.items() if value},
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
        )

    def parse_quest_item_page(self, payload: dict[str, Any]) -> QuestItemRecord:
        """解析任务道具页面。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("类型",),
                ("描述", "介绍"),
                ("相关任务",),
                ("获取方式",),
                ("内容",),
            ),
        )
        content_section = self._find_section_text(parsed_page.sections, ("内容",))
        return QuestItemRecord(
            title=self._resolve_record_title(parsed_page, ("名称",), preferred_params=main_template),
            page_id=parsed_page.page_id,
            type=self._resolve_value(
                parsed_page.templates,
                ("类型",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            description=self._resolve_value(
                parsed_page.templates,
                ("描述", "介绍"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            related_quest=self._resolve_value(
                parsed_page.templates,
                ("相关任务",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            obtain_method=self._resolve_value(
                parsed_page.templates,
                ("获取方式",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            content=self._coalesce(
                self._resolve_value(
                    parsed_page.templates,
                    ("内容", "书籍内容"),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
                content_section,
            ),
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
        )

    def parse_item_page(self, payload: dict[str, Any]) -> ItemRecord:
        """解析道具页面。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("类型",),
                ("来源", "获取方式"),
                ("用途", "用处"),
                ("介绍", "描述"),
            ),
        )
        return ItemRecord(
            title=self._resolve_record_title(parsed_page, ("名称",), preferred_params=main_template),
            page_id=parsed_page.page_id,
            type=self._resolve_value(
                parsed_page.templates,
                ("类型",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            source=self._resolve_value(
                parsed_page.templates,
                ("来源", "获取方式"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            usage=self._resolve_value(
                parsed_page.templates,
                ("用途", "用处"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            description=self._resolve_value(
                parsed_page.templates,
                ("介绍", "描述"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
        )

    def parse_material_page(self, payload: dict[str, Any]) -> MaterialRecord:
        """解析材料页面。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("类型",),
                ("来源",),
                ("介绍", "描述"),
                ("用途", "用处"),
            ),
        )
        return MaterialRecord(
            title=self._resolve_record_title(parsed_page, ("名称",), preferred_params=main_template),
            page_id=parsed_page.page_id,
            type=self._resolve_value(
                parsed_page.templates,
                ("类型",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            source=self._coalesce(
                self._extract_plain_param_from_wikitext(parsed_page.wikitext, ("来源",)),
                self._resolve_value(
                    parsed_page.templates,
                    ("来源",),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
            ),
            description=self._coalesce(
                self._extract_plain_param_from_wikitext(parsed_page.wikitext, ("介绍", "描述")),
                self._resolve_value(
                    parsed_page.templates,
                    ("介绍", "描述"),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
            ),
            usage=self._coalesce(
                self._extract_plain_param_from_wikitext(parsed_page.wikitext, ("用途", "用处")),
                self._resolve_value(
                    parsed_page.templates,
                    ("用途", "用处"),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
            ),
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
        )

    def parse_namecard_page(self, payload: dict[str, Any]) -> NameCardRecord:
        """解析名片页面。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("获取方式",),
                ("描述", "介绍"),
            ),
        )
        return NameCardRecord(
            title=self._resolve_record_title(parsed_page, ("名称",), preferred_params=main_template),
            page_id=parsed_page.page_id,
            obtain_method=self._resolve_value(
                parsed_page.templates,
                ("获取方式",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            description=self._resolve_value(
                parsed_page.templates,
                ("描述", "介绍"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
        )

    def parse_secret_item_page(self, payload: dict[str, Any]) -> SecretItemRecord:
        """解析秘境页面。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("秘境类型", "类型"),
                ("秘境介绍", "介绍", "描述"),
                ("难度4掉落", "掉落"),
            ),
        )
        drop_value = self._coalesce(
            self._resolve_highest_difficulty_drop_value(
                parsed_page.templates,
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            self._resolve_raw_value(
                parsed_page.templates,
                ("掉落",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
        )
        domain_type = self._resolve_value(
            parsed_page.templates,
            ("秘境类型", "类型"),
            preferred_params=main_template,
            wikitext=parsed_page.wikitext,
        )
        return SecretItemRecord(
            title=self._resolve_record_title(parsed_page, ("秘境名称", "名称"), preferred_params=main_template),
            page_id=parsed_page.page_id,
            type=domain_type,
            description=self._resolve_value(
                parsed_page.templates,
                ("秘境介绍", "介绍", "描述"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            drops=self._extract_secret_item_drops(domain_type, drop_value),
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
        )

    def parse_book_page(self, payload: dict[str, Any]) -> BookRecord:
        """
        解析原神书籍页面。

        提取书籍的基本信息（名称、体裁、国家）和所有卷/章详情。

        卷信息从「书籍」模板的参数中提取，参数格式为：
        - 卷X名=X
        - 卷X获取地点=X
        - 卷X描述=X
        - 卷X内容=X

        参数
        ----
        payload : dict[str, Any]
            MediaWiki API 返回的页面 payload

        返回
        ----
        BookRecord
            包含书籍结构化数据的对象
        """
        title, page_id, wikitext = self.extract_page_metadata(payload)
        templates = self.parse_templates(wikitext)
        categories = self.parse_categories(wikitext)

        # 从模板中提取书籍基本信息
        genre = ""
        country = ""
        book_params: dict[str, str] = {}
        for name, items in templates.items():
            if "书籍" in name:
                for params in items:
                    book_params.update(params)
                    if not genre:
                        genre = params.get("体裁", params.get("类型", ""))
                    if not country:
                        raw_country = params.get("国家", params.get("地区", ""))
                        country = _parse_country_code(raw_country)

        # 从模板参数中提取卷信息
        volumes: list[BookVolume] = []
        # 收集所有卷相关的键
        volume_keys: dict[int, dict[str, str]] = {}
        for key, value in book_params.items():
            # 匹配 "卷X名", "卷X获取地点", "卷X描述", "卷X内容" 格式
            import re
            match = re.match(r"^卷(\d+)(名|获取地点|描述|内容)$", key)
            if match:
                vol_num = int(match.group(1))
                field = match.group(2)
                if vol_num not in volume_keys:
                    volume_keys[vol_num] = {}
                volume_keys[vol_num][field] = value

        # 按卷号排序构建 BookVolume
        for vol_num in sorted(volume_keys.keys()):
            fields = volume_keys[vol_num]
            # 将 <br> 替换为 \n（两个连续 <br> 替换为两个连续 \n）
            content = fields.get("内容", "")
            content = content.replace("<br>", "\n")
            volumes.append(BookVolume(
                name=fields.get("名", ""),
                description=fields.get("描述", ""),
                location=fields.get("获取地点", ""),
                content=content,
            ))

        return BookRecord(
            title=title,
            genre=genre,
            country=country,
            volumes=volumes,
            categories=categories,
            page_id=page_id,
        )

    def parse_character_story_page(
        self,
        payload: dict[str, Any],
        voice_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """提取角色页面中的故事相关结构化数据。"""
        record = self.parse_character_page(payload, voice_payload=voice_payload)
        return {
            "title": record.title,
            "page_id": record.page_id,
            "summary": record.summary,
            "god_eye_description": record.god_eye_description,
            "power_record": None if record.power_record is None else record.power_record.to_dict(),
            "story_records": [item.to_dict() for item in record.story_records],
            "adventure_notes": [item.to_dict() for item in record.adventure_notes],
            "character_introductions": [item.to_dict() for item in record.character_introductions],
            "story_sections": [item.to_dict() for item in record.story_sections],
            "voice_records": [item.to_dict() for item in record.voice_records],
        }

    def parse_character_voice_page(self, payload: dict[str, Any]) -> list[CharacterVoiceRecord]:
        """解析独立的角色语音页面。"""
        _, _, wikitext = self.extract_page_metadata(payload)
        return self._extract_voice_records_from_wikitext(wikitext)

    def _select_best_template(
        self,
        templates: dict[str, list[dict[str, str]]],
        keywords: Iterable[str],
    ) -> dict[str, str]:
        """从匹配关键词的模板中选择参数最完整的一个。"""
        candidates: list[tuple[int, dict[str, str]]] = []
        for name, items in templates.items():
            if self._is_character_template_name(name, keywords):
                for params in items:
                    candidates.append((len(params), params))
        if not candidates:
            return {}
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _select_best_template_by_fields(
        self,
        templates: dict[str, list[dict[str, str]]],
        field_groups: Sequence[Sequence[str]],
    ) -> dict[str, str]:
        """根据字段命中数选择最合适的模板。"""
        best_params: dict[str, str] = {}
        best_score = 0
        best_size = -1
        for items in templates.values():
            for params in items:
                score = sum(1 for aliases in field_groups if self._value_from_params(params, aliases, plain=False))
                if score > best_score or (score == best_score and len(params) > best_size):
                    best_score = score
                    best_size = len(params)
                    best_params = params
        return best_params

    def _collect_matching_templates(
        self,
        templates: dict[str, list[dict[str, str]]],
        keywords: Iterable[str],
    ) -> list[dict[str, str]]:
        """收集所有匹配关键词的模板参数。"""
        matched: list[dict[str, str]] = []
        for name, items in templates.items():
            if any(keyword in name for keyword in keywords):
                matched.extend(items)
        return matched

    def _extract_prefixed_list_field(self, attributes: dict[str, str], prefix: str) -> list[str]:
        """
        从属性字典中提取列表字段。

        例如 "突破武器材料1"、"突破武器材料2" 等会被收集为列表。

        参数
        ----
        attributes : dict[str, str]
            属性字典
        prefix : str
            字段前缀

        返回
        ----
        list[str]
            字段值列表
        """
        result: list[str] = []
        for key, value in attributes.items():
            if key.startswith(prefix):
                cleaned = self._clean_field_value(value)
                if cleaned:
                    result.append(cleaned)
        return self._dedupe(result)

    def _parse_obtaining_method(self, raw: str) -> str:
        """
        解析武器获取途径。

        - 若为"祈愿"或"限定祈愿"则填写"祈愿"或"限定祈愿"
        - 若描述为活动或任务获取的武器填写来自哪个活动/任务
        - 若描述为锻造之类字眼的武器则填写图纸如何获取

        参数
        ----
        raw : str
            原始获取途径字段

        返回
        ----
        str
            解析后的获取途径
        """
        raw = raw.strip()
        if not raw:
            return ""

        # 去除 HTML 注释
        raw = re.sub(r"<!--.*?-->", "", raw)

        # 处理 [[祈愿]] 或 [[限定祈愿]] 格式
        wish_match = re.search(r"\[\[(限定)?祈愿\]\]", raw)
        if wish_match:
            prefix = wish_match.group(1) or ""
            return f"{prefix}祈愿".strip()

        # 处理锻造类型：返回锻造图纸获取方式
        if "锻造" in raw:
            # 提取锻造图纸获取方式，格式如：完成「兰那罗的世界」后获得兑换物「关于你与兰那罗的故事」，接着与梦之树附近的兰随尼兑换锻造图纸
            # 简化处理：返回包含"图纸"之后的部分
            blueprint_match = re.search(r"兑换锻造图纸", raw)
            if blueprint_match:
                # 返回简化描述
                return "图纸兑换"
            return "锻造"

        # 处理活动/任务格式：[[活动名称]]：任务名称：获取方式
        mission_match = re.search(r"\[\[([^]]+)\]\]：([^：]+)：(.+)", raw)
        if mission_match:
            return f"{mission_match.group(1)}：{mission_match.group(3)}"

        # 返回原文（去除[[]])
        return re.sub(r"\[\[|\]\]", "", raw).strip()

    def _parse_forging_material(self, attributes: dict[str, str]) -> str | None:
        """
        解析锻造材料。

        参数
        ----
        attributes : dict[str, str]
            属性字典

        返回
        ----
        str | None
            锻造材料描述，若不可锻造则返回 None
        """
        can_forge = re.sub(r"<!--.*?-->", "", attributes.get("是否可锻造获取", "否"))
        if can_forge == "否":
            return None

        # 收集锻造材料
        materials: list[str] = []
        for i in range(1, 4):
            key = f"锻造材料{i}="
            for attr_key, attr_value in attributes.items():
                if attr_key.startswith(key) or attr_key == f"锻造材料{i}":
                    # 去除 HTML 注释
                    clean_value = re.sub(r"<!--.*?-->", "", attr_value).strip()
                    if clean_value:
                        materials.append(clean_value)
                    break
        return "、".join(materials) if materials else None

    def _parse_refining_material(self, attributes: dict[str, str]) -> str | None:
        """
        解析精炼材料。

        参数
        ----
        attributes : dict[str, str]
            属性字典

        返回
        ----
        str | None
            精炼材料描述，若不可精炼则返回 None
        """
        refining_key = "精炼材料="
        for key, value in attributes.items():
            if key.startswith(refining_key) or key == "精炼材料":
                # 去除 HTML 注释
                clean_value = re.sub(r"<!--.*?-->", "", value).strip()
                return clean_value if clean_value else None
        return None

    def _clean_br_tags(self, text: str) -> str:
        """
        清理文本中的<br>标签，替换为\n。

        连续的两个<br>替换为两个连续的\n。

        参数
        ----
        text : str
            原始文本

        返回
        ----
        str
            清理后的文本
        """
        if not text:
            return ""
        # 将 <br> 替换为 \n，然后将多个连续的 \n 合并（但保留两个）
        text = text.replace("<br>", "\n")
        # 保留最多两个连续的换行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_story_from_sections(self, sections: list[ParsedSection]) -> str:
        """
        从章节中提取故事内容。

        参数
        ----
        sections : list[ParsedSection]
            页面章节列表

        返回
        ----
        str
            故事内容
        """
        for section in sections:
            if "故事" in section.title:
                return section.text
        # 如果没有找到故事章节，返回空字符串
        return ""

    def _extract_set_effect_from_sections(self, sections: list[ParsedSection]) -> str:
        """
        从章节中提取套装效果描述。

        参数
        ----
        sections : list[ParsedSection]
            页面章节列表

        返回
        ----
        str
            套装效果描述
        """
        for section in sections:
            if "套装效果" in section.title or "效果" in section.title:
                return section.text
        return ""

    def _parse_artifact_obtaining_method(self, attributes: dict[str, str], templates: dict[str, list[dict[str, str]]] | None = None) -> str:
        """
        解析圣遗物获取方式。

        参数
        ----
        attributes : dict[str, str]
            属性字典
        templates : dict[str, list[dict[str, str]]] | None
            完整模板字典，用于直接从获取途径模板提取

        返回
        ----
        str
            解析后的获取方式
        """
        import re

        # 尝试从 获取途径= 字段解析
        # 格式：[[aaaaa]]：bbbbb：cccc -> 提取 aaaaa：cccc
        raw = attributes.get("获取途径", "")
        if raw:
            # 去除 HTML 注释
            raw = re.sub(r"<!--.*?-->", "", raw)
            # 先去除 [[ ]] 包裹的部分
            wiki_link_match = re.search(r"\[\[([^\]]+)\]\]", raw)
            if wiki_link_match:
                inner = wiki_link_match.group(1)
                # 查找 ]] 之后的内容
                after_bracket = raw[wiki_link_match.end():]
                # after_bracket 应该是：：cccc 格式
                # 提取冒号后的最后一部分
                after_match = re.match(r"：：(.+)", after_bracket)
                if after_match:
                    return f"{inner}：{after_match.group(1)}"
                # 如果没有 ：：格式，检查是否有冒号分隔
                after_clean = after_bracket.strip("：")
                if "：" in after_clean:
                    parts = after_clean.split("：")
                    if len(parts) >= 2:
                        return f"{inner}：{parts[-1]}".strip()
                elif after_clean:
                    return f"{inner}：{after_clean}".strip()

        # 尝试从 获取方式= 字段解析
        # 格式1：{{圣遗物套装/获取途径|NPC|（四星）击杀首领或周本BOSS}}
        # 格式2：{{圣遗物套装/获取途径|BOSS|部分首领敌人掉落}}
        # 格式3：{{圣遗物套装/获取途径|周本|[[北风的王狼]]及征讨领域概率掉落}}
        obtaining = attributes.get("获取方式", "")
        if obtaining:
            import re
            # 清理HTML注释
            obtaining = re.sub(r"<!--.*?-->", "", obtaining)
            descriptions = []
            # 按 }} 分割模板
            templates = obtaining.split("}}")
            for template in templates:
                template = template.strip()
                if not template.startswith("{{"):
                    continue
                # 提取 | 分隔的部分
                # 格式：{{圣遗物套装/获取途径|aaa|bbb}}
                match = re.search(r"\|\s*([^|]+?)\s*\|\s*(.+?)\s*$", template)
                if match:
                    bbb = match.group(2).strip()
                    # 清理 wiki 链接 [[...]] 或 [[...|...]]
                    bbb = re.sub(r"\[\[([^\]|]+?\|)?([^\]]+?)\]\]", r"\2", bbb)
                    # 如果包含 (x星) 或 （x星）格式，提取后面的部分
                    star_match = re.search(r"[（(][^）)]*[）)]\s*(.+)", bbb)
                    if star_match:
                        bbb = star_match.group(1).strip()
                    if bbb:
                        descriptions.append(bbb)
            if descriptions:
                return "、".join(descriptions)

        return obtaining

    def _resolve_value(
        self,
        templates: dict[str, list[dict[str, str]]],
        aliases: Sequence[str],
        *,
        preferred_params: dict[str, str] | None = None,
        wikitext: str | None = None,
    ) -> str:
        """提取清洗后的纯文本字段值。"""
        if preferred_params:
            value = self._value_from_params(preferred_params, aliases, plain=True)
            if value:
                return value
        for items in templates.values():
            for params in items:
                value = self._value_from_params(params, aliases, plain=True)
                if value:
                    return value
        if wikitext:
            raw_value = self._extract_param_from_wikitext(wikitext, aliases)
            if raw_value:
                return self._normalize_plain_text(raw_value)
        return ""

    def _resolve_raw_value(
        self,
        templates: dict[str, list[dict[str, str]]],
        aliases: Sequence[str],
        *,
        preferred_params: dict[str, str] | None = None,
        wikitext: str | None = None,
    ) -> str:
        """提取规范化后的原始模板字段值。"""
        if preferred_params:
            value = self._value_from_params(preferred_params, aliases, plain=False)
            if value:
                return value
        for items in templates.values():
            for params in items:
                value = self._value_from_params(params, aliases, plain=False)
                if value:
                    return value
        if wikitext:
            raw_value = self._extract_param_from_wikitext(wikitext, aliases)
            if raw_value:
                return self._normalize_text(raw_value)
        return ""

    def _resolve_highest_difficulty_drop_value(
        self,
        templates: dict[str, list[dict[str, str]]],
        *,
        preferred_params: dict[str, str] | None = None,
        wikitext: str | None = None,
    ) -> str:
        """Resolve the highest available non-empty 难度N掉落 field."""
        for level in range(6, 0, -1):
            value = self._resolve_raw_value(
                templates,
                (f"难度{level}掉落",),
                preferred_params=preferred_params,
                wikitext=wikitext,
            )
            if value:
                return value
        return ""

    def _value_from_params(
        self,
        params: dict[str, str],
        aliases: Sequence[str],
        *,
        plain: bool,
    ) -> str:
        """从参数字典中读取第一个非空匹配字段。"""
        for alias in aliases:
            if alias not in params:
                continue
            raw_value = params[alias]
            value = self._normalize_plain_text(raw_value) if plain else self._normalize_text(raw_value)
            if value and value != "[[]]":
                return value
        return ""

    def _normalize_plain_text(self, value: str) -> str:
        """去除 wikitext 标记并保留文本换行。"""
        normalized = self._normalize_text(value)
        normalized = _ICON_TEMPLATE_PATTERN.sub(
            lambda match: (match.group(2) or match.group(1) or "").strip(),
            normalized,
        )
        normalized = self._strip_plain_markup(normalized)
        plain_text = mwparserfromhell.parse(normalized).strip_code()
        return self._normalize_text(str(plain_text))

    def _strip_plain_markup(self, value: str) -> str:
        """移除不应出现在纯文本字段中的图片、HTML 与 tabber 标记。"""
        cleaned = _FILE_LINK_PATTERN.sub("", value)
        cleaned = _HTML_TAG_PATTERN.sub("", cleaned)
        cleaned = _TABBER_SEPARATOR_PATTERN.sub("", cleaned)
        cleaned = _TABBER_LABEL_PATTERN.sub("", cleaned)
        return cleaned

    def _find_section_text(self, sections: Sequence[ParsedSection], titles: Sequence[str]) -> str:
        """按章节标题查找正文文本。"""
        wanted = {title.strip() for title in titles}
        for index, section in enumerate(sections):
            if section.title.strip() not in wanted:
                continue
            text = self._normalize_text(section.text)
            if text:
                return text
            if index + 1 < len(sections):
                next_text = self._normalize_text(sections[index + 1].text)
                if next_text:
                    return next_text
        return ""

    def _extract_labeled_value(self, text: str, labels: Sequence[str]) -> str:
        """从章节文本里提取形如“标签: 值”的行。"""
        normalized = self._normalize_text(text)
        if not normalized:
            return ""
        for line in normalized.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            for label in labels:
                if not stripped.startswith(label):
                    continue
                value = stripped[len(label):].lstrip("：: \t")
                if value:
                    return value
        return ""

    def _extract_first_non_empty_line(self, text: str) -> str:
        """返回文本中的第一条非空行。"""
        normalized = self._normalize_text(text)
        for line in normalized.splitlines():
            line = line.strip()
            if line:
                return line
        return ""

    def _extract_secret_item_drops(self, domain_type: str, value: str) -> dict[str, str]:
        """按秘境类型提取结构化掉落字段。"""
        normalized_type = self._normalize_plain_text(domain_type)
        if "圣遗物秘境" in normalized_type:
            artifact_names = self._extract_artifact_drop_names(value)
            return {
                "圣遗物1": artifact_names[-2] if len(artifact_names) >= 2 else "",
                "圣遗物2": artifact_names[-1] if artifact_names else "",
            }
        if "BOSS秘境" in normalized_type:
            boss_materials = self._extract_ordered_drop_names(value)[:3]
            result = {
                "材料1": "",
                "材料2": "",
                "材料3": "",
            }
            for index, material_name in enumerate(boss_materials, start=1):
                result[f"材料{index}"] = material_name
            return result
        if "天赋技能材料秘境" in normalized_type:
            return self._extract_grouped_drop_map(value, prefix="天赋技能材料", count=3)
        if "武器突破材料秘境" in normalized_type:
            return self._extract_grouped_drop_map(value, prefix="武器突破材料", count=3)
        fallback_names = self._extract_artifact_drop_names(value)
        return {
            f"掉落{index}": item_name
            for index, item_name in enumerate(fallback_names, start=1)
        }

    def _extract_artifact_drop_names(self, value: str) -> list[str]:
        """从圣遗物秘境的掉落字段中提取最后两个套装名。"""
        if not value:
            return []
        code = mwparserfromhell.parse(self._normalize_text(value))
        icon_titles: list[str] = []
        for template in code.filter_templates(recursive=True):
            if str(template.name).strip() != "图标":
                continue
            first = self._normalize_plain_text(template.get(1).value.strip()) if template.has(1) else ""
            second = self._normalize_plain_text(template.get(2).value.strip()) if template.has(2) else ""
            if first == "圣遗物" and second:
                icon_titles.append(second)
        unique_icon_titles = self._unique_preserve_order(icon_titles)
        if len(unique_icon_titles) >= 2:
            return unique_icon_titles[-2:]
        link_titles: list[str] = []
        for wikilink in code.filter_wikilinks(recursive=True):
            title = self._normalize_plain_text(str(wikilink.title))
            if not title or title.startswith(_FILE_LINK_PREFIXES):
                continue
            link_titles.append(title)
        unique_titles = self._unique_preserve_order(link_titles)
        if len(unique_titles) >= 2:
            return unique_titles[-2:]
        plain_text = self._normalize_plain_text(value)
        parts = [
            chunk.strip(" -*\t")
            for chunk in re.split(r"[\n,，、/]+", plain_text)
            if chunk.strip(" -*\t")
        ]
        unique_parts = self._unique_preserve_order(parts)
        return unique_parts[-2:]

    def _extract_ordered_drop_names(self, value: str) -> list[str]:
        """Extract ordered item names from a raw domain drop field."""
        if not value:
            return []
        code = mwparserfromhell.parse(self._normalize_text(value))
        icon_titles: list[str] = []
        for template in code.filter_templates(recursive=True):
            if str(template.name).strip() != "图标":
                continue
            first = self._normalize_plain_text(template.get(1).value.strip()) if template.has(1) else ""
            second = self._normalize_plain_text(template.get(2).value.strip()) if template.has(2) else ""
            title = second or first
            if title:
                icon_titles.append(title)
        unique_icon_titles = self._unique_preserve_order(icon_titles)
        if unique_icon_titles:
            return unique_icon_titles

        link_titles: list[str] = []
        for wikilink in code.filter_wikilinks(recursive=True):
            title = self._normalize_plain_text(str(wikilink.title))
            if not title or title.startswith(_FILE_LINK_PREFIXES):
                continue
            link_titles.append(title)
        unique_titles = self._unique_preserve_order(link_titles)
        if unique_titles:
            return unique_titles

        plain_text = self._normalize_plain_text(value)
        parts = [
            chunk.strip(" -*\t")
            for chunk in re.split(r"[\n,，、/]+", plain_text)
            if chunk.strip(" -*\t")
        ]
        return self._unique_preserve_order(parts)

    def _extract_grouped_drop_map(self, value: str, *, prefix: str, count: int) -> dict[str, str]:
        """从按组展示的掉落字段中提取最后 N 组材料名。"""
        groups = self._extract_grouped_drop_values(value)
        selected_groups = groups[-count:] if len(groups) >= count else groups
        result = {
            f"{prefix}{index}": ""
            for index in range(1, count + 1)
        }
        for index, group_value in enumerate(selected_groups, start=1):
            result[f"{prefix}{index}"] = group_value
        return result

    def _extract_grouped_drop_values(self, value: str) -> list[str]:
        """提取以 <hr> 等分隔的掉落组文本。"""
        if not value:
            return []
        normalized = self._normalize_text(value)
        segments = [
            segment.strip()
            for segment in _HORIZONTAL_RULE_PATTERN.split(normalized)
            if segment.strip()
        ]
        groups: list[str] = []
        for segment in segments:
            code = mwparserfromhell.parse(segment)
            titles: list[str] = []
            for template in code.filter_templates(recursive=True):
                if str(template.name).strip() != "图标":
                    continue
                first = self._normalize_plain_text(template.get(1).value.strip()) if template.has(1) else ""
                second = self._normalize_plain_text(template.get(2).value.strip()) if template.has(2) else ""
                if first == "圣遗物":
                    continue
                title = second or first
                if title:
                    titles.append(title)
            unique_titles = self._unique_preserve_order(titles)
            if unique_titles:
                groups.append("、".join(unique_titles))
                continue
            plain_text = self._normalize_plain_text(segment)
            parts = [
                chunk.strip(" -*\t")
                for chunk in re.split(r"[\n,，、/]+", plain_text)
                if chunk.strip(" -*\t")
            ]
            unique_parts = self._unique_preserve_order(parts)
            if unique_parts:
                groups.append("、".join(unique_parts))
        return groups

    def _unique_preserve_order(self, values: Sequence[str]) -> list[str]:
        """按原顺序去重。"""
        unique_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            unique_values.append(value)
        return unique_values

    def _coalesce(self, *values: str) -> str:
        """返回第一个非空字符串。"""
        for value in values:
            if value:
                return value
        return ""

    def _resolve_record_title(
        self,
        parsed_page: ParsedPage,
        aliases: Sequence[str],
        *,
        preferred_params: dict[str, str] | None = None,
    ) -> str:
        """优先使用模板中的名称字段，回退到页面标题。"""
        return self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                aliases,
                preferred_params=preferred_params,
                wikitext=parsed_page.wikitext,
            ),
            parsed_page.title,
        )

    def _extract_param_from_wikitext(self, wikitext: str, aliases: Sequence[str]) -> str:
        """在原始 wikitext 中手工提取复杂模板参数。"""
        for alias in aliases:
            pattern = re.compile(rf"(?m)^\|{re.escape(alias)}=")
            match = pattern.search(wikitext)
            if not match:
                continue
            start = match.end()
            template_depth = 0
            link_depth = 0
            index = start
            while index < len(wikitext):
                if wikitext.startswith("{{", index):
                    template_depth += 1
                    index += 2
                    continue
                if wikitext.startswith("}}", index):
                    if template_depth == 0:
                        break
                    template_depth -= 1
                    index += 2
                    continue
                if wikitext.startswith("[[", index):
                    link_depth += 1
                    index += 2
                    continue
                if wikitext.startswith("]]", index):
                    if link_depth > 0:
                        link_depth -= 1
                    index += 2
                    continue
                if (
                    wikitext[index] == "\n"
                    and template_depth == 0
                    and link_depth == 0
                    and (
                        wikitext.startswith("\n|", index)
                        or wikitext.startswith("\n}}", index)
                    )
                ):
                    break
                index += 1
            value = wikitext[start:index].strip()
            if value:
                return value
        return ""

    def _extract_plain_param_from_wikitext(self, wikitext: str, aliases: Sequence[str]) -> str:
        """提取并清洗原始 wikitext 参数值。"""
        value = self._extract_param_from_wikitext(wikitext, aliases)
        if not value:
            return ""
        return self._normalize_plain_text(value)

    def _extract_payload_categories(self, payload: dict[str, Any]) -> list[str]:
        """从 API payload 中提取分类。"""
        pages = payload.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        categories = page.get("categories", [])
        result = []
        for item in categories:
            title = item.get("title", "")
            if not title:
                continue
            if ":" in title:
                title = title.split(":", 1)[1]
            title = title.strip()
            if title:
                result.append(title)
        return sorted(set(result))

    def _is_character_template_name(self, name: str, keywords: Iterable[str]) -> bool:
        """过滤角色基础信息模板，避免误选故事/语音等模板。"""
        if not any(keyword in name for keyword in keywords):
            return False
        return not any(excluded in name for excluded in _CHARACTER_TEMPLATE_EXCLUDES)

    def _iter_template_params(
        self,
        templates: dict[str, list[dict[str, str]]],
        keywords: Iterable[str] | None = None,
    ) -> Iterable[tuple[str, dict[str, str]]]:
        """按模板遍历参数字典。"""
        for name, items in templates.items():
            if keywords is not None and not any(keyword in name for keyword in keywords):
                continue
            for params in items:
                yield name, params

    def _extract_text_field(
        self,
        attributes: dict[str, str],
        keys: Iterable[str],
        *,
        context: str = "generic",
        fallback: str = "",
    ) -> str:
        """按候选键提取单个文本字段。"""
        for key in keys:
            raw = attributes.get(key, "")
            cleaned = self._clean_field_value(raw, context=context)
            if cleaned:
                return cleaned
        return fallback

    def _extract_list_field(
        self,
        attributes: dict[str, str],
        keys: Iterable[str],
        *,
        context: str = "generic",
    ) -> list[str]:
        """按候选键提取多值字段。"""
        values: list[str] = []
        for key in keys:
            raw = attributes.get(key, "")
            if not raw:
                continue
            for chunk in self._split_raw_items(raw):
                cleaned = self._clean_field_value(chunk, context=context)
                if cleaned:
                    values.append(cleaned)
        return self._dedupe(values)

    def _extract_nicknames(self, attributes: dict[str, str]) -> list[str]:
        """提取昵称/外号字段。"""
        values: list[str] = []
        for key in _NICKNAME_KEYS:
            raw = attributes.get(key, "")
            if not raw:
                continue
            for chunk in self._split_raw_items(raw):
                cleaned = self._strip_quotes(self._clean_field_value(chunk, context="nickname"))
                if cleaned:
                    values.append(cleaned)
        return self._dedupe(values)

    def _build_talent_record(self, params: dict[str, str]) -> TalentRecord:
        """构建增强版天赋记录。"""
        return TalentRecord(
            name=self._first_value(params, ("名称", "天赋名称", "技能名称")),
            description=self._first_value(params, ("描述", "效果", "说明")),
            category=self._first_value(params, ("类别", "类型", "天赋类型")),
            element=self._first_value(params, ("元素", "元素类型")),
            raw=params,
        )

    def _build_constellation_record(self, params: dict[str, str]) -> ConstellationRecord:
        """构建增强版命座记录。"""
        return ConstellationRecord(
            name=self._first_value(params, ("名称", "命座名称")),
            effect=self._first_value(params, ("效果",)),
            description=self._first_value(params, ("描述", "说明")),
            raw=params,
        )

    def _extract_story_records(self, templates: dict[str, list[dict[str, str]]]) -> list[CharacterStoryRecord]:
        """提取角色详细与角色故事条目。"""
        records: list[CharacterStoryRecord] = []
        seen: set[tuple[str, str]] = set()
        for _, params in self._iter_template_params(templates, _STORY_TEMPLATE_KEYWORDS):
            for name, raw in params.items():
                if name != "角色详细" and not re.fullmatch(r"角色故事\d+", name):
                    continue
                content = self._clean_field_value(raw, context="story")
                if not content or (name, content) in seen:
                    continue
                seen.add((name, content))
                records.append(CharacterStoryRecord(title=name, content=content, group="角色故事"))
        records.sort(key=self._story_sort_key)
        return records

    def _extract_adventure_notes(self, templates: dict[str, list[dict[str, str]]]) -> list[AdventureNotesRecord]:
        """提取冒险笔记条目。"""
        records: list[AdventureNotesRecord] = []
        seen: set[tuple[str, str]] = set()
        for _, params in self._iter_template_params(templates, _STORY_TEMPLATE_KEYWORDS):
            note_titles: dict[str, str] = {}
            note_contents: dict[str, str] = {}
            for name, raw in params.items():
                if name.startswith("冒险笔记名称"):
                    suffix = name.removeprefix("冒险笔记名称") or "1"
                    note_titles[suffix] = self._clean_field_value(raw)
                    continue
                if name == "冒险笔记":
                    note_contents["1"] = raw
                    continue
                if name.startswith("冒险笔记内容"):
                    suffix = name.removeprefix("冒险笔记内容") or "1"
                    note_contents[suffix] = raw
                    continue
                if name.startswith("冒险笔记") and name != "冒险笔记名称":
                    suffix = name.removeprefix("冒险笔记") or "1"
                    note_contents[suffix] = raw
            for suffix, title in note_titles.items():
                content = self._clean_field_value(note_contents.get(suffix, ""), context="story")
                if not title or not content or (title, content) in seen:
                    continue
                seen.add((title, content))
                records.append(AdventureNotesRecord(title=title, content=content))
        return records

    def _extract_character_introductions(
        self,
        templates: dict[str, list[dict[str, str]]],
    ) -> list[CharacterStoryRecord]:
        """提取壹·人物下的角色介绍切换板内容。"""
        raw = self._find_first_param_value(templates, _INTRO_SECTION_KEYS)
        if not raw:
            return []
        records: list[CharacterStoryRecord] = []
        for index, content in enumerate(_SWITCH_PANEL_CONTENT_PATTERN.findall(raw), start=1):
            cleaned = self._clean_field_value(content, context="story")
            if cleaned:
                records.append(
                    CharacterStoryRecord(
                        title=f"角色介绍{index}",
                        content=cleaned,
                        group="壹·人物",
                    )
                )
        return records

    def _extract_story_sections(self, templates: dict[str, list[dict[str, str]]]) -> list[CharacterStoryRecord]:
        """提取贰·故事下带标题的切换板内容。"""
        raw = self._find_first_param_value(templates, _STORY_SECTION_KEYS)
        if not raw:
            return []
        return self._extract_switch_panel_story_pairs(raw)

    def _extract_character_introductions_from_wikitext(self, wikitext: str) -> list[CharacterStoryRecord]:
        """从页面章节 wikitext 中提取壹·人物介绍。"""
        raw = self._extract_named_section_wikitext(wikitext, "壹·人物")
        if not raw:
            return []
        records: list[CharacterStoryRecord] = []
        for index, content in enumerate(_SWITCH_PANEL_CONTENT_PATTERN.findall(raw), start=1):
            cleaned = self._clean_field_value(content, context="story")
            if cleaned:
                records.append(
                    CharacterStoryRecord(
                        title=f"角色介绍{index}",
                        content=cleaned,
                        group="壹·人物",
                    )
                )
        if records:
            return records
        cleaned = self._clean_field_value(raw, context="story")
        if not cleaned:
            return []
        return [CharacterStoryRecord(title="角色介绍1", content=cleaned, group="壹·人物")]

    def _extract_story_sections_from_wikitext(self, wikitext: str) -> list[CharacterStoryRecord]:
        """从页面章节 wikitext 中提取贰·故事内容。"""
        raw = self._extract_named_section_wikitext(wikitext, "贰·故事")
        if not raw:
            return []
        records = self._extract_switch_panel_story_pairs(raw)
        if records:
            return records
        cleaned = self._clean_field_value(raw, context="story")
        if not cleaned:
            return []
        return [CharacterStoryRecord(title="贰·故事", content=cleaned, group="贰·故事")]

    def _extract_switch_panel_story_pairs(self, raw: str) -> list[CharacterStoryRecord]:
        """按顺序配对切换板标题和内容。"""
        records: list[CharacterStoryRecord] = []
        titles = _SWITCH_PANEL_TITLE_PATTERN.findall(raw)
        contents = _SWITCH_PANEL_CONTENT_PATTERN.findall(raw)
        for title, content in zip(titles, contents, strict=False):
            cleaned_title = self._clean_field_value(title)
            cleaned_content = self._clean_field_value(content, context="story")
            if cleaned_title and cleaned_content:
                records.append(
                    CharacterStoryRecord(
                        title=cleaned_title,
                        content=cleaned_content,
                        group="贰·故事",
                    )
                )
        return records

    def _extract_voice_records(self, templates: dict[str, list[dict[str, str]]]) -> list[CharacterVoiceRecord]:
        """提取 display:block 的角色语音内容。"""
        raw = self._find_first_param_value(templates, _VOICE_SECTION_KEYS)
        if not raw:
            return self._extract_direct_voice_records(templates)
        return self._extract_voice_records_from_wikitext(raw)

    def _extract_direct_voice_records(
        self,
        templates: dict[str, list[dict[str, str]]],
    ) -> list[CharacterVoiceRecord]:
        """回退提取直接模板化的语音内容。"""
        records: list[CharacterVoiceRecord] = []
        seen: set[tuple[str, str]] = set()
        for _, params in self._iter_template_params(templates):
            title = self._clean_field_value(params.get("语音类型", ""))
            content = self._clean_field_value(params.get("语音内容", ""), context="voice")
            if not title or not content or (title, content) in seen:
                continue
            seen.add((title, content))
            records.append(CharacterVoiceRecord(title=title, content=content))
        return records

    def _extract_voice_records_from_wikitext(self, wikitext: str) -> list[CharacterVoiceRecord]:
        """从语音页或语音片段 wikitext 中提取 display:block 中文语音。"""
        records: list[CharacterVoiceRecord] = []
        seen: set[tuple[str, str]] = set()
        for block in _VOICE_BLOCK_PATTERN.findall(wikitext):
            code = mwparserfromhell.parse(block)
            for template in code.filter_templates(recursive=True):
                params = {
                    str(param.name).strip(): str(param.value).strip()
                    for param in template.params
                }
                title = self._clean_field_value(params.get("语音类型", ""))
                content = self._clean_field_value(params.get("语音内容", ""), context="voice")
                if not title or not content or (title, content) in seen:
                    continue
                seen.add((title, content))
                records.append(CharacterVoiceRecord(title=title, content=content))
        return records

    def _extract_power_record(
        self,
        templates: dict[str, list[dict[str, str]]],
        title: str,
    ) -> CharacterStoryRecord | None:
        """提取权能描述内容。"""
        for _, params in self._iter_template_params(templates, _STORY_TEMPLATE_KEYWORDS):
            for key in ("神之眼", "神之心", "其他故事", "其他"):
                content = self._clean_field_value(params.get(key, ""), context="story")
                if content:
                    return CharacterStoryRecord(title=title or key, content=content, group="权能")
        return None

    def _find_first_param_value(
        self,
        templates: dict[str, list[dict[str, str]]],
        keys: Iterable[str],
    ) -> str:
        """在所有模板参数中查找首个匹配的值。"""
        for _, params in self._iter_template_params(templates):
            for key in keys:
                value = params.get(key, "")
                if value:
                    return value
        return ""

    def _extract_named_section_wikitext(self, wikitext: str, title: str) -> str:
        """提取指定标题对应的原始章节 wikitext。"""
        pattern = re.compile(
            rf"^====\s*{re.escape(title)}\s*====\s*$\n?(.*?)(?=^====\s*[^=].*?====\s*$|^===\s*[^=].*?===\s*$|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(wikitext)
        if not match:
            return ""
        return match.group(1).strip()

    def _first_value(self, params: dict[str, str], keys: Iterable[str]) -> str:
        """从参数字典中按候选键提取文本。"""
        for key in keys:
            cleaned = self._clean_field_value(params.get(key, ""))
            if cleaned:
                return cleaned
        return ""

    def _split_raw_items(self, raw: str) -> list[str]:
        """按常见列表分隔符拆分原始字段值。"""
        normalized = self._normalize_line_breaks(raw)
        return [chunk.strip() for chunk in _LIST_SPLIT_PATTERN.split(normalized) if chunk.strip()]

    def _clean_field_value(self, raw: str, *, context: str = "generic") -> str:
        """将模板参数值清洗为适合输出的纯文本。"""
        if not raw:
            return ""
        text = self._normalize_line_breaks(raw)
        text = _FILE_LINK_PATTERN.sub("", text)
        text = self._replace_phonetic_templates(text, context)
        text = self._replace_blackout_templates(text, context)
        text = text.replace("&nbsp;", " ")
        text = mwparserfromhell.parse(text).strip_code().strip()
        text = self._strip_quotes(self._normalize_text(text))
        return text

    def _replace_phonetic_templates(self, text: str, context: str) -> str:
        """替换注音模板。"""
        def replacer(match: re.Match[str]) -> str:
            display = self._strip_quotes(match.group(1).strip())
            reading = self._strip_quotes(match.group(2).strip())
            return reading if context == "nickname" else display

        return _PHONETIC_TEMPLATE_PATTERN.sub(replacer, text)

    def _replace_blackout_templates(self, text: str, context: str) -> str:
        """替换黑幕模板。"""
        def replacer(match: re.Match[str]) -> str:
            inner = match.group(1).strip()
            deleted = self._extract_deleted_text(inner)
            if deleted:
                return "" if context == "nickname" else deleted
            if context == "nickname":
                return self._extract_parenthesized_text(inner)
            return inner

        return _BLACKOUT_TEMPLATE_PATTERN.sub(replacer, text)

    def _extract_deleted_text(self, text: str) -> str:
        """提取 <del> 标签包裹的文本。"""
        match = _DEL_TAG_PATTERN.search(text)
        if not match:
            return ""
        return self._normalize_text(mwparserfromhell.parse(match.group(1)).strip_code().strip())

    def _extract_parenthesized_text(self, text: str) -> str:
        """提取括号中的文本。"""
        match = _PARENTHESIS_PATTERN.search(text)
        if not match:
            return ""
        return self._normalize_text(match.group(1).strip())

    def _normalize_line_breaks(self, text: str) -> str:
        """将 <br> 标签替换为换行符。"""
        return _BR_TAG_PATTERN.sub("\n", text).replace("\r\n", "\n").replace("\r", "\n")

    def _normalize_text(self, text: str) -> str:
        """规范化文本中的转义、空白与换行。"""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\\|", "|").replace("{{!}}", "|")
        normalized = normalized.replace("&nbsp;", " ").replace("\xa0", " ")
        normalized = _COMMENT_PATTERN.sub("", normalized)
        normalized = _BREAK_WITH_LINE_END_PATTERN.sub(r"\1", normalized)
        normalized = self._normalize_line_breaks(normalized)
        normalized = "\n".join(line.strip() for line in normalized.split("\n"))
        normalized = re.sub(r"[ \t]+\n", "\n", normalized)
        normalized = re.sub(r"\n[ \t]+", "\n", normalized)
        normalized = re.sub(r"[ \t]{2,}", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    def _strip_quotes(self, text: str) -> str:
        """移除包裹文本的常见引号。"""
        return text.strip().strip("「」\"'")

    def _dedupe(self, values: Iterable[str]) -> list[str]:
        """保持顺序去重。"""
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _story_sort_key(self, record: CharacterStoryRecord) -> tuple[int, int | str]:
        """对角色详细和角色故事进行稳定排序。"""
        if record.title == "角色详细":
            return (0, 0)
        match = re.fullmatch(r"角色故事(\d+)", record.title)
        if match:
            return (1, int(match.group(1)))
        return (2, record.title)
