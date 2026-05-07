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
from .models import BookRecord, BookVolume, CharacterRecord, ParsedPage, ParsedSection

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
