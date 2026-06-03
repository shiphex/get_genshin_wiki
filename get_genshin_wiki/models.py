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


def _serialize_record_metadata(
    *,
    page_id: int | str | None,
    categories: list[str],
    sections: list["ParsedSection"],
    templates: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    """Build shared metadata for specialized record classes."""
    return {
        "page_id": page_id,
        "categories": categories,
        "sections": [section.to_dict() for section in sections],
        "templates": templates,
    }


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


# 书籍卷/章详情
@dataclass
class BookVolume:
    """
    书籍单卷的结构化数据。

    属性
    ----
    name : str
        卷/章名称
    description : str
        卷/章描述
    location : str
        获取地点
    content : str
        卷/章正文内容，使用 \\n 表示换行
    """

    name: str
    description: str
    location: str
    content: str

    def to_dict(self) -> dict[str, str]:
        """将卷记录转换为字典格式，便于 JSON 序列化。"""
        return {
            "name": self.name,
            "description": self.description,
            "location": self.location,
            "content": self.content,
        }


# 书籍页面专用解析结果
@dataclass
class BookRecord:
    """
    原神书籍页面的结构化解析结果。

    包含书籍的基本信息和所有卷/章详情。

    属性
    ----
    title : str
        书籍名称
    genre : str
        体裁（如：史书、工具书、小说）
    country : str
        所属国家/地区
    volumes : list[BookVolume]
        卷/章列表
    categories : list[str]
        页面所属分类
    page_id : int | str | None
        页面 ID
    """

    title: str
    genre: str
    country: str
    volumes: list[BookVolume] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """将书籍记录转换为字典格式，便于 JSON 序列化。"""
        return {
            "title": self.title,
            "genre": self.genre,
            "country": self.country,
            "volumes": [volume.to_dict() for volume in self.volumes],
            "categories": self.categories,
            "page_id": self.page_id,
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
            **_serialize_record_metadata(
                page_id=self.page_id,
                categories=self.categories,
                sections=self.sections,
                templates=self.templates,
            ),
        }

    def to_storage_dict(self) -> dict[str, Any]:
        """Serialize the character record to the minimal persisted schema."""
        power_title = ""
        power_content = ""
        if self.power_record is not None:
            power_title = self.god_eye_description or self.power_record.title
            power_content = self.power_record.content

        return {
            "角色": {
                "名称": self.title,
                "称号": self._join_values(self.titles),
                "全名": self.full_name,
                "所属": self.homeland,
                "出身": self.origin,
                "种族": self.race,
                "介绍": self.introduction,
                "神之眼描述": self.god_eye_description,
                "元素属性": self.element,
                "武器类型": self.weapon_type,
                "命之座": self.constellation,
                "特殊料理": self.special_dish,
                "性别": self.gender,
                "羁绊属性": self.bond_attribute,
                "昵称/外号": self._join_values(self.nicknames),
                "衣装名称": self._join_values(self.outfits),
                "归属": self._join_values(self.affiliation),
                "职业": self.profession,
            },
            "角色故事": self._records_to_mapping(self.story_records),
            "冒险笔记": self._records_to_mapping(self.adventure_notes),
            "权能": {} if not power_title and not power_content else {power_title: power_content},
            "壹·人物": self._records_to_mapping(self.character_introductions),
            "贰·故事": self._records_to_mapping(self.story_sections),
            "角色语音": self._records_to_mapping(self.voice_records),
        }

    def _join_values(self, values: list[str]) -> str:
        """Join multi-value character fields using the agreed separator."""
        return "、".join(value for value in values if value)

    def _records_to_mapping(self, records: list[Any]) -> dict[str, str]:
        """Convert ordered record lists into stable key/value mappings."""
        result: dict[str, str] = {}
        for record in records:
            title = getattr(record, "title", "")
            content = getattr(record, "content", "")
            if not title or title in result:
                continue
            result[title] = content
        return result


@dataclass
class ChronicleRecord:
    """Legacy flat chronicle record kept for compatibility with old helpers."""

    era_name: str
    year: str
    major_events: list[str] = field(default_factory=list)
    faction_changes: list[str] = field(default_factory=list)
    related_characters: list[str] = field(default_factory=list)
    background: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the legacy chronicle record for JSON output."""
        return {
            "era_name": self.era_name,
            "year": self.year,
            "major_events": self.major_events,
            "faction_changes": self.faction_changes,
            "related_characters": self.related_characters,
            "background": self.background,
        }


@dataclass
class ChronicleItemRecord:
    """Structured record for one chronicle item within a chapter."""

    title: str
    content: str = ""
    entries: list[str] = field(default_factory=list)
    related_characters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the chronicle item for JSON output."""
        return {
            "title": self.title,
            "content": self.content,
            "entries": self.entries,
            "related_characters": self.related_characters,
        }


@dataclass
class ChronicleSectionRecord:
    """Structured record for one chronicle chapter or subchapter."""

    title: str
    level: int
    content: str = ""
    items: list[ChronicleItemRecord] = field(default_factory=list)
    subsections: list["ChronicleSectionRecord"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the chronicle section for JSON output."""
        return {
            "title": self.title,
            "level": self.level,
            "content": self.content,
            "items": [item.to_dict() for item in self.items],
            "subsections": [section.to_dict() for section in self.subsections],
        }


@dataclass
class ChroniclePageRecord:
    """Structured record for one chronicle page and its chapter tree."""

    title: str
    intro: str = ""
    sections: list[ChronicleSectionRecord] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the chronicle page record for JSON output."""
        return {
            "title": self.title,
            "intro": self.intro,
            "sections": [section.to_dict() for section in self.sections],
            "categories": self.categories,
            "page_id": self.page_id,
        }


@dataclass
class FoodRecord:
    """Structured record for food pages."""

    title: str
    type: str
    normal_description: str
    perfect_description: str = ""
    failed_description: str = ""
    ingredients: str = ""
    recipe_obtain_method: str = ""
    special_dish: str = ""
    special_dish_character: str = ""
    categories: list[str] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    templates: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the food record for JSON output."""
        return {
            "名称": self.title,
            "类型": self.type,
            "介绍": {
                "普通料理": self.normal_description,
                "完美料理": self.perfect_description,
                "失败料理": self.failed_description,
            },
            "所需食材": self.ingredients,
            "食谱获取方式": self.recipe_obtain_method,
            "特殊料理": self.special_dish,
            "特殊料理角色": self.special_dish_character,
        }


@dataclass
class WildlifeRecord:
    """Structured record for wildlife pages."""

    title: str
    type: str
    species: str
    description: str
    locations: str = ""
    capturable: str = ""
    fishing_info: dict[str, str] = field(default_factory=dict)
    categories: list[str] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    templates: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the wildlife record for JSON output."""
        return {
            "名称": self.title,
            "类型": self.type,
            "种类": self.species,
            "描述": self.description,
            "出现地点": self.locations,
            "能否捕捉": self.capturable,
            "钓鱼信息": {
                "钓鱼鱼饵": self.fishing_info.get("bait", ""),
                "钓鱼时间": self.fishing_info.get("time", ""),
                "钓鱼地点": self.fishing_info.get("location", ""),
            },
        }


@dataclass
class QuestItemRecord:
    """Structured record for quest item pages."""

    title: str
    type: str
    description: str
    related_quest: str = ""
    obtain_method: str = ""
    content: str = ""
    categories: list[str] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    templates: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the quest item record for JSON output."""
        return {
            "名称": self.title,
            "类型": self.type,
            "描述": self.description,
            "相关任务": self.related_quest,
            "获取方式": self.obtain_method,
            "内容": self.content,
        }


@dataclass
class ItemRecord:
    """Structured record for general item pages."""

    title: str
    type: str
    source: str
    usage: str
    description: str
    categories: list[str] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    templates: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the item record for JSON output."""
        return {
            "名称": self.title,
            "类型": self.type,
            "来源": self.source,
            "用途": self.usage,
            "介绍": self.description,
        }


@dataclass
class MaterialRecord:
    """Structured record for material pages."""

    title: str
    type: str
    source: str
    description: str
    usage: str
    categories: list[str] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    templates: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the material record for JSON output."""
        return {
            "名称": self.title,
            "类型": self.type,
            "来源": self.source,
            "介绍": self.description,
            "用途": self.usage,
        }


@dataclass
class NameCardRecord:
    """Structured record for name card pages."""

    title: str
    obtain_method: str
    description: str
    categories: list[str] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    templates: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the name card record for JSON output."""
        return {
            "名称": self.title,
            "获取方式": self.obtain_method,
            "描述": self.description,
        }


@dataclass
class SecretItemRecord:
    """Structured record for domain-like secret item pages."""

    title: str
    type: str
    description: str
    drops: dict[str, str] = field(default_factory=dict)
    categories: list[str] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    templates: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    page_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the secret item record for JSON output."""
        return {
            "名称": self.title,
            "类型": self.type,
            "介绍": self.description,
            "掉落": dict(self.drops),
        }


# 武器页面专用解析结果
@dataclass
class WeaponRecord:
    """
    原神武器页面的结构化解析结果。

    武器规格要求字段：
    - 名称 (title)
    - 类型 (weapon_type)
    - 介绍 (description)
    - 突破武器材料序列 (ascension_weapon_materials)
    - 突破高级材料序列 (ascension_premium_materials)
    - 突破普通材料序列 (ascension_common_materials)
    - 获取途径 (obtaining_method)
    - 锻造材料 (forging_blueprint)
    - 精炼材料 (refining_material)
    - 故事 (story)

    属性
    ----
    title : str
        武器名称
    weapon_type : str
        武器类型（如 弓、法器、单手剑等）
    description : str
        武器介绍
    ascension_weapon_materials : list[str]
        突破武器材料序列
    ascension_premium_materials : list[str]
        突破高级材料序列
    ascension_common_materials : list[str]
        突破普通材料序列
    obtaining_method : str
        获取途径（祈愿/限定祈愿/活动名称/任务名称/锻造等）
    forging_blueprint : str
        锻造材料，若不可锻造则为"不可锻造获取"
    refining_material : str
        精炼材料，若不可精炼则为"不可使用材料精炼"
    story : str
        武器故事/背景描述
    """

    title: str
    weapon_type: str
    description: str = ""
    ascension_weapon_materials: list[str] = field(default_factory=list)
    ascension_premium_materials: list[str] = field(default_factory=list)
    ascension_common_materials: list[str] = field(default_factory=list)
    obtaining_method: str = ""
    forging_blueprint: str = "不可锻造获取"
    refining_material: str = "不可使用材料精炼"
    story: str = ""

    def to_dict(self) -> dict[str, Any]:
        """将武器记录转换为字典格式，便于 JSON 序列化。"""
        return {
            "名称": self.title,
            "类型": self.weapon_type,
            "介绍": self.description,
            "突破武器材料序列": self.ascension_weapon_materials,
            "突破高级材料序列": self.ascension_premium_materials,
            "突破普通材料序列": self.ascension_common_materials,
            "获取途径": self.obtaining_method,
            "锻造材料": self.forging_blueprint,
            "精炼材料": self.refining_material,
            "故事": self.story,
        }


# 圣遗物套装解析结果
@dataclass
class ArtifactPieceRecord:
    """
    圣遗物部件（生之花、死之羽、时之沙、空之杯、理之冠）。

    属性
    ----
    slot : str
        部位名称（如 生之花、死之羽等）
    name : str
        部件名称
    description : str
        部件描述
    story : str
        部件故事
    """

    slot: str
    name: str
    description: str
    story: str

    def to_dict(self) -> dict[str, str]:
        """转换为字典格式。"""
        return {
            "名称": self.name,
            "描述": self.description,
            "故事": self.story,
        }


@dataclass
class ArtifactSetRecord:
    """
    原神圣遗物套装页面的结构化解析结果。

    圣遗物规格要求字段：
    - 名称 (title)
    - 获取方式 (obtaining_method)
    - 时之沙、死之羽、理之冠、生之花、空之杯: 名称、描述、故事

    属性
    ----
    title : str
        套装名称
    obtaining_method : str
        获取方式
    pieces : list[ArtifactPieceRecord]
        套装部件列表（生之花、死之羽、时之沙、空之杯、理之冠）
    """

    title: str
    obtaining_method: str = ""
    pieces: list[ArtifactPieceRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """将圣遗物套装记录转换为字典格式，便于 JSON 序列化。"""
        result = {
            "名称": self.title,
            "获取方式": self.obtaining_method,
        }
        # 按固定顺序添加各部件
        slot_order = ["时之沙", "死之羽", "理之冠", "生之花", "空之杯"]
        pieces_dict = {p.slot: p.to_dict() for p in self.pieces}
        for slot in slot_order:
            if slot in pieces_dict:
                result[slot] = pieces_dict[slot]
        return result


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
