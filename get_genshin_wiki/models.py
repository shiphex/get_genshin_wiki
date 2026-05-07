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


# 角色页面专用解析结果
@dataclass
class CharacterRecord:
    """
    原神角色页面的结构化解析结果。

    继承通用页面属性，并额外包含角色特有的：
    - attributes : 角色基础属性（元素、武器等）
    - talents    : 天赋/技能列表
    - constellations : 命座/星座列表

    属性
    ----
    title : str
        角色名称
    summary : str
        角色简介/摘要
    attributes : dict[str, str]
        角色基础属性字典，如 {"元素": "冰", "武器": "法器"}
    talents : list[dict[str, str]]
        天赋技能列表，每个天赋包含名称、描述等
    constellations : list[dict[str, str]]
        命座列表，每个命座包含名称、效果等
    categories : list[str]
        页面所属分类
    sections : list[ParsedSection]
        页面章节列表
    templates : dict[str, list[dict[str, str]]]
        页面使用的模板
    page_id : int | str | None
        页面 ID
    """

    title: str
    summary: str
    attributes: dict[str, str]
    talents: list[dict[str, str]] = field(default_factory=list)
    constellations: list[dict[str, str]] = field(default_factory=list)
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
            "categories": self.categories,
            "sections": [section.to_dict() for section in self.sections],
            "templates": self.templates,
        }


# 怪物页面专用解析结果
@dataclass
class MonsterRecord:
    """
    原神怪物页面的结构化解析结果。

    属性（仅包含 git-worktree-spec.md 中要求的核心字段）：
    ----
    title : str
        怪物名称
    monster_class : str
        怪物类别（如：周刷BOSS、精英等）
    monster_category : str
        怪物分类（如：值得铭记的强敌、自律机关等）
    monster_type : str
        怪物类型（如：其他、战争机械等）
    location : str
        出现地点
    drop_materials : list[str]
        掉落素材列表
    description : str
        怪物介绍
    """

    title: str
    monster_class: str
    monster_category: str
    monster_type: str
    location: str
    drop_materials: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """将怪物记录转换为字典格式，便于 JSON 序列化。"""
        return {
            "title": self.title,
            "monster_class": self.monster_class,
            "monster_category": self.monster_category,
            "monster_type": self.monster_type,
            "location": self.location,
            "drop_materials": self.drop_materials,
            "description": self.description,
        }
