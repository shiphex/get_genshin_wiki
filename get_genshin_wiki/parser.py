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
from typing import Any, Iterable, Mapping

try:
    import mwparserfromhell
except ModuleNotFoundError:
    class _MiniTemplateParam:
        def __init__(self, name: str, value: str) -> None:
            self.name = name
            self.value = value


    class _MiniTemplate:
        def __init__(self, raw: str) -> None:
            self._raw = raw
            inner = raw[2:-2]
            parts = _mini_split_top_level(inner, "|")
            self.name = parts[0].strip() if parts else ""
            self.params: list[_MiniTemplateParam] = []
            positional_index = 1
            for part in parts[1:]:
                key, value = _mini_split_param(part)
                if key is None:
                    key = str(positional_index)
                    positional_index += 1
                self.params.append(_MiniTemplateParam(key.strip(), value.strip()))

        def has(self, key: int | str) -> bool:
            key_text = str(key).strip()
            return any(str(param.name).strip() == key_text for param in self.params)

        def get(self, key: int | str) -> _MiniTemplateParam:
            key_text = str(key).strip()
            for param in self.params:
                if str(param.name).strip() == key_text:
                    return param
            raise ValueError(f"template parameter not found: {key}")

        def __str__(self) -> str:
            return self._raw


    class _MiniHeading:
        def __init__(self, title: str) -> None:
            self.title = title


    class _MiniWikiLink:
        def __init__(self, raw: str) -> None:
            parts = _mini_split_top_level(raw, "|")
            self.title = parts[0].strip() if parts else ""


    class _MiniSection:
        def __init__(self, text: str) -> None:
            self._text = text

        def filter_headings(self) -> list[_MiniHeading]:
            first_line = self._text.splitlines()[0] if self._text.splitlines() else ""
            match = re.match(r"^(={2,6})\s*(.*?)\s*\1\s*$", first_line)
            if not match:
                return []
            return [_MiniHeading(match.group(2).strip())]

        def __str__(self) -> str:
            return self._text


    def _mini_protect_raw_blocks(text: str) -> tuple[str, list[str]]:
        blocks: list[str] = []

        def replacer(match: re.Match[str]) -> str:
            blocks.append(match.group(0))
            return f"\x00RAWBLOCK{len(blocks) - 1}\x00"

        protected = re.sub(r"(?is)<tabber\b[^>]*>.*?</tabber>", replacer, text)
        return protected, blocks


    def _mini_restore_raw_blocks(text: str, blocks: list[str]) -> str:
        restored = text
        for index, block in enumerate(blocks):
            restored = restored.replace(f"\x00RAWBLOCK{index}\x00", block)
        return restored


    def _mini_split_top_level(text: str, separator: str) -> list[str]:
        protected, blocks = _mini_protect_raw_blocks(text)
        parts: list[str] = []
        current: list[str] = []
        template_depth = 0
        link_depth = 0
        index = 0
        while index < len(protected):
            if protected.startswith("{{", index):
                template_depth += 1
                current.append("{{")
                index += 2
                continue
            if protected.startswith("}}", index) and template_depth > 0:
                template_depth -= 1
                current.append("}}")
                index += 2
                continue
            if protected.startswith("[[", index):
                link_depth += 1
                current.append("[[")
                index += 2
                continue
            if protected.startswith("]]", index) and link_depth > 0:
                link_depth -= 1
                current.append("]]")
                index += 2
                continue
            if protected[index] == separator and template_depth == 0 and link_depth == 0:
                parts.append(_mini_restore_raw_blocks("".join(current), blocks))
                current = []
                index += 1
                continue
            current.append(protected[index])
            index += 1
        parts.append(_mini_restore_raw_blocks("".join(current), blocks))
        return parts


    def _mini_split_param(text: str) -> tuple[str | None, str]:
        protected, blocks = _mini_protect_raw_blocks(text)
        template_depth = 0
        link_depth = 0
        index = 0
        while index < len(protected):
            if protected.startswith("{{", index):
                template_depth += 1
                index += 2
                continue
            if protected.startswith("}}", index) and template_depth > 0:
                template_depth -= 1
                index += 2
                continue
            if protected.startswith("[[", index):
                link_depth += 1
                index += 2
                continue
            if protected.startswith("]]", index) and link_depth > 0:
                link_depth -= 1
                index += 2
                continue
            if protected[index] == "=" and template_depth == 0 and link_depth == 0:
                return (
                    _mini_restore_raw_blocks(protected[:index], blocks),
                    _mini_restore_raw_blocks(protected[index + 1 :], blocks),
                )
            index += 1
        return None, text


    def _mini_find_balanced_spans(text: str, open_token: str, close_token: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        stack: list[int] = []
        open_size = len(open_token)
        close_size = len(close_token)
        index = 0
        limit = len(text)
        while index < limit:
            if text.startswith(open_token, index):
                stack.append(index)
                index += open_size
                continue
            if text.startswith(close_token, index) and stack:
                start = stack.pop()
                spans.append((start, index + close_size))
                index += close_size
                continue
            index += 1
        return spans


    def _mini_render_template(raw: str) -> str:
        template = _MiniTemplate(raw)
        name = template.name.strip()
        if not name:
            return ""
        if name.startswith("#"):
            return ""
        if name == "!":
            return "|"
        if name in {"\u6ce8\u97f3", "\u9ed1\u5e55"}:
            return template.get(1).value if template.has(1) else ""
        if name == "\u56fe\u6807":
            if template.has(2):
                return template.get(2).value
            if template.has(1):
                return template.get(1).value
            return ""
        if name == "\u661f\u671f":
            return template.get(1).value if template.has(1) else ""
        return ""


    def _mini_strip_code(text: str) -> str:
        cleaned = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<hr\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?m)^(={2,6})\s*(.*?)\s*\1\s*$", r"\2", cleaned)

        guard = 0
        while "{{" in cleaned and "}}" in cleaned and guard < 2000:
            spans = _mini_find_balanced_spans(cleaned, "{{", "}}")
            if not spans:
                break
            start, end = spans[0]
            cleaned = cleaned[:start] + _mini_render_template(cleaned[start:end]) + cleaned[end:]
            guard += 1

        cleaned = re.sub(
            r"\[\[\s*(?:File|file|Image|image|\u6587\u4ef6)\s*:[^\]]+\]\]",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\[(https?://[^\s\]]+)\s+([^\]]+)\]", r"\2", cleaned)
        cleaned = re.sub(r"\[(https?://[^\]]+)\]", "", cleaned)
        cleaned = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", cleaned)
        cleaned = re.sub(r"\[\[([^\]]+)\]\]", r"\1", cleaned)
        cleaned = re.sub(r"</?[A-Za-z][^>]*>", "", cleaned)
        cleaned = cleaned.replace("'''", "").replace("''", "")
        return cleaned


    class _MiniWikiCode:
        def __init__(self, text: str) -> None:
            self._text = text

        def filter_templates(self, recursive: bool = True) -> list[_MiniTemplate]:
            spans = sorted(_mini_find_balanced_spans(self._text, "{{", "}}"), key=lambda item: item[0])
            return [_MiniTemplate(self._text[start:end]) for start, end in spans]

        def filter_wikilinks(self, recursive: bool = True) -> list[_MiniWikiLink]:
            spans = sorted(_mini_find_balanced_spans(self._text, "[[", "]]"), key=lambda item: item[0])
            return [_MiniWikiLink(self._text[start + 2 : end - 2]) for start, end in spans]

        def get_sections(self, include_headings: bool = True, flat: bool = True) -> list[_MiniSection]:
            heading_pattern = re.compile(r"(?m)^(={2,6})\s*(.*?)\s*\1\s*$")
            matches = list(heading_pattern.finditer(self._text))
            if not matches:
                return [_MiniSection(self._text)]
            sections: list[_MiniSection] = []
            if matches[0].start() > 0:
                sections.append(_MiniSection(self._text[: matches[0].start()]))
            for index, match in enumerate(matches):
                section_end = matches[index + 1].start() if index + 1 < len(matches) else len(self._text)
                sections.append(_MiniSection(self._text[match.start() : section_end]))
            return sections

        def strip_code(self) -> str:
            return _mini_strip_code(self._text)


    class _MiniMwParserFromHell:
        @staticmethod
        def parse(text: str) -> _MiniWikiCode:
            return _MiniWikiCode(text)


    mwparserfromhell = _MiniMwParserFromHell()

from .exceptions import ParsingError
from .models import (
    ArtifactPieceRecord,
    ArtifactSetRecord,
    ArchonQuestReference,
    ArchonQuestDialogue,
    ArchonQuestRecord,
    BookRecord,
    BookVolume,
    CharacterQuestRecord,
    ChronicleRecord,
    ChronicleItemRecord,
    ChroniclePageRecord,
    ChronicleSectionRecord,
    CharacterRecord,
    EventQuestDialogueEntry,
    EventQuestRecord,
    EventQuestStepRecord,
    MonsterRecord, ParsedPage,
    NorthLibraryNode,
    NorthLibraryRecord,
    CharacterStoryRecord,
    CharacterVoiceRecord,
    ConstellationRecord,
    AdventureNotesRecord,
    ParsedSection,
    WeaponRecord,
    FoodRecord,
    ItemRecord,
    MaterialRecord,
    MonsterRecord,
    NameCardRecord,
    QuestRewardRecord,
    ParsedPage,
    ParsedSection,
    QuestItemRecord,
    SecretItemRecord,
    TalentRecord,
    WeaponRecord,
    WildlifeRecord,
)

_ARCHON_ACT_PATTERN = re.compile(r"(第[〇零一二三四五六七八九十百千两\d]+幕|序奏|幕间)")
_ARCHON_DIALOGUE_SPEAKER_PATTERN = re.compile(r"^[*#:;\s]*([^：:\n]{1,40})[：:]", re.MULTILINE)
_ARCHON_SPLIT_PATTERN = re.compile(r"[、，,\n]+")
_ARCHON_LINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_ARCHON_HEADING_PATTERN = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$")
_ARCHON_DIALOGUE_LINE_PATTERN = re.compile(r"^(?P<speaker>[^：:\n]{1,40})[：:](?P<text>.+)$")
_ARCHON_OPTION_LINE_PATTERN = re.compile(r"^(?:选项(?:分支)?\d*|分支\d*|选项)\s*[：:]\s*(?P<text>.+)$")
_ARCHON_CHAPTER_PATTERN = re.compile(r"(序章|间章|第[零〇一二三四五六七八九十百千万两\d]+章|无)")
_ARCHON_ALT_ACT_PATTERN = re.compile(
    r"(第[零〇一二三四五六七八九十百千万两\d]+幕|序奏|幕间|月之[零〇一二三四五六七八九十两\d]+|月之一|月之二|月之三|月之四)"
)
_ARCHON_SPECIAL_CHAPTERS = {"空月之歌"}
_ARCHON_TRAVELER_SPEAKERS = {"旅行者", "空", "荧"}
_ARCHON_QUOTED_TITLE_PATTERN = re.compile(r"[「『“\"]\s*(?P<title>[^」』”\"]+?)\s*[」』”\"]")
_ARCHON_REFERENCE_CHAPTER_ACT_PATTERN = re.compile(
    r"(?P<chapter>序章|间章|第[零〇一二三四五六七八九十百千万两\d]+章|无)?"
    r"(?:\s*[·．•\-—]\s*|\s+)?"
    r"(?P<act>第[〇零一二三四五六七八九十百千两\d]+幕)?"
)
_ARCHON_SERIES_SECTION_EXCLUDES = {
    "简介",
    "剧情",
    "任务剧情",
    "任务流程",
    "任务奖励",
    "奖励",
    "相关成就",
    "成就",
    "出场人物",
    "登场人物",
    "相关NPC",
    "对话",
    "背景",
}

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
_CHRONICLE_HEADING_PATTERN = re.compile(r"^(={3,5})\s*(.*?)\s*\1\s*$")
_CHRONICLE_BOLD_ITEM_PATTERN = re.compile(r"^'''(.+?)'''(?:\s*[：:]\s*(.*))?$")
_CHRONICLE_BULLET_PATTERN = re.compile(r"^\*\s*(.+)$")
_CHRONICLE_BULLET_ITEM_PATTERN = re.compile(r"^(?P<year>.+?)(?:\s{2,}|\t+|[：:])\s*(?P<content>.+)$")
_CHRONICLE_WRAPPER_TAG_PATTERN = re.compile(r"^</?div\b[^>]*>$", re.IGNORECASE)
_CHRONICLE_FACTION_KEYWORDS = (
    "势力",
    "阵营",
    "王朝",
    "王庭",
    "政权",
    "统治",
    "统一",
    "分裂",
    "联盟",
    "城邦",
    "执政",
    "秩序",
    "覆灭",
    "灭亡",
    "崛起",
    "退守",
    "版图",
)

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
_NORTH_LIBRARY_BSTYLE_PATTERN = re.compile(r"<bstyle>.*?</bstyle>", re.IGNORECASE | re.DOTALL)
_NORTH_LIBRARY_RULE_PATTERN = re.compile(r"^\s*-{4,}\s*$")
_NORTH_LIBRARY_HEADING_PATTERN = re.compile(r"^(={1,4})\s*(.*?)\s*\1\s*$")
_NORTH_LIBRARY_ENTRY_PATTERN = re.compile(r"^\*+\s*(.*?)\s*$")
_NORTH_LIBRARY_ITEM_PATTERN = re.compile(r"^\s*(?:<[^>]+>\s*)*'''(.*?)'''(?:\s*</[^>]+>\s*)*$")
_NORTH_LIBRARY_COLOR_TEMPLATE_PATTERN = re.compile(
    r"\{\{\s*颜色\s*\|[^{}|]+\|([^{}|]+?)(?:\|[^{}]*)?\s*}}"
)
_NORTH_LIBRARY_SIMPLE_TEMPLATE_PATTERN = re.compile(r"\{\{\s*[^{}|]+\|([^{}]+?)\s*}}")
_FILE_LINK_PREFIXES = ("文件:", "File:", "Image:", "Category:", "分类:")
# 书籍模板关键词
_BOOK_TEMPLATE_KEYWORDS = ("书籍", "书籍信息", "白夜国馆藏", "千世流樱", "浮世风流", "冒险家")
_EVENT_QUEST_OPTION_MARKERS = {"★", "☆", "MediaWiki:PlotOptions"}
_EVENT_QUEST_OPTION_ICON_PATTERN = re.compile(
    r"^(?:(?:Image|File|文件)\s*:\s*)?剧情选项[-\w\u4e00-\u9fff]*\.(?:png|jpe?g|gif|svg)\s*",
    re.IGNORECASE,
)
_EVENT_QUEST_OPTION_SIZE_PATTERN = re.compile(r"^\d+\s*px\b\s*", re.IGNORECASE)
_EVENT_QUEST_IGNORED_LINES = {
    "折叠",
    "展开",
    "MediaWiki:fold",
    "* * *",
}
_EVENT_QUEST_SECTION_BOUNDARIES = {
    "任务相关",
    "任务条件",
    "前置任务",
    "后续任务",
    "任务流程",
    "任务剧情",
    "活动奖励",
    "奖励",
    "纪行奖励",
    "注释",
    "参考",
}
_EVENT_QUEST_REWARD_TOKENS = ("原石", "摩拉", "经验", "精锻", "魔矿", "阅历", "好感")
_EVENT_QUEST_PLOT_SECTION_PREFIXES = ("任务剧情", "剧情")
_CHARACTER_QUEST_SECTION_BOUNDARIES = {
    "任务相关",
    "任务条件",
    "前置任务",
    "后续任务",
    "系列任务",
    "任务流程",
    "任务剧情",
    "剧情",
    "任务奖励",
    "奖励",
    "注释",
    "参考",
}
_CHARACTER_QUEST_LIST_STOP_TITLES = {"邀约事件", "热点事件"}
_CHARACTER_QUEST_FILE_HINT_PATTERN = re.compile(
    r"(?:File|Image|文件)\s*:\s*任务-[^-|\]]+-(?P<name>[^.\]|]+)\.(?:png|jpe?g|gif|svg|webp)",
    re.IGNORECASE,
)
_WIKILINK_TARGET_TEXT_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_INLINE_BREAK_SENTINEL = "__INLINE_BR__"
_WIKITEXT_HEADING_PATTERN = re.compile(
    r"(?m)^(?P<marks>=+)\s*(?P<title>.*?)\s*(?P=marks)\s*$"
)

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

    def parse_chronicle_page(self, payload: dict[str, Any]) -> ChroniclePageRecord:
        """解析提瓦特编年史页面，按章节层级与条目顺序提取记录。"""
        parsed_page = self.parse_page(payload)
        intro, sections = self._extract_chronicle_sections(parsed_page.title, parsed_page.wikitext)
        return ChroniclePageRecord(
            title=parsed_page.title,
            page_id=parsed_page.page_id,
            categories=parsed_page.categories,
            intro=intro,
            sections=sections,
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

    def parse_character_quest_page(
        self,
        payload: dict[str, Any],
        *,
        series_context: Mapping[str, Any] | None = None,
    ) -> CharacterQuestRecord:
        """解析角色传说任务与部族纪闻的具体任务页面。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("任务名称", "名称"),
                ("任务地区", "地区", "国家"),
                ("任务类型", "类型"),
                ("任务描述", "描述", "介绍"),
                ("出场人物", "相关角色"),
                ("前置任务",),
                ("后续任务",),
            ),
        )
        series_context = series_context or {}
        series_titles = self._extract_character_quest_series_titles(parsed_page)
        chapter_name = series_titles[0] if series_titles else ""
        related_quest = series_titles[1] if len(series_titles) > 1 else ""
        related_activity = self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                ("相关活动", "所属任务", "活动"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            self._extract_first_list_item(self._find_section_text(parsed_page.sections, ("相关活动", "所属任务"))),
        )
        context = self._resolve_character_quest_context(
            series_context,
            title=self._resolve_record_title(parsed_page, ("任务名称", "名称"), preferred_params=main_template),
            related_quest=related_quest or related_activity,
            chapter_name=chapter_name,
        )
        description = self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                ("任务描述", "描述", "介绍"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            self._extract_first_non_empty_line(self._find_section_text(parsed_page.sections, ("简介",))),
            parsed_page.summary,
        )
        related_characters = self._extract_link_titles(
            self._coalesce(
                self._resolve_raw_value(
                    parsed_page.templates,
                    ("出场人物", "相关角色"),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
                self._find_section_text(parsed_page.sections, ("出场人物", "相关角色")),
            )
        )
        objectives = self._extract_character_quest_flow_titles(parsed_page.sections, parsed_page.wikitext)
        dialogues = self._extract_character_quest_dialogues(parsed_page.sections, objectives, parsed_page.wikitext)
        related_character = self._coalesce(
            context.get("related_character", "") if context else "",
            context.get("group_name", "") if context else "",
            related_characters[0] if related_characters else "",
        )
        version_match = re.search(r"\|所属版本\s*=\s*(.+?)(?:\||\n|$)", parsed_page.wikitext)
        version = self._clean_field_value(version_match.group(1)) if version_match else ""

        return CharacterQuestRecord(
            title=self._resolve_record_title(parsed_page, ("任务名称", "名称"), preferred_params=main_template),
            page_id=parsed_page.page_id,
            region=self._coalesce(
                self._resolve_value(
                    parsed_page.templates,
                    ("任务地区", "地区", "国家"),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
                context.get("region", "") if context else "",
            ),
            version=version,
            quest_type=self._coalesce(
                self._resolve_value(
                    parsed_page.templates,
                    ("任务类型", "类型"),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
                context.get("quest_type", "") if context else "",
            ),
            related_character=related_character,
            related_characters=related_characters,
            description=description,
            chapter_name=self._coalesce(
                context.get("chapter_name", "") if context else "",
                chapter_name,
                related_activity if not related_quest else "",
            ),
            act=context.get("act", "") if context else "",
            act_name=self._coalesce(
                context.get("act_name", "") if context else "",
                related_quest,
            ),
            related_quest=self._coalesce(
                related_quest,
                context.get("act_name", "") if context else "",
                related_activity,
            ),
            previous_quest=self._coalesce(
                self._resolve_value(
                    parsed_page.templates,
                    ("前置任务",),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
                self._extract_first_list_item(self._find_section_text(parsed_page.sections, ("前置任务",))),
                self._extract_required_quest(self._find_section_text(parsed_page.sections, ("任务条件",))),
            ),
            next_quest=self._coalesce(
                self._resolve_value(
                    parsed_page.templates,
                    ("后续任务",),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
                self._extract_first_list_item(self._find_section_text(parsed_page.sections, ("后续任务",))),
            ),
            objectives=objectives,
            dialogues=dialogues,
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
        )

    def parse_event_quest_page(
        self,
        payload: dict[str, Any],
        event_payload: dict[str, Any] | None = None,
    ) -> EventQuestRecord:
        """解析活动任务风格的任务页面。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("任务地区", "地区", "国家"),
                ("任务类型", "类型"),
                ("相关活动", "所属任务", "活动"),
                ("出场人物", "相关角色"),
                ("任务描述", "描述", "介绍"),
                ("时间", "活动时间", "活动期间", "开始时间"),
            ),
        )
        related_event = self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                ("相关活动", "所属任务", "活动"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            self._extract_first_list_item(self._find_section_text(parsed_page.sections, ("所属任务", "相关活动"))),
        )
        description = self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                ("任务描述", "描述", "介绍"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            self._extract_event_quest_description(parsed_page.sections),
        )
        related_characters = self._extract_link_titles(
            self._coalesce(
                self._resolve_raw_value(
                    parsed_page.templates,
                    ("出场人物", "相关角色"),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
                self._find_section_text(parsed_page.sections, ("出场人物", "相关角色")),
            )
        )
        previous_quest = self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                ("前置任务",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            self._extract_first_list_item(self._find_section_text(parsed_page.sections, ("前置任务",))),
            self._extract_required_quest(self._find_section_text(parsed_page.sections, ("任务条件",))),
        )
        next_quest = self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                ("后续任务",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            self._extract_first_list_item(self._find_section_text(parsed_page.sections, ("后续任务",))),
        )
        event_name = related_event
        event_period = self._resolve_event_period(
            parsed_page.templates,
            preferred_params=main_template,
            wikitext=parsed_page.wikitext,
        )
        related_event_description = ""
        event_list: list[str] = []
        if event_payload is not None:
            event_name, event_period, event_list, related_event_description = self._extract_event_page_context(
                event_payload,
                fallback_event_name=event_name,
                fallback_event_period=event_period,
            )
        quests = self._extract_event_quest_flow_titles(parsed_page.sections, parsed_page.wikitext)
        dialogue = self._extract_event_quest_dialogue(parsed_page.sections, quests, parsed_page.wikitext)

        return EventQuestRecord(
            title=self._resolve_record_title(parsed_page, ("任务名称", "名称"), preferred_params=main_template),
            page_id=parsed_page.page_id,
            region=self._resolve_value(
                parsed_page.templates,
                ("任务地区", "地区", "国家"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            quest_type=self._resolve_value(
                parsed_page.templates,
                ("任务类型", "类型"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            event_list=event_list,
            event_name=event_name,
            event_period=event_period,
            quests=quests,
            description=description,
            dialogue=dialogue,
            version=self._resolve_value(
                parsed_page.templates,
                ("所属版本", "版本"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            related_event=related_event,
            related_event_description=related_event_description,
            related_characters=related_characters,
            previous_quest=previous_quest,
            next_quest=next_quest,
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

    def parse_archon_quest_page(
        self,
        payload: dict[str, Any],
        *,
        series_context: Mapping[str, Any] | None = None,
    ) -> ArchonQuestRecord:
        """解析魔神任务页面。"""
        parsed_page = self.parse_page(payload)
        template_name, main_template = self._select_archon_quest_template(parsed_page.templates)
        series_context = series_context or {}

        title = self._resolve_record_title(
            parsed_page,
            ("任务名称", "系列任务名", "名称"),
            preferred_params=main_template,
        )
        english_title = self._resolve_archon_english_title(
            parsed_page.templates,
            preferred_params=main_template,
            wikitext=parsed_page.wikitext,
        )
        description = self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                ("任务描述", "描述"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            parsed_page.summary,
        )
        dialogues = self._extract_archon_dialogues(
            self._resolve_raw_value(
                parsed_page.templates,
                ("任务剧情", "剧情", "对话", "任务对话"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            parsed_page.sections,
            wikitext=parsed_page.wikitext,
        )
        series = self._extract_archon_series_chain(
            self._resolve_raw_value(
                parsed_page.templates,
                ("系列任务",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            )
        )
        chapter, chapter_name, act, act_name = self._resolve_archon_chapter_act(
            template_name,
            main_template,
            series,
            series_context,
            page_title=title,
            wikitext=parsed_page.wikitext,
        )
        objectives = self._extract_archon_objectives(
            self._resolve_raw_value(
                parsed_page.templates,
                ("任务流程",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            parsed_page.sections,
        )
        rewards = self._extract_archon_rewards(
            self._resolve_raw_value(
                parsed_page.templates,
                ("奖励",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            )
        )
        related_npcs = self._extract_archon_related_npcs(
            self._resolve_raw_value(
                parsed_page.templates,
                ("出场人物",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            parsed_page.sections,
            dialogues=dialogues,
        )
        prerequisites = self._extract_archon_references(
            self._coalesce(
                self._resolve_raw_value(
                    parsed_page.templates,
                    ("前置任务",),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
                self._resolve_raw_value(
                    parsed_page.templates,
                    ("任务条件",),
                    preferred_params=main_template,
                    wikitext=parsed_page.wikitext,
                ),
            )
            ,
            series_context=series_context,
        )
        parallel_quests = self._extract_archon_references(
            self._resolve_raw_value(
                parsed_page.templates,
                ("并行任务",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            series_context=series_context,
        )
        follow_up_quests = self._extract_archon_references(
            self._resolve_raw_value(
                parsed_page.templates,
                ("后续任务",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            series_context=series_context,
        )

        return ArchonQuestRecord(
            title=title,
            english_title=english_title,
            page_type=template_name,
            chapter=chapter,
            chapter_name=chapter_name,
            act=act,
            act_name=act_name,
            description=description,
            objectives=objectives,
            rewards=rewards,
            related_npcs=related_npcs,
            region=self._resolve_value(
                parsed_page.templates,
                ("任务地区",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            version=self._resolve_value(
                parsed_page.templates,
                ("所属版本",),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            series=series,
            prerequisites=prerequisites,
            parallel_quests=parallel_quests,
            follow_up_quests=follow_up_quests,
            dialogues=dialogues,
            categories=parsed_page.categories,
            sections=parsed_page.sections,
            templates=parsed_page.templates,
            page_id=parsed_page.page_id,
        )
    def parse_archon_quest_list_page(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        """Parse the archon quest index page into ordered quest entries."""
        _, _, wikitext = self.extract_page_metadata(payload)
        current_chapter = ""
        current_chapter_name = ""
        current_act = ""
        current_act_name = ""
        seen: set[str] = set()
        entries: list[dict[str, str]] = []

        for raw_line in wikitext.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            heading_match = _ARCHON_HEADING_PATTERN.match(line)
            if heading_match:
                heading_info = self._extract_archon_heading_parts(heading_match.group(2))
                if heading_info["chapter"]:
                    current_chapter = heading_info["chapter"]
                    current_chapter_name = heading_info["chapter_name"]
                if heading_info["act"]:
                    current_act = heading_info["act"]
                    current_act_name = heading_info["act_name"]
                elif heading_info["chapter"]:
                    current_act = ""
                    current_act_name = ""
                continue

            for entry in self._extract_archon_icon_entries_from_line(
                line,
                current_chapter=current_chapter,
                current_chapter_name=current_chapter_name,
                current_act=current_act,
                current_act_name=current_act_name,
            ):
                self._append_archon_list_entry(entries, seen, entry)

            if not current_chapter and not current_act:
                continue

            for title in self._extract_archon_direct_entry_titles(line):
                self._append_archon_list_entry(
                    entries,
                    seen,
                    {
                        "title": title,
                        "chapter": current_chapter,
                        "chapter_name": current_chapter_name,
                        "act": current_act,
                        "act_name": current_act_name,
                    },
                )
        return entries

    def build_archon_series_context(
        self,
        entries: Sequence[Mapping[str, str]],
    ) -> dict[str, tuple[str, str, str, str]]:
        """Build a chapter/act/name lookup from list-page quest entries."""
        context: dict[str, tuple[str, str, str, str]] = {}
        for entry in entries:
            chapter = entry.get("chapter", "")
            act = entry.get("act", "")
            chapter_name = entry.get("chapter_name", "")
            act_name = entry.get("act_name", "") or (entry.get("series_title", "") if act else "")
            for key in self._extract_archon_context_keys(entry):
                context.setdefault(key, (chapter, act, chapter_name, act_name))
        return context

    def parse_character_quest_list_page(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        """解析传说任务列表页中的传说任务/部族纪闻入口。"""
        _, _, wikitext = self.extract_page_metadata(payload)
        section_wikitext = self._extract_section_wikitext(wikitext, ("传说任务和部族纪闻",)) or wikitext
        current_region = ""
        current_group = ""
        current_quest_type = "传说任务"
        pending_related_character = ""
        entries: list[dict[str, str]] = []
        seen: set[str] = set()

        for raw_line in section_wikitext.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            heading_match = _WIKITEXT_HEADING_PATTERN.match(line)
            if heading_match:
                heading_title = self._normalize_plain_text(heading_match.group("title")).strip()
                heading_level = len(heading_match.group("marks"))
                if heading_title in _CHARACTER_QUEST_LIST_STOP_TITLES:
                    break
                if heading_level == 3:
                    current_region = heading_title
                    current_group = ""
                    current_quest_type = "传说任务"
                    continue
                if heading_level == 4 and heading_title in {"传说任务", "部族纪闻"}:
                    current_group = ""
                    current_quest_type = heading_title
                    continue
                if heading_level >= 4:
                    current_group = heading_title
                    if current_region == "纳塔" and current_quest_type != "传说任务":
                        current_quest_type = "部族纪闻"
                    continue

            related_character = self._extract_character_quest_related_character_from_line(line)
            if related_character:
                pending_related_character = related_character
                continue

            entry = self._extract_character_quest_list_entry_from_line(
                line,
                region=current_region,
                quest_type=current_quest_type,
                group_name=current_group,
                related_character=pending_related_character,
            )
            if entry is None:
                continue
            title = entry["title"]
            if title in seen:
                pending_related_character = ""
                continue
            seen.add(title)
            entries.append(entry)
            pending_related_character = ""

        return entries

    def build_character_quest_series_context(
        self,
        entries: Sequence[Mapping[str, str]],
    ) -> dict[str, dict[str, str]]:
        """Build a chapter/act/region lookup from the character quest list page."""
        context: dict[str, dict[str, str]] = {}
        for entry in entries:
            value = {
                "title": entry.get("title", ""),
                "chapter_name": entry.get("chapter_name", ""),
                "act": entry.get("act", ""),
                "act_name": entry.get("act_name", ""),
                "region": entry.get("region", ""),
                "quest_type": entry.get("quest_type", ""),
                "group_name": entry.get("group_name", ""),
                "related_character": entry.get("related_character", ""),
            }
            for key in self._extract_character_quest_context_keys(entry):
                context.setdefault(key, value)
        return context

    def extract_archon_series_quest_titles(
        self,
        wikitext: str,
        *,
        rendered_section_titles: Sequence[str] | None = None,
    ) -> list[str]:
        """Extract concrete quest-page titles from an archon series/act page."""
        titles: list[str] = []
        for raw_line in self._normalize_text(wikitext).splitlines():
            if "详细任务内容" not in self._normalize_plain_text(raw_line):
                continue
            for raw_title in _ARCHON_LINK_PATTERN.findall(raw_line):
                title = self._normalize_plain_text(raw_title).strip()
                if self._is_archon_series_quest_title(title):
                    titles.append(title)
        if titles:
            return self._unique_preserve_order(titles)

        for title, raw_text in self._extract_raw_sections(wikitext):
            normalized_title = self._normalize_plain_text(title).strip()
            if not self._is_archon_series_quest_title(normalized_title):
                continue
            plain_text = self._normalize_plain_text(raw_text)
            if "详细任务内容" in plain_text or "[[" in raw_text or "{{任务" in raw_text:
                titles.append(normalized_title)
        if titles:
            return self._unique_preserve_order(titles)

        if not rendered_section_titles:
            return []
        return self._unique_preserve_order(
            [
                self._normalize_plain_text(title).strip()
                for title in rendered_section_titles
                if self._is_archon_series_quest_title(title)
            ]
        )

    def parse_north_library_page(self, payload: dict[str, Any]) -> NorthLibraryRecord:
        """Parse the North Library encyclopedia index page into a nested tree."""
        title, page_id, wikitext = self.extract_page_metadata(payload)
        categories = self.parse_categories(wikitext)
        if not categories:
            categories = self._extract_payload_categories(payload)
        summary, nodes = self._build_north_library_tree(wikitext)
        return NorthLibraryRecord(
            title=title,
            page_id=page_id,
            summary=summary,
            categories=categories,
            nodes=nodes,
        )

    def _build_north_library_tree(self, wikitext: str) -> tuple[str, list[NorthLibraryNode]]:
        """Build a hierarchical tree from the North Library page wikitext."""
        sanitized = _CATEGORY_LINK_PATTERN.sub("", wikitext)
        sanitized = _NORTH_LIBRARY_BSTYLE_PATTERN.sub("", sanitized)
        sanitized = self._normalize_line_breaks(sanitized)

        root = NorthLibraryNode(kind="root")
        stack: list[tuple[int, NorthLibraryNode]] = [(0, root)]
        buffers: dict[int, list[str]] = {id(root): []}

        for raw_line in sanitized.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                self._append_north_library_text(buffers, stack[-1][1], "")
                continue
            if _NORTH_LIBRARY_RULE_PATTERN.match(stripped):
                continue

            heading_match = _NORTH_LIBRARY_HEADING_PATTERN.match(stripped)
            if heading_match:
                kind = {
                    1: "一级",
                    2: "二级",
                    3: "三级",
                    4: "四级",
                }[len(heading_match.group(1))]
                title = self._normalize_north_library_title(heading_match.group(2))
                if title:
                    node = NorthLibraryNode(kind=kind, title=title)
                    self._push_north_library_node(stack, buffers, node, self._north_library_depth(kind))
                    continue

            entry_match = _NORTH_LIBRARY_ENTRY_PATTERN.match(stripped)
            if entry_match:
                self._pop_north_library_stack(stack, self._north_library_depth("条目"))
                entry_content = entry_match.group(1).strip()
                entry_title = self._extract_north_library_item_title(entry_content)
                if entry_title:
                    node = NorthLibraryNode(kind="条目", title=entry_title)
                    self._push_north_library_node(stack, buffers, node, self._north_library_depth("条目"))
                else:
                    entry_text = self._normalize_north_library_text(entry_content)
                    if entry_text:
                        stack[-1][1].children.append(NorthLibraryNode(kind="条目", text=entry_text))
                continue

            item_title = self._extract_north_library_item_title(stripped)
            if item_title:
                node = NorthLibraryNode(kind="项目", title=item_title)
                self._push_north_library_node(stack, buffers, node, self._north_library_depth("项目"))
                continue

            text = self._normalize_north_library_text(line)
            if text:
                self._append_north_library_text(buffers, stack[-1][1], text)

        self._finalize_north_library_buffers(root, buffers)
        return root.text, root.children

    def _north_library_depth(self, kind: str) -> int:
        """Map North Library node kinds to a stable nesting depth."""
        return {
            "一级": 1,
            "二级": 2,
            "三级": 3,
            "四级": 4,
            "项目": 5,
            "条目": 6,
        }[kind]

    def _push_north_library_node(
        self,
        stack: list[tuple[int, NorthLibraryNode]],
        buffers: dict[int, list[str]],
        node: NorthLibraryNode,
        depth: int,
    ) -> None:
        """Attach a new node and make it the current text target."""
        self._pop_north_library_stack(stack, depth)
        stack[-1][1].children.append(node)
        stack.append((depth, node))
        buffers[id(node)] = []

    def _pop_north_library_stack(
        self,
        stack: list[tuple[int, NorthLibraryNode]],
        depth: int,
    ) -> None:
        """Pop the stack until the next node becomes the correct parent."""
        while len(stack) > 1 and stack[-1][0] >= depth:
            stack.pop()

    def _append_north_library_text(
        self,
        buffers: dict[int, list[str]],
        node: NorthLibraryNode,
        text: str,
    ) -> None:
        """Append a text line while preserving intentional paragraph breaks."""
        buffer = buffers.setdefault(id(node), [])
        if text:
            buffer.append(text)
            return
        if buffer and buffer[-1] != "":
            buffer.append("")

    def _finalize_north_library_buffers(
        self,
        node: NorthLibraryNode,
        buffers: dict[int, list[str]],
    ) -> None:
        """Normalize buffered text for a node and all of its descendants."""
        existing = self._normalize_text(node.text)
        buffered = self._normalize_text("\n".join(buffers.get(id(node), [])))
        node.text = self._normalize_text("\n".join(part for part in (existing, buffered) if part))
        for child in node.children:
            self._finalize_north_library_buffers(child, buffers)

    def _extract_north_library_item_title(self, raw_text: str) -> str:
        """Return the title for a bold-only item or bullet title line."""
        match = _NORTH_LIBRARY_ITEM_PATTERN.match(raw_text)
        if not match:
            return ""
        return self._normalize_north_library_title(match.group(1))

    def _normalize_north_library_title(self, raw_text: str) -> str:
        """Normalize a heading or project title with targeted template fallbacks."""
        title = self._normalize_north_library_text(raw_text)
        if title:
            return title
        fallback = _NORTH_LIBRARY_SIMPLE_TEMPLATE_PATTERN.sub(
            self._replace_north_library_simple_template,
            raw_text,
        )
        if fallback == raw_text:
            return ""
        return self._normalize_north_library_text(fallback)

    def _normalize_north_library_text(self, raw_text: str) -> str:
        """Normalize line-level North Library text with minimal template fallback."""
        cleaned = _NORTH_LIBRARY_BSTYLE_PATTERN.sub("", raw_text)
        cleaned = _NORTH_LIBRARY_COLOR_TEMPLATE_PATTERN.sub(
            lambda match: match.group(1).strip(),
            cleaned,
        )
        return self._normalize_plain_text(cleaned)

    def _replace_north_library_simple_template(self, match: re.Match[str]) -> str:
        """Fallback for display-only templates that strip_code drops completely."""
        values = [part.strip() for part in match.group(1).split("|") if part.strip()]
        return values[-1] if values else ""

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

    def _select_archon_quest_template(
        self,
        templates: dict[str, list[dict[str, str]]],
    ) -> tuple[str, dict[str, str]]:
        """Select the most likely archon-quest template from a page."""
        candidates: list[tuple[int, int, str, dict[str, str]]] = []
        for name, items in templates.items():
            normalized_name = self._normalize_plain_text(name)
            if "多重系列任务" in normalized_name:
                field_groups = (("系列任务名",), ("任务类型",), ("任务地区",), ("所属版本",))
                template_type = "多重系列任务"
            elif "系列任务" in normalized_name:
                field_groups = (("系列任务名",), ("副标题", "任务章节"), ("任务类型",), ("系列任务",))
                template_type = "系列任务"
            elif normalized_name == "任务":
                field_groups = (("任务名称",), ("任务描述", "描述"), ("奖励",), ("任务流程",), ("系列任务",))
                template_type = "任务"
            else:
                continue
            for params in items:
                score = sum(1 for aliases in field_groups if self._value_from_params(params, aliases, plain=False))
                if score <= 0:
                    continue
                candidates.append((score, len(params), template_type, params))
        if not candidates:
            return "", {}
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        _, _, template_type, params = candidates[0]
        return template_type, params
    def _resolve_archon_chapter_act(
        self,
        template_type: str,
        params: dict[str, str],
        series: Sequence[str],
        series_context: Mapping[str, Any],
        *,
        page_title: str,
        wikitext: str,
    ) -> tuple[str, str, str, str]:
        """Resolve chapter/act codes and display names across archon quest page types."""
        mapped_chapter, mapped_act, mapped_chapter_name, mapped_act_name = self._lookup_archon_series_context(
            series_context,
            page_title,
        )
        if mapped_chapter or mapped_act:
            return mapped_chapter, mapped_chapter_name, mapped_act, mapped_act_name

        subtitle = self._coalesce(
            self._value_from_params(params, ("副标题", "任务章节"), plain=True),
            self._extract_plain_param_from_wikitext(wikitext, ("副标题", "任务章节")),
        )
        heading_info = self._extract_archon_heading_parts(subtitle)
        chapter, act = self._parse_archon_chapter_act_text(subtitle)
        chapter_name = heading_info["chapter_name"]
        act_name = heading_info["act_name"]
        if template_type == "系列任务" and act and not act_name and page_title != chapter:
            act_name = page_title
        if chapter or act:
            return chapter, chapter_name, act, act_name

        if template_type == "多重系列任务":
            chapter = self._coalesce(
                self._value_from_params(params, ("系列任务名", "任务章节"), plain=True),
                page_title,
            )
            return chapter, "", "", ""

        if template_type == "系列任务":
            chapter = self._coalesce(
                self._value_from_params(params, ("系列任务", "任务章节"), plain=True),
                series[0] if series else "",
                page_title,
            )
            return chapter, "", "", ""

        for candidate in reversed(series):
            mapped_chapter, mapped_act, mapped_chapter_name, mapped_act_name = self._lookup_archon_series_context(
                series_context,
                candidate,
            )
            if mapped_chapter or mapped_act:
                return mapped_chapter, mapped_chapter_name, mapped_act, mapped_act_name

        if series:
            fallback_chapter, fallback_act = self._parse_archon_chapter_act_text(series[0])
            if fallback_chapter or fallback_act:
                return fallback_chapter, "", fallback_act, series[-1] if len(series) >= 2 else ""
            if len(series) >= 2:
                return series[0], "", "", series[-1]
            return series[0], "", "", ""

        chapter, act = self._parse_archon_chapter_act_text(page_title)
        return chapter, "", act, ""
    def _parse_archon_chapter_act_text(self, value: str) -> tuple[str, str]:
        """Parse strings like '第五章 第六幕' into chapter/act fields."""
        normalized = re.sub(r"\s+", " ", self._normalize_plain_text(value))
        if not normalized:
            return "", ""
        heading_info = self._extract_archon_heading_parts(normalized)
        if heading_info["chapter"] or heading_info["act"]:
            return heading_info["chapter"] or normalized, heading_info["act"]
        return normalized, ""
    def _extract_archon_series_chain(self, raw: str) -> list[str]:
        """Split a raw series field into stable ordered titles."""
        if not raw:
            return []
        normalized = self._normalize_plain_text(raw).strip()
        heading_info = self._extract_archon_heading_parts(normalized)
        if heading_info["chapter"] and heading_info["chapter_name"] and not heading_info["act"]:
            return self._unique_preserve_order([heading_info["chapter"], heading_info["chapter_name"]])
        parts = [
            self._normalize_plain_text(chunk).strip()
            for chunk in _ARCHON_SPLIT_PATTERN.split(normalized)
        ]
        return self._unique_preserve_order([part for part in parts if part])
    def _extract_archon_objectives(
        self,
        raw: str,
        sections: Sequence[ParsedSection],
    ) -> list[str]:
        """Extract objectives from template fields first, then fallback to section headings."""
        objectives = self._extract_archon_list(raw)
        if objectives:
            return objectives
        fallback_titles: list[str] = []
        for section in sections:
            title = self._normalize_plain_text(section.title)
            if title in {"", "简介", "任务剧情", "剧情", "任务流程"}:
                continue
            fallback_titles.append(title)
        return self._unique_preserve_order(fallback_titles)
    def _extract_archon_rewards(self, raw: str) -> list[QuestRewardRecord]:
        """Extract structured rewards from repeated 图标 templates."""
        if not raw:
            return []
        rewards: list[QuestRewardRecord] = []
        code = mwparserfromhell.parse(self._normalize_text(raw))
        for template in code.filter_templates(recursive=True):
            if self._normalize_plain_text(str(template.name)) != "图标":
                continue
            name = self._normalize_plain_text(str(template.get(1).value)) if template.has(1) else ""
            amount = self._extract_archon_reward_amount(
                self._normalize_plain_text(str(template.get(2).value)) if template.has(2) else ""
            )
            if not name:
                continue
            rewards.append(QuestRewardRecord(name=name, amount=amount))
        if rewards:
            return rewards
        return [
            QuestRewardRecord(name=item, amount=None)
            for item in self._extract_archon_list(raw)
        ]
    def _extract_archon_reward_amount(self, value: str) -> int | str | None:
        """Normalize reward amounts into integers when possible."""
        normalized = self._normalize_plain_text(value).replace(",", "").strip()
        if not normalized:
            return None
        return int(normalized) if normalized.isdigit() else normalized
    def _extract_archon_related_npcs(
        self,
        raw: str,
        sections: Sequence[ParsedSection],
        *,
        dialogues: Sequence[ArchonQuestDialogue] | None = None,
    ) -> list[str]:
        """Merge explicit 出场人物 data with dialogue-speaker fallback."""
        explicit_candidates = self._extract_archon_list(raw)
        candidates = list(explicit_candidates)
        if dialogues is not None:
            fallback_candidates = [
                dialogue.speaker
                for dialogue in dialogues
                if dialogue.speaker and dialogue.dialogue_type in {"character", "traveler"}
            ]
        else:
            fallback_candidates = self._extract_archon_dialogue_speakers(sections)
        excluded = {"？？？", "???", "描述"}
        if explicit_candidates:
            excluded = excluded | {"旅行者", "派蒙"}
        candidates.extend(
            speaker
            for speaker in fallback_candidates
            if speaker and speaker not in excluded
        )
        return self._unique_preserve_order(
            [item for item in candidates if item and item not in {"？？？", "???", "描述"}]
        )
    def _extract_archon_heading_parts(self, value: str) -> dict[str, str]:
        """Split chapter/act headings into code and display-name fields."""
        normalized = self._normalize_plain_text(value).strip()
        chapter_match = _ARCHON_CHAPTER_PATTERN.search(normalized)
        act_match = _ARCHON_ALT_ACT_PATTERN.search(normalized)
        chapter = chapter_match.group(1).strip() if chapter_match else ""
        if not chapter:
            for special_chapter in _ARCHON_SPECIAL_CHAPTERS:
                if normalized == special_chapter:
                    chapter = special_chapter
                    break
                if normalized.startswith(special_chapter):
                    separator = normalized[len(special_chapter):len(special_chapter) + 1]
                    if separator in {"", " ", "·", "・", "-", "：", ":", "、", "，", ","}:
                        chapter = special_chapter
                        break
        act = act_match.group(1).strip() if act_match else ""

        chapter_name = ""
        if chapter:
            chapter_end = chapter_match.end() if chapter_match else len(chapter)
            chapter_name_end = act_match.start() if act_match and act_match.start() > chapter_end else len(normalized)
            chapter_name = normalized[chapter_end:chapter_name_end].strip(" ：:·-、，,")

        act_name = normalized[act_match.end():].strip(" ：:·-、，,") if act_match else ""
        return {
            "chapter": chapter,
            "chapter_name": chapter_name,
            "act": act,
            "act_name": act_name,
        }

    def _iter_template_positional_values(self, template: Any) -> list[str]:
        """Return template positional parameters ordered by position."""
        positional: list[tuple[int, str]] = []
        for param in getattr(template, "params", []):
            name = str(param.name).strip()
            if not name.isdigit():
                continue
            positional.append((int(name), str(param.value).strip()))
        positional.sort(key=lambda item: item[0])
        return [value for _, value in positional]

    def _extract_archon_icon_entries_from_line(
        self,
        line: str,
        *,
        current_chapter: str,
        current_chapter_name: str,
        current_act: str,
        current_act_name: str,
    ) -> list[dict[str, str]]:
        """Extract quest entries from 图标 task templates on the index page."""
        entries: list[dict[str, str]] = []
        code = mwparserfromhell.parse(line)
        for template in code.filter_templates(recursive=True):
            if self._normalize_plain_text(str(template.name)).strip() != "图标":
                continue
            positional = self._iter_template_positional_values(template)
            if len(positional) < 5:
                continue
            if self._normalize_plain_text(positional[0]).strip() != "任务":
                continue
            heading_info = self._extract_archon_heading_parts(positional[3])
            title = self._normalize_plain_text(positional[-1]).strip()
            if not title:
                continue
            entries.append(
                {
                    "title": title,
                    "chapter": heading_info["chapter"] or current_chapter,
                    "chapter_name": current_chapter_name or heading_info["chapter_name"],
                    "act": heading_info["act"] or current_act,
                    "act_name": heading_info["act_name"] or current_act_name,
                }
            )
        return entries

    def _append_archon_list_entry(
        self,
        entries: list[dict[str, str]],
        seen: set[str],
        entry: Mapping[str, str],
    ) -> None:
        """Append one normalized archon list entry when it is a real quest page."""
        title = self._normalize_plain_text(entry.get("title", "")).strip()
        if (
            not title
            or ":" in title
            or title in seen
            or title in {"魔神任务", entry.get("chapter", ""), entry.get("act", "")}
        ):
            return
        seen.add(title)
        entries.append(
            {
                "title": title,
                "chapter": entry.get("chapter", ""),
                "chapter_name": entry.get("chapter_name", ""),
                "act": entry.get("act", ""),
                "act_name": entry.get("act_name", ""),
                "series_title": entry.get("series_title", ""),
            }
        )

    def _extract_archon_direct_entry_titles(self, line: str) -> list[str]:
        """Extract plain-link quest entries without pulling in contextual prose links."""
        candidate = re.sub(r"''+", "", line).strip()
        candidate = candidate.lstrip("*#:;").strip()
        if not candidate:
            return []
        matches = _ARCHON_LINK_PATTERN.findall(candidate)
        if not matches:
            return []
        if not re.fullmatch(r"(?:\[\[[^\]]+\]\]\s*)+", candidate):
            return []
        return [self._normalize_plain_text(raw_title).strip() for raw_title in matches]

    def _is_archon_series_quest_title(self, value: str) -> bool:
        """Return True when a rendered section title looks like a concrete quest page."""
        normalized = self._normalize_plain_text(value).strip()
        if not normalized or normalized in _ARCHON_SERIES_SECTION_EXCLUDES:
            return False
        heading_info = self._extract_archon_heading_parts(normalized)
        if heading_info["chapter"] or heading_info["act"]:
            return False
        return True

    def _extract_raw_sections(self, wikitext: str) -> list[tuple[str, str]]:
        """Extract raw section bodies without stripping templates."""
        sanitized_wikitext = _CATEGORY_LINK_PATTERN.sub("", wikitext)
        code = mwparserfromhell.parse(sanitized_wikitext)
        sections: list[tuple[str, str]] = []
        for index, section in enumerate(code.get_sections(include_headings=True, flat=True)):
            heading_nodes = section.filter_headings()
            title = "简介" if index == 0 or not heading_nodes else str(heading_nodes[0].title).strip()
            raw_text = str(section)
            if heading_nodes:
                lines = raw_text.splitlines()
                raw_text = "\n".join(lines[1:]) if len(lines) > 1 else ""
            raw_text = raw_text.strip()
            if raw_text:
                sections.append((title, raw_text))
        return sections

    def _extract_archon_context_keys(self, entry: Mapping[str, str]) -> list[str]:
        """Build stable context keys for one quest index entry."""
        keys = [
            entry.get("title", ""),
            entry.get("series_title", ""),
            entry.get("chapter_name", ""),
            entry.get("act_name", ""),
            " ".join(part for part in (entry.get("chapter", ""), entry.get("act", "")) if part).strip(),
        ]
        return [key for key in self._unique_preserve_order(keys) if key]

    def _extract_character_quest_related_character_from_line(self, line: str) -> str:
        """从列表页图片文件名中提取中心角色/部族提示。"""
        match = _CHARACTER_QUEST_FILE_HINT_PATTERN.search(line)
        if not match:
            return ""
        return self._strip_quotes(self._clean_field_value(match.group("name"), context="generic"))

    def _normalize_character_quest_title(self, value: str) -> str:
        """Normalize task/group titles used in character-quest context matching."""
        normalized = self._strip_quotes(self._clean_field_value(value, context="generic"))
        for suffix in ("（系列任务）", "(系列任务)", "（任务）", "(任务)"):
            if normalized.endswith(suffix):
                return normalized[: -len(suffix)].strip()
        return normalized

    def _extract_character_quest_related_character_from_image_name(self, value: str) -> str:
        """Extract a role hint from inline icon-template image names."""
        normalized = self._normalize_text(value)
        if not normalized:
            return ""
        tail = normalized.rsplit("-", 1)[-1].strip()
        return self._normalize_character_quest_title(tail)

    def _extract_character_quest_list_entry_from_line(
        self,
        line: str,
        *,
        region: str,
        quest_type: str,
        group_name: str,
        related_character: str,
    ) -> dict[str, str] | None:
        """从列表页的一行双链接文本中提取任务索引信息。"""
        code = mwparserfromhell.parse(line)
        for template in code.filter_templates(recursive=False):
            if self._normalize_plain_text(str(template.name)).strip() != "图标":
                continue
            params = [self._normalize_plain_text(str(param.value)).strip() for param in template.params]
            if len(params) < 5 or params[0] != "任务":
                continue
            chapter_text = params[3]
            title = self._normalize_character_quest_title(params[4])
            chapter_name, act = self._split_character_quest_chapter_act(chapter_text)
            if not title or not chapter_name or not act:
                continue
            entry_related_character = related_character
            if len(params) >= 2 and params[1] and params[1] != "自定义":
                entry_related_character = self._normalize_character_quest_title(params[1])
            elif len(params) >= 6 and params[5]:
                image_related_character = self._extract_character_quest_related_character_from_image_name(params[5])
                if image_related_character:
                    entry_related_character = image_related_character
            return {
                "title": title,
                "chapter_name": chapter_name,
                "act": act,
                "act_name": title,
                "region": region,
                "quest_type": quest_type,
                "group_name": group_name,
                "related_character": entry_related_character,
            }

        matches = _WIKILINK_TARGET_TEXT_PATTERN.findall(line)
        if len(matches) < 2:
            return None
        first_target, first_text = matches[0]
        last_target, last_text = matches[-1]
        chapter_text = self._clean_field_value(first_text or first_target, context="generic")
        title = self._normalize_character_quest_title(last_target.split("#", 1)[0])
        act_name = self._normalize_character_quest_title(last_text or last_target)
        chapter_name, act = self._split_character_quest_chapter_act(chapter_text)
        if not title or not chapter_name or not act:
            return None
        return {
            "title": title,
            "chapter_name": chapter_name,
            "act": act,
            "act_name": act_name or title,
            "region": region,
            "quest_type": quest_type,
            "group_name": group_name,
            "related_character": related_character,
        }

    def _split_character_quest_chapter_act(self, value: str) -> tuple[str, str]:
        """拆分 `古闻之章 第一幕` 形式的列表页上下文。"""
        normalized = self._normalize_plain_text(value).strip()
        act_match = _ARCHON_ALT_ACT_PATTERN.search(normalized)
        if not act_match:
            return normalized, ""
        chapter_name = normalized[: act_match.start()].strip(" ：:·-、，,")
        act = act_match.group(1).strip()
        return chapter_name, act

    def _extract_character_quest_context_keys(self, entry: Mapping[str, str]) -> list[str]:
        """Build stable context keys for one character-quest list entry."""
        title = self._normalize_character_quest_title(entry.get("title", ""))
        act_name = self._normalize_character_quest_title(entry.get("act_name", ""))
        chapter_name = self._normalize_character_quest_title(entry.get("chapter_name", ""))
        keys = [
            title,
            act_name,
            chapter_name,
            " ".join(part for part in (chapter_name, entry.get("act", "")) if part).strip(),
        ]
        return [key for key in self._unique_preserve_order(keys) if key]

    def _extract_character_quest_series_titles(self, parsed_page: ParsedPage) -> list[str]:
        """提取任务页面“系列任务”章节中的章/幕标题。"""
        candidates = [
            self._find_section_text(parsed_page.sections, ("系列任务",)),
            self._resolve_raw_value(parsed_page.templates, ("系列任务",), wikitext=parsed_page.wikitext),
        ]
        titles: list[str] = []
        for raw in candidates:
            if not raw:
                continue
            values = self._extract_link_titles(raw)
            if not values:
                values = re.split(r"\s*,\s*", self._normalize_plain_text(raw))
            expanded_values: list[str] = []
            for value in values:
                expanded_values.extend(re.split(r"\s*,\s*", self._normalize_plain_text(value)))
            titles.extend(
                normalized
                for normalized in (self._normalize_character_quest_title(value) for value in expanded_values)
                if normalized
            )
        return self._dedupe(titles)

    def _resolve_character_quest_context(
        self,
        series_context: Mapping[str, Any],
        *,
        title: str,
        related_quest: str,
        chapter_name: str,
    ) -> dict[str, str]:
        """按页面标题、所属任务和章名从列表页上下文回填章幕信息。"""
        candidates = [
            self._normalize_character_quest_title(related_quest),
            self._normalize_character_quest_title(title),
            self._normalize_character_quest_title(chapter_name),
        ]
        for key in candidates:
            normalized = self._normalize_plain_text(key).strip()
            if not normalized:
                continue
            value = series_context.get(normalized)
            if isinstance(value, dict):
                return value
        return {}

    def _extract_character_quest_flow_titles(
        self,
        sections: Sequence[ParsedSection],
        wikitext: str,
    ) -> list[str]:
        """提取角色任务页面里的流程标题。"""
        flow_sections = self._extract_event_quest_flow_sections_from_wikitext(wikitext)
        if flow_sections:
            return [title for title, _ in flow_sections]
        flow_text = self._find_section_text(sections, ("任务流程",))
        flow_titles = self._extract_list_items(flow_text)
        if flow_titles:
            return flow_titles
        plot_index = next(
            (
                index
                for index, section in enumerate(sections)
                if self._is_event_quest_plot_section_title(section.title)
            ),
            -1,
        )
        if plot_index == -1:
            return []
        fallback_titles: list[str] = []
        for section in sections[plot_index + 1 :]:
            title = self._normalize_text(section.title)
            if not title:
                continue
            if title in _CHARACTER_QUEST_SECTION_BOUNDARIES and fallback_titles:
                break
            fallback_titles.append(title)
        return fallback_titles

    def _extract_character_quest_dialogues(
        self,
        sections: Sequence[ParsedSection],
        flow_titles: Sequence[str],
        wikitext: str,
    ) -> list[ArchonQuestDialogue]:
        """按流程提取角色任务页的平铺对白。"""
        flow_sections = self._extract_event_quest_flow_sections(sections, flow_titles, wikitext=wikitext)
        dialogues: list[ArchonQuestDialogue] = []
        for task_flow, text in flow_sections:
            for entry in self._parse_event_quest_dialogue_entries(text):
                if entry.type == "选项":
                    dialogues.extend(
                        [
                            ArchonQuestDialogue(
                                speaker="",
                                text=option,
                                dialogue_type="option",
                                task_flow=task_flow,
                            )
                            for option in entry.options
                            if option
                        ]
                    )
                    continue
                dialogue_type = "character"
                if entry.type == "旅行者":
                    dialogue_type = "traveler"
                elif entry.type == "旁白":
                    dialogue_type = "narration"
                content = entry.content.strip()
                if not content:
                    continue
                dialogues.append(
                    ArchonQuestDialogue(
                        speaker=entry.speaker,
                        text=content,
                        dialogue_type=dialogue_type,
                        task_flow=task_flow,
                    )
                )
        return dialogues

    def _extract_archon_dialogues(
        self,
        raw: str,
        sections: Sequence[ParsedSection],
        *,
        wikitext: str = "",
    ) -> list[ArchonQuestDialogue]:
        """Extract ordered archon-quest dialogue lines from raw fields and sections."""
        raw_blocks: list[tuple[str, str]] = []
        plain_blocks: list[tuple[str, str]] = []
        normalized_raw = self._normalize_text(raw)
        if normalized_raw:
            raw_blocks.append(("", normalized_raw))

        for section in sections:
            title = self._normalize_plain_text(section.title)
            text = self._normalize_text(section.text)
            if not text:
                continue
            has_dialogue_title = any(keyword in title for keyword in ("剧情", "对话"))
            has_dialogue_markup = self._archon_block_has_dialogue_markup(text)
            if has_dialogue_title or has_dialogue_markup:
                plain_blocks.append((self._resolve_archon_dialogue_task_flow(title), text))

        for title, raw_text in self._extract_raw_sections(wikitext):
            normalized_title = self._normalize_plain_text(title)
            normalized_text = self._normalize_text(raw_text)
            if not normalized_text:
                continue
            plain_text = self._normalize_plain_text(raw_text)
            has_dialogue_title = any(keyword in normalized_title for keyword in ("剧情", "对话"))
            has_dialogue_markup = self._archon_block_has_dialogue_markup(plain_text) or any(
                token in normalized_text for token in ("{{选项", "{{剧情选项")
            )
            if has_dialogue_title or has_dialogue_markup:
                raw_blocks.append((self._resolve_archon_dialogue_task_flow(normalized_title), normalized_text))

        dialogues: list[ArchonQuestDialogue] = []
        seen: set[tuple[str, str, str, str]] = set()
        seen_blocks: set[tuple[str, str]] = set()
        for task_flow, block in raw_blocks:
            block_key = (task_flow, block)
            if block_key in seen_blocks:
                continue
            seen_blocks.add(block_key)
            self._append_archon_dialogues_from_plain_block(
                self._normalize_plain_text(self._expand_archon_option_templates(block)),
                dialogues,
                seen,
                task_flow=task_flow,
            )
        for task_flow, block in plain_blocks:
            block_key = (task_flow, block)
            if block_key in seen_blocks:
                continue
            seen_blocks.add(block_key)
            self._append_archon_dialogues_from_plain_block(block, dialogues, seen, task_flow=task_flow)
        return dialogues

    def _expand_archon_option_templates(self, raw: str) -> str:
        """Expand option templates into inline text so dialogue order is preserved."""
        expanded = self._normalize_text(raw)
        code = mwparserfromhell.parse(expanded)
        for template in code.filter_templates(recursive=True):
            if self._normalize_plain_text(str(template.name)).strip() not in {"选项", "剧情选项"}:
                continue
            option_values: dict[str, str] = {}
            selection_values: dict[str, str] = {}
            for param in getattr(template, "params", []):
                name = self._normalize_plain_text(str(param.name)).strip()
                value = self._normalize_text(str(param.value))
                if not name or not value:
                    continue
                option_match = re.fullmatch(r"选项(\d+)", name)
                if option_match:
                    option_values[option_match.group(1)] = value
                    continue
                selection_match = re.fullmatch(r"(?:选择|剧情)(\d+)", name)
                if selection_match:
                    selection_values[selection_match.group(1)] = value
            ordered_keys = sorted({*option_values.keys(), *selection_values.keys()}, key=int)
            replacement_lines: list[str] = []
            for key in ordered_keys:
                option_text = option_values.get(key, "").strip()
                if option_text:
                    replacement_lines.append(f"选项：{option_text}")
                selection_text = selection_values.get(key, "")
                if selection_text:
                    replacement_lines.append(selection_text)
            expanded = expanded.replace(str(template), "\n".join(replacement_lines), 1)
        return expanded

    def _append_archon_dialogues_from_plain_block(
        self,
        block: str,
        dialogues: list[ArchonQuestDialogue],
        seen: set[tuple[str, str, str, str]],
        *,
        task_flow: str = "",
    ) -> None:
        """Parse one plain-text dialogue block into structured lines."""
        for raw_line in self._normalize_text(block).splitlines():
            self._append_archon_dialogue_line(raw_line, dialogues, seen, task_flow=task_flow)

    def _append_archon_dialogue_line(
        self,
        line: str,
        dialogues: list[ArchonQuestDialogue],
        seen: set[tuple[str, str, str, str]],
        *,
        default_type: str = "narration",
        task_flow: str = "",
    ) -> None:
        """Append one normalized archon dialogue line when it is unique."""
        line = line.strip().lstrip("*#;").strip()
        if not line or line in {"----", "<hr>", "<hr/>", "<hr />"}:
            return

        option_match = _ARCHON_OPTION_LINE_PATTERN.match(line)
        if option_match:
            text = self._normalize_plain_text(option_match.group("text")).strip()
            if text:
                key = ("", text, "option", task_flow)
                if key not in seen:
                    seen.add(key)
                    dialogues.append(
                        ArchonQuestDialogue(speaker="", text=text, dialogue_type="option", task_flow=task_flow)
                    )
            return

        speaker, text = self._split_archon_dialogue_line(line)
        if speaker and text:
            dialogue_type = "traveler" if speaker in _ARCHON_TRAVELER_SPEAKERS else "character"
            key = (speaker, text, dialogue_type, task_flow)
            if key not in seen:
                seen.add(key)
                dialogues.append(
                    ArchonQuestDialogue(
                        speaker=speaker,
                        text=text,
                        dialogue_type=dialogue_type,
                        task_flow=task_flow,
                    )
                )
            return

        narration = self._normalize_plain_text(line).strip()
        if narration:
            key = ("", narration, default_type, task_flow)
            if key not in seen:
                seen.add(key)
                dialogues.append(
                    ArchonQuestDialogue(
                        speaker="",
                        text=narration,
                        dialogue_type=default_type,
                        task_flow=task_flow,
                    )
                )

    def _split_archon_dialogue_line(self, line: str) -> tuple[str, str]:
        """Split one dialogue line into speaker/text when possible."""
        match = _ARCHON_DIALOGUE_LINE_PATTERN.match(line)
        if not match:
            return "", ""
        speaker = self._normalize_plain_text(match.group("speaker")).strip()
        text = self._normalize_plain_text(match.group("text")).strip()
        return speaker, text

    def _archon_block_has_dialogue_markup(self, text: str) -> bool:
        """Check whether a block contains dialogue or option lines."""
        normalized = self._normalize_text(text)
        plain_text = self._normalize_plain_text(text)
        return bool(
            _ARCHON_DIALOGUE_SPEAKER_PATTERN.search(normalized)
            or re.search(r"^(?:选项(?:分支)?\d*|分支\d*|选项)\s*[：:]", plain_text, re.MULTILINE)
            or any(token in normalized for token in ("{{选项", "{{剧情选项"))
        )

    def _resolve_archon_dialogue_task_flow(self, title: str) -> str:
        """Map dialogue-section titles to their parent task-flow label."""
        normalized_title = self._normalize_plain_text(title).strip()
        if normalized_title in {"", "简介", "任务剧情", "剧情", "对话"}:
            return ""
        return normalized_title

    def _extract_archon_dialogue_speakers(self, sections: Sequence[ParsedSection]) -> list[str]:
        """Collect unique named speakers from dialogue sections."""
        speakers: list[str] = []
        for section in sections:
            for match in _ARCHON_DIALOGUE_SPEAKER_PATTERN.findall(section.text):
                speaker = self._normalize_plain_text(match).strip()
                if speaker:
                    speakers.append(speaker)
        return self._unique_preserve_order(speakers)

    def _resolve_archon_english_title(
        self,
        templates: dict[str, list[dict[str, str]]],
        *,
        preferred_params: dict[str, str] | None = None,
        wikitext: str | None = None,
    ) -> str:
        """Resolve archon quest english titles across the wiki's inconsistent field names."""
        explicit = self._resolve_value(
            templates,
            ("任务英文名", "系列任务英文名", "英文标题", "英文名", "TitleEN", "titleEN", "EN", "en"),
            preferred_params=preferred_params,
            wikitext=wikitext,
        )
        if explicit:
            return explicit
        if preferred_params:
            value = self._find_archon_param_value(preferred_params, self._is_archon_english_param)
            if value:
                return value
        for items in templates.values():
            for params in items:
                value = self._find_archon_param_value(params, self._is_archon_english_param)
                if value:
                    return value
        return ""

    def _find_archon_param_value(
        self,
        params: Mapping[str, str],
        predicate: Any,
    ) -> str:
        """Return the first plain-text template value whose name matches the predicate."""
        for name, raw_value in params.items():
            if not predicate(name):
                continue
            value = self._normalize_plain_text(raw_value)
            if value:
                return value
        return ""

    def _is_archon_english_param(self, name: str) -> bool:
        """Check whether a template parameter likely stores an english archon title."""
        normalized = self._normalize_plain_text(name).replace(" ", "")
        lowered = normalized.lower()
        if normalized in {"英文", "英文标题", "英文名"}:
            return True
        if "英文" in normalized and any(keyword in normalized for keyword in ("任务", "标题", "名称", "名")):
            return True
        return lowered.endswith("en") or lowered in {"en", "titleen", "nameen", "questtitleen"}

    def _extract_archon_references(
        self,
        raw: str,
        *,
        series_context: Mapping[str, Any],
    ) -> list[ArchonQuestReference]:
        """Extract structured quest references for prerequisite/follow-up fields."""
        references: list[ArchonQuestReference] = []
        seen: set[tuple[str, str, str]] = set()
        for chunk in self._split_archon_reference_chunks(raw):
            reference = self._parse_archon_reference(chunk, series_context=series_context)
            if reference is None:
                continue
            key = (reference.title, reference.chapter, reference.act)
            if key in seen:
                continue
            seen.add(key)
            references.append(reference)
        return references

    def _split_archon_reference_chunks(self, raw: str) -> list[str]:
        """Split raw relation fields into stable chunks while preserving wikilinks."""
        if not raw:
            return []
        chunks: list[str] = []
        for line in self._normalize_text(raw).splitlines():
            stripped = line.strip().lstrip("*#:").strip()
            if not stripped:
                continue
            for chunk in self._split_archon_chunks_preserving_links(stripped):
                cleaned = chunk.strip()
                if cleaned:
                    chunks.append(cleaned)
        if chunks:
            return chunks
        return self._split_archon_chunks_preserving_links(self._normalize_text(raw))

    def _parse_archon_reference(
        self,
        raw: str,
        *,
        series_context: Mapping[str, Any],
    ) -> ArchonQuestReference | None:
        """Parse one quest relation into title/chapter/act fields."""
        plain = self._strip_archon_list_prefix(self._normalize_plain_text(raw).strip())
        if not plain:
            return None
        title = self._extract_archon_reference_title(raw, plain)
        chapter, act = self._extract_archon_chapter_act_tokens(plain)
        if not title:
            title = self._clean_archon_reference_title(plain, chapter=chapter, act=act)
        if not title:
            return None
        mapped_chapter, mapped_act, _, _ = self._lookup_archon_series_context(series_context, title)
        return ArchonQuestReference(
            title=title,
            chapter=chapter or mapped_chapter,
            act=act or mapped_act,
        )

    def _extract_archon_reference_title(self, raw: str, plain: str) -> str:
        """Extract the most likely quest title from one relation chunk."""
        code = mwparserfromhell.parse(raw)
        for wikilink in code.filter_wikilinks(recursive=True):
            title = self._normalize_plain_text(str(wikilink.title)).strip()
            if title and not title.startswith(_FILE_LINK_PREFIXES):
                return title
        quoted_match = _ARCHON_QUOTED_TITLE_PATTERN.search(plain)
        if quoted_match:
            return self._normalize_plain_text(quoted_match.group("title")).strip()
        return self._clean_archon_reference_title(plain, chapter="", act="")

    def _extract_archon_chapter_act_tokens(self, value: str) -> tuple[str, str]:
        """Extract chapter/act tokens without treating bare page titles as chapters."""
        normalized = re.sub(r"\s+", " ", self._normalize_plain_text(value)).strip()
        if not normalized:
            return "", ""
        heading_info = self._extract_archon_heading_parts(normalized)
        if not heading_info["chapter"]:
            for special_chapter in _ARCHON_SPECIAL_CHAPTERS:
                if special_chapter in normalized:
                    heading_info["chapter"] = special_chapter
                    break
        return heading_info["chapter"], heading_info["act"]

    def _lookup_archon_series_context(
        self,
        series_context: Mapping[str, Any],
        key: str,
    ) -> tuple[str, str, str, str]:
        """Read one context entry while remaining compatible with old 2-tuples."""
        raw_value = series_context.get(key)
        if raw_value is None:
            return "", "", "", ""
        if isinstance(raw_value, Mapping):
            return (
                self._normalize_plain_text(raw_value.get("chapter", "")),
                self._normalize_plain_text(raw_value.get("act", "")),
                self._normalize_plain_text(raw_value.get("chapter_name", "")),
                self._normalize_plain_text(raw_value.get("act_name", "")),
            )
        if isinstance(raw_value, Sequence) and not isinstance(raw_value, (str, bytes)):
            values = list(raw_value)
            chapter = self._normalize_plain_text(values[0]) if len(values) >= 1 else ""
            act = self._normalize_plain_text(values[1]) if len(values) >= 2 else ""
            chapter_name = self._normalize_plain_text(values[2]) if len(values) >= 3 else ""
            act_name = self._normalize_plain_text(values[3]) if len(values) >= 4 else ""
            return chapter, act, chapter_name, act_name
        return "", "", "", ""

    def _split_archon_chunks_preserving_links(self, raw: str) -> list[str]:
        """Split comma-delimited relation text without breaking wikilink titles."""
        chunks: list[str] = []
        current: list[str] = []
        link_depth = 0
        index = 0
        while index < len(raw):
            pair = raw[index:index + 2]
            if pair == "[[":
                link_depth += 1
                current.append(pair)
                index += 2
                continue
            if pair == "]]" and link_depth > 0:
                link_depth -= 1
                current.append(pair)
                index += 2
                continue
            char = raw[index]
            if link_depth == 0 and char in {"\n", "、", "，", ","}:
                chunk = "".join(current).strip()
                if chunk:
                    chunks.append(chunk)
                current = []
                index += 1
                continue
            current.append(char)
            index += 1
        chunk = "".join(current).strip()
        if chunk:
            chunks.append(chunk)
        return chunks

    def _clean_archon_reference_title(self, value: str, *, chapter: str, act: str) -> str:
        """Remove contextual chapter/act markers and wrappers from a quest reference."""
        cleaned = self._strip_archon_list_prefix(value)
        if chapter:
            cleaned = cleaned.replace(chapter, "", 1)
        if act:
            cleaned = cleaned.replace(act, "", 1)
        cleaned = re.sub(r"[「」『』“”\"'（）()【】\[\]]", "", cleaned)
        return cleaned.strip(" ·．•-—:：")

    def _extract_archon_list(self, raw: str) -> list[str]:
        """Normalize bullet lists and comma-delimited page fields."""
        if not raw:
            return []
        values: list[str] = []
        for line in self._normalize_text(raw).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            stripped = stripped.lstrip("*#:").strip()
            if not stripped:
                continue
            for chunk in _ARCHON_SPLIT_PATTERN.split(stripped):
                cleaned = self._normalize_plain_text(chunk).strip()
                cleaned = self._strip_archon_list_prefix(cleaned)
                if cleaned:
                    values.append(cleaned)
        if values:
            return self._unique_preserve_order(values)
        plain_text = self._normalize_plain_text(raw)
        parts = [self._strip_archon_list_prefix(chunk.strip()) for chunk in _ARCHON_SPLIT_PATTERN.split(plain_text)]
        return self._unique_preserve_order([part for part in parts if part])
    def _strip_archon_list_prefix(self, value: str) -> str:
        """Remove verbose quest-field prefixes while preserving page names."""
        cleaned = value.strip().strip("：:")
        for prefix in ("完成前置任务", "完成魔神任务", "完成任务", "魔神任务", "前置任务"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip("：: ")
        return cleaned
    def _extract_chronicle_records(self, page_title: str, wikitext: str) -> list[ChronicleRecord]:
        """按标题层级、项目时间与条目顺序抽取编年史记录。"""
        records: list[ChronicleRecord] = []
        heading_stack: dict[int, str] = {}
        section_lines: list[str] = []
        section_bullets: list[str] = []
        section_raw_fragments: list[str] = []
        item_year = ""
        item_lines: list[str] = []
        item_bullets: list[str] = []
        item_raw_fragments: list[str] = []
        started = False

        def append_line(buffer: list[str], raw_fragments: list[str], value: str) -> None:
            stripped = value.strip()
            if not stripped:
                if buffer and buffer[-1] != "":
                    buffer.append("")
                return
            buffer.append(value)
            raw_fragments.append(value)

        def append_bullet(buffer: list[str], raw_fragments: list[str], value: str) -> None:
            stripped = value.strip()
            if not stripped:
                return
            buffer.append(value)
            raw_fragments.append(value)

        def flush_section() -> None:
            nonlocal section_lines, section_bullets, section_raw_fragments
            record = self._build_chronicle_record(
                page_title,
                self._current_chronicle_path(heading_stack),
                "",
                section_lines,
                section_bullets,
                section_raw_fragments,
            )
            if record is not None:
                records.append(record)
            section_lines = []
            section_bullets = []
            section_raw_fragments = []

        def flush_item() -> None:
            nonlocal item_year, item_lines, item_bullets, item_raw_fragments
            record = self._build_chronicle_record(
                page_title,
                self._current_chronicle_path(heading_stack),
                item_year,
                item_lines,
                item_bullets,
                item_raw_fragments,
            )
            if record is not None:
                records.append(record)
            item_year = ""
            item_lines = []
            item_bullets = []
            item_raw_fragments = []

        for raw_line in wikitext.splitlines():
            line = raw_line.strip()
            if not started:
                heading_match = _CHRONICLE_HEADING_PATTERN.match(line)
                bold_match = _CHRONICLE_BOLD_ITEM_PATTERN.match(line)
                bullet_match = _CHRONICLE_BULLET_PATTERN.match(line)
                if heading_match or bold_match or bullet_match:
                    started = True
                else:
                    continue
            if not line:
                if item_year or item_lines or item_bullets:
                    append_line(item_lines, item_raw_fragments, "")
                else:
                    append_line(section_lines, section_raw_fragments, "")
                continue
            if _CATEGORY_LINK_PATTERN.fullmatch(line):
                continue
            if line == "__NOEDITSECTION__":
                continue
            if _CHRONICLE_WRAPPER_TAG_PATTERN.fullmatch(line):
                continue

            heading_match = _CHRONICLE_HEADING_PATTERN.match(line)
            if heading_match:
                if item_year or item_lines or item_bullets:
                    flush_item()
                else:
                    flush_section()
                level = len(heading_match.group(1))
                title = self._clean_field_value(heading_match.group(2))
                heading_stack = {
                    existing_level: existing_title
                    for existing_level, existing_title in heading_stack.items()
                    if existing_level < level
                }
                if title:
                    heading_stack[level] = title
                continue

            bold_match = _CHRONICLE_BOLD_ITEM_PATTERN.match(line)
            if bold_match:
                if item_year or item_lines or item_bullets:
                    flush_item()
                else:
                    flush_section()
                item_year = self._clean_field_value(bold_match.group(1))
                remainder = bold_match.group(2) or ""
                append_line(item_lines, item_raw_fragments, remainder)
                continue

            bullet_match = _CHRONICLE_BULLET_PATTERN.match(line)
            if bullet_match:
                bullet_text = bullet_match.group(1)
                bullet_item = self._split_chronicle_bullet_item(bullet_text)
                if bullet_item is not None:
                    if item_year or item_lines or item_bullets:
                        flush_item()
                    elif section_lines or section_bullets:
                        flush_section()
                    item_year = bullet_item["year"]
                    append_line(item_lines, item_raw_fragments, bullet_item["content"])
                    continue
                if item_year or item_lines or item_bullets:
                    append_bullet(item_bullets, item_raw_fragments, bullet_text)
                else:
                    append_bullet(section_bullets, section_raw_fragments, bullet_text)
                continue

            if item_year or item_lines or item_bullets:
                append_line(item_lines, item_raw_fragments, raw_line)
            else:
                append_line(section_lines, section_raw_fragments, raw_line)

        if item_year or item_lines or item_bullets:
            flush_item()
        else:
            flush_section()
        return records

    def _build_chronicle_record(
        self,
        page_title: str,
        heading_path: list[str],
        year: str,
        lines: list[str],
        bullets: list[str],
        raw_fragments: list[str],
    ) -> ChronicleRecord | None:
        """将一个编年史片段转换为结构化记录。"""
        cleaned_year = self._clean_field_value(year)
        cleaned_path = [self._clean_field_value(item) for item in heading_path if self._clean_field_value(item)]
        if not cleaned_year and cleaned_path and self._looks_like_chronicle_year(cleaned_path[-1]):
            cleaned_year = cleaned_path[-1]
            cleaned_path = cleaned_path[:-1]

        background = self._clean_field_value("\n".join(lines), context="story")
        major_events = self._extract_chronicle_major_events(bullets, background)
        if not cleaned_year and not bullets:
            major_events = []
        faction_changes = self._extract_chronicle_faction_changes(major_events, background)
        related_characters = self._extract_chronicle_related_characters("\n".join(raw_fragments))
        era_name = " / ".join(cleaned_path) or page_title

        if not any((cleaned_year, background, major_events, faction_changes, related_characters)):
            return None
        return ChronicleRecord(
            era_name=era_name,
            year=cleaned_year,
            major_events=major_events,
            faction_changes=faction_changes,
            related_characters=related_characters,
            background=background,
        )

    def _current_chronicle_path(self, heading_stack: dict[int, str]) -> list[str]:
        """返回当前编年史标题路径。"""
        return [heading_stack[level] for level in sorted(heading_stack)]

    def _extract_chronicle_sections(
        self,
        page_title: str,
        wikitext: str,
    ) -> tuple[str, list[ChronicleSectionRecord]]:
        """鎸夌珷鑺傘€侀」鐩€佹潯鐩拰姝ｆ枃鏋勫缓缂栧勾鍙茬珷鑺傛爲銆?"""
        sections: list[ChronicleSectionRecord] = []
        page_intro_lines: list[str] = []
        section_stack: list[tuple[int, ChronicleSectionRecord]] = []
        section_buffers: dict[int, list[str]] = {}
        current_item: ChronicleItemRecord | None = None
        current_item_content_lines: list[str] = []
        current_item_entry_lines: list[str] = []
        current_item_raw_fragments: list[str] = []
        started = False

        def append_line(buffer: list[str], value: str) -> None:
            stripped = value.strip()
            if not stripped:
                if buffer and buffer[-1] != "":
                    buffer.append("")
                return
            buffer.append(value)

        def append_non_empty(buffer: list[str], value: str) -> None:
            if value.strip():
                buffer.append(value)

        def finalize_text(lines: list[str]) -> str:
            return self._clean_field_value("\n".join(lines), context="story")

        def current_section() -> ChronicleSectionRecord | None:
            if not section_stack:
                return None
            return section_stack[-1][1]

        def ensure_root_section() -> ChronicleSectionRecord:
            section = current_section()
            if section is not None:
                return section
            synthetic = ChronicleSectionRecord(title=page_title, level=0)
            sections.append(synthetic)
            section_stack.append((0, synthetic))
            section_buffers[id(synthetic)] = []
            return synthetic

        def close_sections(min_level: int) -> None:
            while section_stack and section_stack[-1][0] >= min_level:
                _, section = section_stack.pop()
                section.content = finalize_text(section_buffers.pop(id(section), []))

        def flush_item() -> None:
            nonlocal current_item, current_item_content_lines, current_item_entry_lines, current_item_raw_fragments
            if current_item is None:
                return
            current_item.content = finalize_text(current_item_content_lines)
            current_item.entries = self._dedupe(
                [
                    cleaned
                    for raw_entry in current_item_entry_lines
                    if (cleaned := self._clean_field_value(raw_entry, context="story"))
                ]
            )
            current_item.related_characters = self._extract_chronicle_related_characters(
                "\n".join(current_item_raw_fragments)
            )
            if not any(
                (
                    self._clean_field_value(current_item.title),
                    current_item.content,
                    current_item.entries,
                    current_item.related_characters,
                )
            ):
                section = current_section()
                if section is not None and current_item in section.items:
                    section.items.remove(current_item)
            current_item = None
            current_item_content_lines = []
            current_item_entry_lines = []
            current_item_raw_fragments = []

        def open_section(level: int, title: str) -> None:
            clean_title = self._clean_field_value(title)
            if not clean_title:
                return
            close_sections(level)
            section = ChronicleSectionRecord(title=clean_title, level=level)
            if section_stack:
                section_stack[-1][1].subsections.append(section)
            else:
                sections.append(section)
            section_stack.append((level, section))
            section_buffers[id(section)] = []

        def start_item(title: str, initial_content: str = "") -> None:
            nonlocal current_item, current_item_content_lines, current_item_entry_lines, current_item_raw_fragments
            clean_title = self._clean_field_value(title)
            if not clean_title:
                return
            item = ChronicleItemRecord(title=clean_title)
            ensure_root_section().items.append(item)
            current_item = item
            current_item_content_lines = []
            current_item_entry_lines = []
            current_item_raw_fragments = []
            if initial_content:
                append_line(current_item_content_lines, initial_content)
                append_non_empty(current_item_raw_fragments, initial_content)

        for raw_line in wikitext.splitlines():
            line = raw_line.strip()
            heading_match = _CHRONICLE_HEADING_PATTERN.match(line)
            bold_match = _CHRONICLE_BOLD_ITEM_PATTERN.match(line)
            bullet_match = _CHRONICLE_BULLET_PATTERN.match(line)

            if not started:
                if heading_match or bold_match or bullet_match:
                    started = True
                else:
                    continue

            if not line:
                if current_item is not None:
                    append_line(current_item_content_lines, "")
                elif section_stack:
                    append_line(section_buffers[id(section_stack[-1][1])], "")
                else:
                    append_line(page_intro_lines, "")
                continue
            if _CATEGORY_LINK_PATTERN.fullmatch(line):
                continue
            if line == "__NOEDITSECTION__":
                continue
            if _CHRONICLE_WRAPPER_TAG_PATTERN.fullmatch(line):
                continue

            if heading_match:
                flush_item()
                open_section(len(heading_match.group(1)), heading_match.group(2))
                continue

            if bold_match:
                flush_item()
                start_item(bold_match.group(1), bold_match.group(2) or "")
                continue

            if bullet_match:
                bullet_text = bullet_match.group(1)
                bullet_item = self._split_chronicle_bullet_item(bullet_text)
                if bullet_item is not None:
                    flush_item()
                    start_item(bullet_item["year"], bullet_item["content"])
                    continue
                if current_item is not None:
                    append_non_empty(current_item_entry_lines, bullet_text)
                    append_non_empty(current_item_raw_fragments, bullet_text)
                elif section_stack:
                    append_line(section_buffers[id(section_stack[-1][1])], f"* {bullet_text}")
                else:
                    append_line(page_intro_lines, f"* {bullet_text}")
                continue

            if current_item is not None:
                append_line(current_item_content_lines, raw_line)
                append_non_empty(current_item_raw_fragments, raw_line)
            elif section_stack:
                append_line(section_buffers[id(section_stack[-1][1])], raw_line)
            else:
                append_line(page_intro_lines, raw_line)

        flush_item()
        close_sections(0)
        return finalize_text(page_intro_lines), sections

    def _extract_chronicle_major_events(self, bullets: list[str], background: str) -> list[str]:
        """优先使用列表项提取重大事件；否则保留正文为单条事件。"""
        cleaned_bullets = self._dedupe(
            [
                self._clean_field_value(item, context="story")
                for item in bullets
                if self._clean_field_value(item, context="story")
            ]
        )
        if cleaned_bullets:
            return cleaned_bullets
        if background:
            return [background]
        return []

    def _extract_chronicle_faction_changes(self, events: list[str], background: str) -> list[str]:
        """提取包含势力、统治、政权等关键词的句子。"""
        candidates: list[str] = []
        for event in events:
            event_sentences = self._split_chronicle_sentences(event)
            candidates.extend(event_sentences or [event])
        candidates.extend(self._split_chronicle_sentences(background))
        return self._dedupe(
            [
                candidate
                for candidate in candidates
                if any(keyword in candidate for keyword in _CHRONICLE_FACTION_KEYWORDS)
            ]
        )

    def _extract_chronicle_related_characters(self, raw_text: str) -> list[str]:
        """从编年史片段中的内部链接提取相关人物候选。"""
        if not raw_text.strip():
            return []
        names: list[str] = []
        code = mwparserfromhell.parse(raw_text)
        for wikilink in code.filter_wikilinks(recursive=True):
            title = str(wikilink.title).strip().split("#", 1)[0].strip()
            if not title or any(title.startswith(prefix) for prefix in _FILE_LINK_PREFIXES):
                continue
            if ":" in title:
                continue
            cleaned = self._clean_field_value(title)
            if cleaned:
                names.append(cleaned)
        return self._dedupe(names)

    def _split_chronicle_sentences(self, text: str) -> list[str]:
        """按句号、问号、感叹号切分编年史正文。"""
        if not text:
            return []
        return [sentence.strip() for sentence in re.split(r"(?<=[。！？])\s*", text) if sentence.strip()]

    def _split_chronicle_bullet_item(self, bullet_text: str) -> dict[str, str] | None:
        """将 `*时间  内容` 形式的公元纪条目拆分为时间与正文。"""
        cleaned = bullet_text.strip()
        if not cleaned:
            return None
        match = _CHRONICLE_BULLET_ITEM_PATTERN.match(cleaned)
        if not match:
            return None
        year = self._clean_field_value(match.group("year"))
        content = match.group("content").strip()
        if not year or not self._looks_like_chronicle_year(year):
            return None
        return {
            "year": year,
            "content": content,
        }

    def _looks_like_chronicle_year(self, value: str) -> bool:
        """判断标题是否更像是年代/时间标签而非纪年名称。"""
        normalized = value.strip()
        if not normalized:
            return False
        if re.search(r"\d", normalized):
            return True
        if normalized.startswith("公元"):
            return True
        return any(token in normalized for token in ("年前", "年后", "元年", "次年", "翌年", "同年", "当年"))

    def _extract_event_page_context(
        self,
        payload: dict[str, Any],
        *,
        fallback_event_name: str,
        fallback_event_period: str,
    ) -> tuple[str, str, list[str], str]:
        """提取活动页面上下文信息。"""
        parsed_page = self.parse_page(payload)
        main_template = self._select_best_template_by_fields(
            parsed_page.templates,
            (
                ("活动名称", "名称"),
                ("开始时间", "时间", "活动时间", "活动期间"),
                ("结束时间",),
                ("活动描述", "描述", "介绍"),
            ),
        )
        event_name = self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                ("活动名称", "名称"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            parsed_page.title,
            fallback_event_name,
        )
        event_period = self._coalesce(
            self._resolve_event_period(
                parsed_page.templates,
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            fallback_event_period,
        )
        event_description = self._coalesce(
            self._resolve_value(
                parsed_page.templates,
                ("活动描述", "描述", "介绍"),
                preferred_params=main_template,
                wikitext=parsed_page.wikitext,
            ),
            self._extract_first_non_empty_line(
                self._find_section_text(parsed_page.sections, ("活动说明", "活动介绍", "简介"))
            ),
            parsed_page.summary,
        )
        return (
            event_name,
            event_period,
            self._extract_event_page_quest_titles(parsed_page.wikitext),
            event_description,
        )

    def _resolve_event_period(
        self,
        templates: dict[str, list[dict[str, str]]],
        *,
        preferred_params: dict[str, str] | None = None,
        wikitext: str | None = None,
    ) -> str:
        """提取任务或活动的时间区间。"""
        direct_period = self._resolve_value(
            templates,
            ("时间", "活动时间", "活动期间"),
            preferred_params=preferred_params,
            wikitext=wikitext,
        )
        if direct_period:
            return direct_period
        start_time = self._resolve_value(
            templates,
            ("开始时间", "开始日期"),
            preferred_params=preferred_params,
            wikitext=wikitext,
        )
        end_time = self._resolve_value(
            templates,
            ("结束时间", "结束日期"),
            preferred_params=preferred_params,
            wikitext=wikitext,
        )
        if start_time and end_time:
            return f"{start_time} ~ {end_time}"
        return start_time or end_time

    def _extract_event_quest_description(self, sections: Sequence[ParsedSection]) -> str:
        """从任务剧情摘要中提取任务描述。"""
        plot_text = self._find_section_text(sections, ("任务剧情", "剧情"))
        for line in self._normalize_text(plot_text).splitlines():
            cleaned = self._strip_list_marker(line).lstrip("> ").strip()
            if cleaned:
                return cleaned
        return ""

    def _extract_event_page_quest_titles(self, wikitext: str) -> list[str]:
        """从活动页面提取剧情任务列表。"""
        raw = self._extract_section_wikitext(wikitext, ("活动剧情", "剧情任务", "任务列表"))
        if raw:
            titles = [
                title
                for title in self._extract_link_titles(raw)
                if self._looks_like_quest_title(title)
            ]
            if titles:
                return titles
            plain_text = self._normalize_plain_text(raw)
            return [
                title
                for title in self._extract_list_items(plain_text, dedupe=True)
                if self._looks_like_quest_title(title)
            ]
        return []

    def _extract_event_quest_flow_titles(
        self,
        sections: Sequence[ParsedSection],
        wikitext: str,
    ) -> list[str]:
        """提取任务流程标题列表。"""
        flow_sections = self._extract_event_quest_flow_sections_from_wikitext(wikitext)
        if flow_sections:
            return [title for title, _ in flow_sections]
        flow_text = self._find_section_text(sections, ("任务流程",))
        flow_titles = self._extract_list_items(flow_text)
        if flow_titles:
            return flow_titles
        plot_index = next(
            (
                index
                for index, section in enumerate(sections)
                if self._is_event_quest_plot_section_title(section.title)
            ),
            -1,
        )
        if plot_index == -1:
            return []
        fallback_titles: list[str] = []
        for section in sections[plot_index + 1:]:
            title = self._normalize_text(section.title)
            if not title:
                continue
            if title in _EVENT_QUEST_SECTION_BOUNDARIES and fallback_titles:
                break
            fallback_titles.append(title)
        return fallback_titles

    def _extract_event_quest_dialogue(
        self,
        sections: Sequence[ParsedSection],
        quest_titles: Sequence[str],
        wikitext: str,
    ) -> list[EventQuestStepRecord]:
        """按流程提取活动任务对话。"""
        flow_sections = self._extract_event_quest_flow_sections(sections, quest_titles, wikitext=wikitext)
        return [
            EventQuestStepRecord(title=title, dialogue=self._parse_event_quest_dialogue_entries(text))
            for title, text in flow_sections
        ]

    def _extract_event_quest_flow_sections(
        self,
        sections: Sequence[ParsedSection],
        quest_titles: Sequence[str],
        *,
        wikitext: str = "",
    ) -> list[tuple[str, str]]:
        """根据任务流程标题匹配剧情子章节。"""
        flow_sections = self._extract_event_quest_flow_sections_from_wikitext(wikitext)
        if flow_sections:
            return flow_sections
        if not quest_titles:
            return []
        plot_index = next(
            (
                index
                for index, section in enumerate(sections)
                if self._is_event_quest_plot_section_title(section.title)
            ),
            -1,
        )
        if plot_index == -1:
            return [(title, "") for title in quest_titles]

        matched: list[tuple[str, str]] = []
        expected_index = 0
        for section in sections[plot_index + 1:]:
            if expected_index >= len(quest_titles):
                break
            title = self._normalize_text(section.title)
            if not title:
                continue
            if title == self._normalize_text(quest_titles[expected_index]):
                matched.append((quest_titles[expected_index], section.text))
                expected_index += 1
                continue
            if title in _EVENT_QUEST_SECTION_BOUNDARIES and matched:
                break
        while expected_index < len(quest_titles):
            matched.append((quest_titles[expected_index], ""))
            expected_index += 1
        return matched

    def _extract_event_quest_flow_sections_from_wikitext(self, wikitext: str) -> list[tuple[str, str]]:
        """直接从原始 wikitext 中提取任务剧情子章节，保留空流程与重复标题。"""
        if not wikitext:
            return []
        headings = self._iter_wikitext_headings(wikitext)
        if not headings:
            return []
        flow_sections: list[tuple[str, str]] = []
        for plot_heading in headings:
            if not self._is_event_quest_plot_section_title(plot_heading["title"]):
                continue
            block_end = len(wikitext)
            for candidate in headings:
                if candidate["start"] <= plot_heading["start"]:
                    continue
                if candidate["level"] <= plot_heading["level"]:
                    block_end = candidate["start"]
                    break
            block_headings = [
                heading
                for heading in headings
                if plot_heading["content_start"] <= heading["start"] < block_end and heading["level"] > plot_heading["level"]
            ]
            for index, heading in enumerate(block_headings):
                next_start = block_end if index + 1 >= len(block_headings) else block_headings[index + 1]["start"]
                raw_text = wikitext[heading["content_start"]:next_start].strip()
                flow_sections.append((heading["title"], self._normalize_event_quest_flow_text(raw_text)))
        return flow_sections

    def _iter_wikitext_headings(self, wikitext: str) -> list[dict[str, int | str]]:
        """遍历原始 wikitext 标题，保留层级与原始位置。"""
        headings: list[dict[str, int | str]] = []
        for match in _WIKITEXT_HEADING_PATTERN.finditer(wikitext):
            title = self._normalize_text(match.group("title"))
            if not title:
                continue
            headings.append(
                {
                    "title": title,
                    "level": len(match.group("marks")),
                    "start": match.start(),
                    "content_start": match.end(),
                }
            )
        return headings

    def _is_event_quest_plot_section_title(self, title: str) -> bool:
        """判断标题是否属于活动任务的剧情章节。"""
        normalized = self._normalize_text(title)
        return any(
            normalized == prefix or normalized.startswith(f"{prefix}·")
            for prefix in _EVENT_QUEST_PLOT_SECTION_PREFIXES
        )

    def _normalize_event_quest_flow_text(self, raw_text: str) -> str:
        """将任务剧情子章节的原始 wikitext 规范化为对话解析可消费的纯文本。"""
        if not raw_text:
            return ""
        expanded = _CATEGORY_LINK_PATTERN.sub("", raw_text)
        expanded = _BR_TAG_PATTERN.sub(_INLINE_BREAK_SENTINEL, expanded)
        expanded = self._expand_event_quest_wikitext(expanded)
        expanded = self._replace_phonetic_templates(expanded, "generic")
        expanded = self._replace_blackout_templates(expanded, "generic")
        plain_text = mwparserfromhell.parse(expanded).strip_code().strip()
        return self._normalize_text(str(plain_text))

    def _expand_event_quest_wikitext(self, text: str) -> str:
        """展开活动任务剧情中常见的模板，避免 strip_code 后丢失关键信息。"""
        expanded = text
        code = mwparserfromhell.parse(text)
        for template in code.filter_templates(recursive=True):
            replacement = self._render_event_quest_template(template)
            if replacement is None:
                continue
            expanded = expanded.replace(str(template), replacement, 1)
        return expanded

    def _render_event_quest_template(self, template: Any) -> str | None:
        """将活动任务剧情里的特定模板转为纯文本。"""
        name = self._normalize_text(str(template.name).strip())
        if name == "剧情选项":
            return self._render_event_quest_option_template(template)
        if name == "任务描述":
            return self._coalesce(
                self._template_param_value(template, 1, "1", "描述"),
                self._template_last_param_value(template),
            )
        if name == "折叠":
            return self._coalesce(
                self._template_param_value(template, "内容", 2, "2"),
                self._template_last_param_value(template),
            )
        if name == "颜色":
            return self._coalesce(
                self._template_param_value(template, "描述", "内容", 2, "2", 3, "3"),
                self._template_last_param_value(template),
            )
        if "人物对话" in name:
            speaker = self._coalesce(
                self._template_param_value(template, "角色", 2, "2"),
                self._template_param_value(template, 1, "1"),
            )
            content = self._coalesce(
                self._template_param_value(template, "内容", 3, "3"),
                self._template_last_param_value(template),
            )
            if speaker and content:
                return f"{speaker}：{content}"
            return content
        if name == "注音":
            return self._template_param_value(template, 1, "1")
        return None

    def _render_event_quest_option_template(self, template: Any) -> str:
        """展开 {{剧情选项}} 模板，保留选项和各分支对白。"""
        suffixes: set[int] = set()
        for param in template.params:
            match = re.fullmatch(r"(?:选项|剧情)(\d+)", str(param.name).strip())
            if match:
                suffixes.add(int(match.group(1)))
        if not suffixes:
            return ""
        option_lines: list[str] = []
        branch_texts: list[str] = []
        for index in sorted(suffixes):
            option = self._template_param_value(template, f"选项{index}")
            if option:
                option_lines.append(f"* {option}")
            branch_text = self._template_param_value(template, f"剧情{index}")
            if branch_text:
                branch_texts.append(branch_text)
        parts: list[str] = []
        if option_lines:
            parts.append("★")
            parts.extend(option_lines)
        parts.extend(branch_texts)
        return "\n".join(part for part in parts if part).strip()

    def _template_param_value(self, template: Any, *aliases: Any) -> str:
        """读取模板参数值。"""
        for alias in aliases:
            if not template.has(alias):
                continue
            return str(template.get(alias).value).strip()
        return ""

    def _template_last_param_value(self, template: Any) -> str:
        """读取模板最后一个参数值。"""
        if not template.params:
            return ""
        return str(template.params[-1].value).strip()

    def _parse_event_quest_dialogue_entries(self, text: str) -> list[EventQuestDialogueEntry]:
        """解析单个任务流程中的对话与旁白。"""
        normalized = self._normalize_text(text)
        if not normalized:
            return []
        entries: list[EventQuestDialogueEntry] = []
        pending_options: list[str] = []
        collecting_options = False

        for raw_line in normalized.splitlines():
            line = self._strip_list_marker(raw_line).lstrip("> ").strip()
            if not line:
                continue
            option_content, option_artifact = self._clean_event_quest_option_line(line)
            if line in _EVENT_QUEST_OPTION_MARKERS:
                collecting_options = True
                continue
            if option_artifact:
                collecting_options = True
                if option_content:
                    pending_options.append(option_content.replace(_INLINE_BREAK_SENTINEL, "\n"))
                continue
            if line in _EVENT_QUEST_IGNORED_LINES or line.startswith("额外对话"):
                if pending_options:
                    entries.append(EventQuestDialogueEntry(type="选项", options=list(pending_options)))
                    pending_options.clear()
                collecting_options = False
                continue
            speaker_content = self._split_event_quest_dialogue_line(line)
            if collecting_options and speaker_content is None:
                pending_options.append((option_content or line).replace(_INLINE_BREAK_SENTINEL, "\n"))
                continue
            if pending_options:
                entries.append(EventQuestDialogueEntry(type="选项", options=list(pending_options)))
                pending_options.clear()
                collecting_options = False
            if speaker_content is not None:
                speaker, content = speaker_content
                entries.append(
                    EventQuestDialogueEntry(
                        type="旅行者" if speaker == "旅行者" else "角色/NPC",
                        speaker=speaker,
                        content=content,
                    )
                )
                continue
            entries.append(EventQuestDialogueEntry(type="旁白", content=line.replace(_INLINE_BREAK_SENTINEL, "\n")))

        if pending_options:
            entries.append(EventQuestDialogueEntry(type="选项", options=list(pending_options)))
        return entries

    def _clean_event_quest_option_line(self, line: str) -> tuple[str, bool]:
        """移除剧情选项图标残留，仅保留选项文本。"""
        cleaned = line
        matched = False

        stripped = _EVENT_QUEST_OPTION_ICON_PATTERN.sub("", cleaned)
        if stripped != cleaned:
            cleaned = stripped
            matched = True

        stripped = _EVENT_QUEST_OPTION_SIZE_PATTERN.sub("", cleaned)
        if stripped != cleaned:
            cleaned = stripped
            matched = True

        return cleaned.strip(), matched or line.startswith("剧情选项")

    def _split_event_quest_dialogue_line(self, line: str) -> tuple[str, str] | None:
        """解析“角色：内容”格式的对话行。"""
        match = re.match(r"^([^：]+)：\s*(.+)$", line)
        if not match:
            return None
        speaker = match.group(1).strip()
        content = match.group(2).replace(_INLINE_BREAK_SENTINEL, "\n").strip()
        if not speaker or not content:
            return None
        return speaker, content

    def _extract_link_titles(self, raw: str) -> list[str]:
        """从原始字段中提取链接标题，回退到普通文本切分。"""
        if not raw:
            return []
        code = mwparserfromhell.parse(self._normalize_text(raw))
        titles: list[str] = []
        for wikilink in code.filter_wikilinks(recursive=True):
            title = self._normalize_plain_text(str(wikilink.title))
            if not title or title.startswith(_FILE_LINK_PREFIXES):
                continue
            titles.append(title)
        if titles:
            return self._unique_preserve_order(titles)
        plain_text = self._normalize_plain_text(raw)
        return self._extract_list_items(plain_text, dedupe=True)

    def _extract_list_items(self, text: str, *, dedupe: bool = False) -> list[str]:
        """将章节列表文本按行拆分为有序条目。"""
        normalized = self._normalize_text(text)
        items: list[str] = []
        for line in normalized.splitlines():
            cleaned = self._strip_list_marker(line).strip()
            if not cleaned:
                continue
            items.append(cleaned)
        return self._unique_preserve_order(items) if dedupe else items

    def _extract_first_list_item(self, text: str) -> str:
        """返回列表文本中的第一项。"""
        items = self._extract_list_items(text)
        return items[0] if items else ""

    def _extract_required_quest(self, text: str) -> str:
        """从任务条件文本中提取“完成任务 X”形式的前置任务。"""
        normalized = self._normalize_text(text)
        match = re.search(r"完成任务\s*(.+)", normalized)
        if not match:
            return ""
        return self._strip_quotes(self._strip_list_marker(match.group(1)).strip())

    def _strip_list_marker(self, line: str) -> str:
        """移除列表或引用前缀。"""
        return re.sub(r"^[>*#\-]+\s*", "", line).strip()

    def _extract_section_wikitext(self, wikitext: str, titles: Sequence[str]) -> str:
        """从原始 wikitext 中提取指定标题对应的章节。"""
        for title in titles:
            for match in _WIKITEXT_HEADING_PATTERN.finditer(wikitext):
                heading_title = self._normalize_text(match.group("title")).strip()
                if heading_title != title.strip():
                    continue
                level = len(match.group("marks"))
                start = match.end()
                end = len(wikitext)
                for next_match in _WIKITEXT_HEADING_PATTERN.finditer(wikitext, start):
                    if len(next_match.group("marks")) <= level:
                        end = next_match.start()
                        break
                return wikitext[start:end].strip()
        return ""

    def _looks_like_quest_title(self, title: str) -> bool:
        """过滤活动剧情中的奖励条目，仅保留疑似任务标题。"""
        normalized = self._normalize_plain_text(title)
        if not normalized:
            return False
        if any(token in normalized for token in _EVENT_QUEST_REWARD_TOKENS):
            return False
        if re.search(r"[×xX]\s*\d+$", normalized):
            return False
        return True

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
        stripped = text.strip()
        for left, right in (("「", "」"), ("\"", "\""), ("'", "'")):
            if stripped.startswith(left) and stripped.endswith(right) and len(stripped) >= len(left) + len(right):
                return stripped[len(left) : len(stripped) - len(right)].strip()
        return stripped

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
