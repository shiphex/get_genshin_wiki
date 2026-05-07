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
from .models import CharacterRecord, MonsterRecord, ParsedPage, ParsedSection

# 分类链接匹配正则：[[Category:xxx]] 或 [[分类:xxx]]
_CATEGORY_PATTERN = re.compile(r"\[\[\s*(?:Category|分类)\s*:\s*([^\]|]+)")
# 分类链接本身（用于从正文中移除分类标记）
_CATEGORY_LINK_PATTERN = re.compile(r"\[\[\s*(?:Category|分类)\s*:[^\]]+\]\]")

# 角色属性模板关键词（用于识别角色信息模板）
_CHARACTER_TEMPLATE_KEYWORDS = ("角色属性", "角色信息", "角色资料", "角色")
# 天赋模板关键词
_TALENT_TEMPLATE_KEYWORDS = ("天赋", "技能")
# 命座模板关键词
_CONSTELLATION_TEMPLATE_KEYWORDS = ("命之座", "命座")


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
            # strip_code() 去除 wikitext 标记，得到纯文本
            text = section.strip_code().strip()
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
        return ParsedPage(
            title=title,
            page_id=page_id,
            summary=summary,
            categories=self.parse_categories(wikitext),
            sections=sections,
            templates=self.parse_templates(wikitext),
            wikitext=wikitext,
        )

    def parse_character_page(self, payload: dict[str, Any]) -> CharacterRecord:
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
        # 从模板中筛选角色属性（参数最多的最完整）
        attributes = self._select_best_template(parsed_page.templates, _CHARACTER_TEMPLATE_KEYWORDS)
        # 收集所有匹配天赋关键词的模板
        talents = self._collect_matching_templates(parsed_page.templates, _TALENT_TEMPLATE_KEYWORDS)
        # 收集所有匹配命座关键词的模板
        constellations = self._collect_matching_templates(parsed_page.templates, _CONSTELLATION_TEMPLATE_KEYWORDS)
        return CharacterRecord(
            title=parsed_page.title,
            page_id=parsed_page.page_id,
            summary=parsed_page.summary,
            attributes=attributes,
            talents=talents,
            constellations=constellations,
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
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

    def _select_best_template(
        self,
        templates: dict[str, list[dict[str, str]]],
        keywords: Iterable[str],
    ) -> dict[str, str]:
        """
        从匹配关键词的模板中选择参数最完整的一个。

        原理：角色属性模板参数越多，信息越完整，
        因此选择参数数量最多的模板作为角色属性来源。

        参数
        ----
        templates : dict[str, list[dict[str, str]]]
            parse_templates 返回的模板字典
        keywords : Iterable[str]
            匹配的关键词元组

        返回
        ----
        dict[str, str]
            参数最多的匹配模板的参数字典
        """
        candidates: list[tuple[int, dict[str, str]]] = []
        for name, items in templates.items():
            if any(keyword in name for keyword in keywords):
                for params in items:
                    # 按参数数量排序
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
        """
        收集所有匹配关键词的模板参数。

        参数
        ----
        templates : dict[str, list[dict[str, str]]]
            parse_templates 返回的模板字典
        keywords : Iterable[str]
            匹配的关键词元组

        返回
        ----
        list[dict[str, str]]
            所有匹配模板的参数列表
        """
        matched: list[dict[str, str]] = []
        for name, items in templates.items():
            if any(keyword in name for keyword in keywords):
                matched.extend(items)
        return matched
