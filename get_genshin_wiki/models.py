"""
核心数据模型定义
================

本模块定义了项目中使用的数据类（dataclass），用于表示从 Wiki 获取或解析后的各种数据结构。

数据模型层次
------------
- RequestPolicy   : HTTP 请求策略配置（不可变对象）
- WikiPage        : MediaWiki API 返回的原始页面数据
- ParsedSection   : 从 wikitext 中提取的单个章节
- ParsedPage      : 通用页面解析结果
- CharacterRecord : 角色页面专用解析结果

使用示例
--------
    from get_genshin_wiki.models import WikiPage, ParsedPage

    page = WikiPage(title="哥伦比娅", page_id=123, wikitext="{{角色}}", raw_payload={})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# HTTP 请求策略配置（不可变对象）
@dataclass(frozen=True)
class RequestPolicy:
    """
    HTTP 请求行为控制配置。

    此类实例不可变（frozen=True），创建后字段不可修改。

    属性
    ----
    user_agent : str
        HTTP User-Agent 头信息
    timeout_seconds : float
        单次请求超时时间（秒）
    throttle_seconds : float
        请求间最小间隔时间（秒）
    max_retries : int
        请求失败最大重试次数，默认为 2
    """

    user_agent: str
    timeout_seconds: float
    throttle_seconds: float
    max_retries: int = 2


# MediaWiki API 返回的原始页面数据
@dataclass
class WikiPage:
    """
    MediaWiki API 返回的原始页面内容。

    属性
    ----
    title : str
        页面标题
    page_id : int | str | None
        页面 ID
    wikitext : str
        页面原始 wikitext 内容
    raw_payload : dict[str, Any]
        API 返回的完整 JSON 响应
    """

    title: str
    page_id: int | str | None
    wikitext: str
    raw_payload: dict[str, Any]


# 从 wikitext 中提取的单个章节
@dataclass
class ParsedSection:
    """
    从 wikitext 中提取的单个章节/段落。

    章节由标题（heading）和正文文本组成。

    属性
    ----
    title : str
        章节标题，如 "角色故事"、"天赋介绍" 等
    text : str
        章节的纯文本内容（已去除 wikitext 标记）
    """

    title: str
    text: str

    def to_dict(self) -> dict[str, str]:
        """将章节转换为字典格式，便于 JSON 序列化。"""
        return {"title": self.title, "text": self.text}


# 通用页面解析结果
@dataclass
class ParsedPage:
    """
    通用 Wiki 页面的解析结果表示。

    包含页面的基本信息、分类、章节、模板等结构化数据。

    属性
    ----
    title : str
        页面标题
    page_id : int | str | None
        页面 ID
    summary : str
        页面摘要，通常为第一个章节的文本
    categories : list[str]
        页面所属分类列表
    sections : list[ParsedSection]
        页面所有章节列表
    templates : dict[str, list[dict[str, str]]]
        页面中使用的模板，按模板名称分组
        键为模板名，值为该模板的参数列表
    wikitext : str
        原始 wikitext 内容
    """

    title: str
    page_id: int | str | None
    summary: str
    categories: list[str]
    sections: list[ParsedSection]
    templates: dict[str, list[dict[str, str]]]
    wikitext: str

    def to_dict(self) -> dict[str, Any]:
        """将解析结果转换为字典格式，便于 JSON 序列化。"""
        return {
            "title": self.title,
            "page_id": self.page_id,
            "summary": self.summary,
            "categories": self.categories,
            "sections": [section.to_dict() for section in self.sections],
            "templates": self.templates,
            "wikitext": self.wikitext,
        }


@dataclass
class CharacterStoryRecord:
    """角色故事类内容记录。"""

    title: str
    content: str
    group: str = ""

    def to_dict(self) -> dict[str, str]:
        """将故事记录转换为字典。"""
        return {
            "title": self.title,
            "content": self.content,
            "group": self.group,
        }


@dataclass
class CharacterVoiceRecord:
    """角色语音记录。"""

    title: str
    content: str

    def to_dict(self) -> dict[str, str]:
        """将语音记录转换为字典。"""
        return {
            "title": self.title,
            "content": self.content,
        }


@dataclass
class AdventureNotesRecord:
    """冒险笔记记录。"""

    title: str
    content: str

    def to_dict(self) -> dict[str, str]:
        """将冒险笔记转换为字典。"""
        return {
            "title": self.title,
            "content": self.content,
        }


@dataclass
class ConstellationRecord:
    """增强版命座记录。"""

    name: str
    effect: str = ""
    description: str = ""
    raw: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将命座记录转换为字典。"""
        return {
            "name": self.name,
            "effect": self.effect,
            "description": self.description,
            "raw": self.raw,
        }


@dataclass
class TalentRecord:
    """增强版天赋记录。"""

    name: str
    description: str = ""
    category: str = ""
    element: str = ""
    raw: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将天赋记录转换为字典。"""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "element": self.element,
            "raw": self.raw,
        }


# 角色页面专用解析结果
@dataclass
class CharacterRecord:
    """
    原神角色页面的结构化解析结果。

    兼容旧版基础字段，并提供角色信息、故事、语音等更完整的结构化内容。
    """

    title: str
    summary: str
    attributes: dict[str, str]
    talents: list[dict[str, str]] = field(default_factory=list)
    constellations: list[dict[str, str]] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    full_name: str = ""
    homeland: str = ""
    origin: str = ""
    affiliation: list[str] = field(default_factory=list)
    race: str = ""
    introduction: str = ""
    god_eye_description: str = ""
    god_eye_story: str = ""
    element: str = ""
    weapon_type: str = ""
    constellation: str = ""
    special_dish: str = ""
    gender: str = ""
    bond_attribute: str = ""
    nicknames: list[str] = field(default_factory=list)
    outfits: list[str] = field(default_factory=list)
    profession: str = ""
    talent_records: list[TalentRecord] = field(default_factory=list)
    constellation_records: list[ConstellationRecord] = field(default_factory=list)
    story_records: list[CharacterStoryRecord] = field(default_factory=list)
    voice_records: list[CharacterVoiceRecord] = field(default_factory=list)
    adventure_notes: list[AdventureNotesRecord] = field(default_factory=list)
    character_introductions: list[CharacterStoryRecord] = field(default_factory=list)
    story_sections: list[CharacterStoryRecord] = field(default_factory=list)
    power_record: CharacterStoryRecord | None = None
    categories: list[str] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    templates: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """将角色记录转换为字典格式，便于 JSON 序列化。"""
        return {
            "title": self.title,
            "page_id": self.page_id,
            "summary": self.summary,
            "attributes": self.attributes,
            "talents": self.talents,
            "constellations": self.constellations,
            "titles": self.titles,
            "full_name": self.full_name,
            "homeland": self.homeland,
            "origin": self.origin,
            "affiliation": self.affiliation,
            "race": self.race,
            "introduction": self.introduction,
            "god_eye_description": self.god_eye_description,
            "god_eye_story": self.god_eye_story,
            "element": self.element,
            "weapon_type": self.weapon_type,
            "constellation": self.constellation,
            "special_dish": self.special_dish,
            "gender": self.gender,
            "bond_attribute": self.bond_attribute,
            "nicknames": self.nicknames,
            "outfits": self.outfits,
            "profession": self.profession,
            "talent_records": [record.to_dict() for record in self.talent_records],
            "constellation_records": [record.to_dict() for record in self.constellation_records],
            "story_records": [record.to_dict() for record in self.story_records],
            "voice_records": [record.to_dict() for record in self.voice_records],
            "adventure_notes": [record.to_dict() for record in self.adventure_notes],
            "character_introductions": [record.to_dict() for record in self.character_introductions],
            "story_sections": [record.to_dict() for record in self.story_sections],
            "power_record": None if self.power_record is None else self.power_record.to_dict(),
            "categories": self.categories,
            "sections": [section.to_dict() for section in self.sections],
            "templates": self.templates,
        }
