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
from typing import Any, Iterable

import mwparserfromhell

from .exceptions import ParsingError
from .models import (
    AdventureNotesRecord,
    CharacterRecord,
    CharacterStoryRecord,
    CharacterVoiceRecord,
    ConstellationRecord,
    ParsedPage,
    ParsedSection,
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
                sections.append(ParsedSection(title=title, text=text))
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
        """规范化文本中的空白与换行。"""
        normalized = self._normalize_line_breaks(text)
        normalized = re.sub(r"[ \t]+\n", "\n", normalized)
        normalized = re.sub(r"\n[ \t]+", "\n", normalized)
        normalized = re.sub(r"[ \t]{2,}", " ", normalized)
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
