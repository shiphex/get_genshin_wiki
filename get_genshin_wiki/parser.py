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
    ArtifactPieceRecord,
    ArtifactSetRecord,
    CharacterRecord,
    ParsedPage,
    ParsedSection,
    WeaponRecord,
)

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
        ascension_weapon_materials = self._extract_list_field(attributes, "突破武器材料")
        ascension_premium_materials = self._extract_list_field(attributes, "突破高级材料")
        ascension_common_materials = self._extract_list_field(attributes, "突破普通材料")

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

    def _extract_list_field(self, attributes: dict[str, str], prefix: str) -> list[str]:
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
        result = []
        for key, value in attributes.items():
            if key.startswith(prefix):
                result.append(value)
        return result

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

        import re

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
        import re
        can_forge = re.sub(r"<!--.*?-->", "", attributes.get("是否可锻造获取", "否"))
        if can_forge == "否":
            return None

        # 收集锻造材料
        import re
        materials = []
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
        import re
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
