"""
命令行入口模块
==============

本模块提供原神 Wiki 数据抓取与管理的命令行接口。

命令结构
--------
    python -m get_genshin_wiki <command> <subcommand> [options]

主要命令组
----------
1. crawl - 从 Wiki API 抓取数据
   - categories     : 抓取分类列表
   - members        : 抓取分类成员列表
   - page           : 抓取单个页面
   - category-pages : 抓取分类下所有页面

2. parse - 解析已存储的页面数据
   - page           : 解析通用页面
   - character      : 解析角色页面
   - book           : 解析书籍页面

3. store - 操作本地存储的 JSON 数据
   - put/query/update/add/delete/exists/list

使用示例
--------
    # 抓取角色分类
    python -m get_genshin_wiki crawl categories --prefix 角色

    # 抓取角色分类的所有页面
    python -m get_genshin_wiki crawl category-pages 角色 --page-limit 10

    # 解析角色页面
    python -m get_genshin_wiki parse character 哥伦比娅

    # 查询存储数据
    python -m get_genshin_wiki store query pages 哥伦比娅
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from tools.batch_archon_quests import (
    DEFAULT_LIST_TITLE as _DEFAULT_ARCHON_QUEST_LIST_TITLE,
    DEFAULT_OUTPUT as _DEFAULT_ARCHON_QUEST_OUTPUT,
    INDEX_NAMESPACE as _ARCHON_QUEST_INDEX_NAMESPACE,
    OUTPUT_NAMESPACE as _ARCHON_QUEST_OUTPUT_NAMESPACE,
    expand_archon_index_entries,
    load_existing_output as _load_existing_archon_output,
    write_output as _write_archon_output,
)
from tools.batch_character_quests import (
    DEFAULT_LIST_TITLE as _DEFAULT_CHARACTER_QUEST_LIST_TITLE,
    DEFAULT_OUTPUT as _DEFAULT_CHARACTER_QUEST_OUTPUT,
    INDEX_NAMESPACE as _CHARACTER_QUEST_INDEX_NAMESPACE,
    OUTPUT_NAMESPACE as _CHARACTER_QUEST_OUTPUT_NAMESPACE,
    build_character_quest_index,
    discover_character_categories,
    is_character_quest_series_payload,
    load_existing_output as _load_existing_character_quest_output,
    load_or_crawl_category_members,
    load_or_crawl_page,
    order_character_records,
    write_output as _write_character_quest_output,
)
from tools.reparse_and_store import ENTITY_CONFIGS

from .client import MediaWikiClient
from .crawler import WikiCrawler
from .parser import WikiTextParser
from .storage import JsonFileStore

# CLI 命令处理器类型别名
# 每个 handler 函数接收解析后的参数和运行时环境，返回退出码
CliHandler = Callable[[argparse.Namespace, "CliRuntime"], int]

# 解析输出的默认命名空间映射
_DEFAULT_PARSE_NAMESPACES = {
    "page": "parsed/pages",
    "chronicle": "parsed/chronicles",
    "character": "parsed/characters",
    "archon-quest": "parsed/archon-quests",
    "event-quest": "parsed/event-quests",
    "weapon": "parsed/weapons",
    "artifact": "parsed/artifacts",
    "monster": "parsed/monsters",
    "food": "parsed/foods",
    "wildlife": "parsed/wildlife",
    "quest-item": "parsed/quest-items",
    "item": "parsed/items",
    "material": "parsed/materials",
    "namecard": "parsed/namecards",
    "secret-item": "parsed/secret-items",
    "book": "parsed/books",
    "north-library": "parsed/north-library",
}

_ALL_STANDARD_ENTITY_IDS = (
    "weapons",
    "artifacts",
    "monsters",
    "books",
    "foods",
    "wildlife",
    "quest-items",
    "items",
    "materials",
    "namecards",
    "secret-items",
)
_ALL_ENTITY_ORDER = (
    *_ALL_STANDARD_ENTITY_IDS,
    "characters",
    "event-quests",
    "chronicles",
    "north-library",
    "archon-quests",
    "character-quests",
)
_ALL_CHRONICLE_TITLES = (
    "提瓦特编年史（公元纪）",
    "提瓦特编年史",
    "蒙德",
    "璃月",
    "稻妻",
    "须弥",
    "枫丹",
    "纳塔",
    "至冬",
    "坎瑞亚",
    "白夜国",
    "星球",
    "宇宙",
)


@dataclass
class CliRuntime:
    """
    CLI 命令运行时依赖容器。

    包含处理命令所需的所有组件实例，
    便于测试时注入 mock 对象。
    """

    store: JsonFileStore
    client: MediaWikiClient
    crawler: WikiCrawler
    parser: WikiTextParser


def build_runtime(data_root: Path | None = None) -> CliRuntime:
    """
    构建 CLI 运行时环境。

    创建并组装所有必要的组件实例。

    参数
    ----
    data_root : Path | None
        数据存储根目录，默认为 None（使用配置默认值）

    返回
    ----
    CliRuntime
        配置好的运行时环境对象
    """
    store = JsonFileStore(data_root)
    session = requests.Session()
    session.trust_env = False
    client = MediaWikiClient(session=session)
    crawler = WikiCrawler(client=client, store=store)
    parser = WikiTextParser()
    return CliRuntime(store=store, client=client, crawler=crawler, parser=parser)


def build_parser() -> argparse.ArgumentParser:
    """
    构建完整的命令行参数解析器。

    返回
    ----
    argparse.ArgumentParser
        配置好的解析器对象
    """
    parser = argparse.ArgumentParser(description="Crawl, parse, and manage Genshin wiki data.")
    # 全局参数：数据存储根目录
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Override the root directory used for local JSON storage.",
    )
    # 子命令解析器：crawl / parse / store
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ========== crawl 子命令 ==========
    crawl_parser = subparsers.add_parser("crawl", help="Fetch data from the wiki API.")
    crawl_commands = crawl_parser.add_subparsers(dest="crawl_target", required=True)

    # crawl categories：抓取分类列表
    crawl_categories = crawl_commands.add_parser("categories", help="Fetch wiki categories.")
    crawl_categories.add_argument("--prefix", default=None, help="Filter categories by prefix")
    crawl_categories.add_argument("--no-persist", action="store_true", help="Do not save to storage")
    crawl_categories.set_defaults(handler=handle_crawl_categories)

    # crawl members：抓取分类成员
    crawl_members = crawl_commands.add_parser("members", help="Fetch members of a category.")
    crawl_members.add_argument("category", help="Category name")
    crawl_members.add_argument("--no-persist", action="store_true")
    crawl_members.set_defaults(handler=handle_crawl_members)

    # crawl page：抓取单个页面
    crawl_page = crawl_commands.add_parser("page", help="Fetch a single page payload.")
    crawl_page.add_argument("title", help="Page title")
    crawl_page.add_argument("--no-persist", action="store_true")
    crawl_page.set_defaults(handler=handle_crawl_page)

    # crawl category-pages：批量抓取分类页面
    crawl_category_pages = crawl_commands.add_parser(
        "category-pages",
        help="Fetch all member pages for a category.",
    )
    crawl_category_pages.add_argument("category", help="Category name")
    crawl_category_pages.add_argument("--page-limit", type=int, default=None, help="Limit number of pages")
    crawl_category_pages.add_argument("--no-persist", action="store_true")
    crawl_category_pages.set_defaults(handler=handle_crawl_category_pages)

    crawl_north_library = crawl_commands.add_parser(
        "north-library",
        help="Fetch, parse, and persist the North Library index page.",
    )
    crawl_north_library.add_argument("--title", default="北陆图书馆", help="North Library page title")
    crawl_north_library.add_argument("--output-namespace", default=None, help="Namespace to write parsed result")
    crawl_north_library.add_argument("--no-persist", action="store_true")
    crawl_north_library.set_defaults(handler=handle_crawl_north_library)

    # crawl chronicle-pages：探测并抓取提瓦特编年史分类页面
    crawl_chronicle_pages = crawl_commands.add_parser(
        "chronicle-pages",
        help="Detect the chronicle category and fetch all of its pages.",
    )
    crawl_chronicle_pages.add_argument("--page-limit", type=int, default=None, help="Limit number of pages")
    crawl_chronicle_pages.add_argument("--no-persist", action="store_true")
    crawl_chronicle_pages.set_defaults(handler=handle_crawl_chronicle_pages)

    # crawl event-quests：自动探测活动任务分类并抓取成员页面
    crawl_event_quests = crawl_commands.add_parser(
        "event-quests",
        aliases=["eventquests"],
        help="Discover and fetch event quest pages plus related event pages.",
    )
    crawl_event_quests.add_argument("--page-limit", type=int, default=None, help="Limit number of quest pages")
    crawl_event_quests.add_argument("--no-persist", action="store_true")
    crawl_event_quests.set_defaults(handler=handle_crawl_event_quests)

    # ========== parse 子命令 ==========
    parse_parser = subparsers.add_parser("parse", help="Parse stored page payloads.")
    parse_commands = parse_parser.add_subparsers(dest="parse_target", required=True)

    # parse page：解析通用页面
    parse_page = parse_commands.add_parser("page", help="Parse a stored page payload.")
    parse_page.add_argument("title", help="Page title")
    parse_page.add_argument("--source-namespace", default="pages", help="Namespace to read from")
    parse_page.add_argument("--output-namespace", default=None, help="Namespace to write parsed result")
    parse_page.add_argument("--no-persist", action="store_true")
    parse_page.set_defaults(handler=handle_parse_page)

    # parse chronicle：解析编年史页面
    parse_chronicle = parse_commands.add_parser("chronicle", help="Parse a stored chronicle page.")
    parse_chronicle.add_argument("title", help="Chronicle page title")
    parse_chronicle.add_argument("--source-namespace", default="pages")
    parse_chronicle.add_argument("--output-namespace", default=None)
    parse_chronicle.add_argument("--no-persist", action="store_true")
    parse_chronicle.set_defaults(handler=handle_parse_chronicle)

    # parse character：解析角色页面
    parse_character = parse_commands.add_parser("character", help="Parse a stored character page.")
    parse_character.add_argument("title", help="Character name")
    parse_character.add_argument("--source-namespace", default="pages")
    parse_character.add_argument("--output-namespace", default=None)
    parse_character.add_argument("--no-persist", action="store_true")
    parse_character.set_defaults(handler=handle_parse_character)

    # parse archon-quest：解析魔神任务页面
    parse_archon_quest = parse_commands.add_parser(
        "archon-quest",
        aliases=["archonquest"],
        help="Parse a stored archon quest page.",
    )
    parse_archon_quest.add_argument("title", help="Archon quest page title")
    parse_archon_quest.add_argument("--source-namespace", default="pages")
    parse_archon_quest.add_argument("--output-namespace", default=None)
    parse_archon_quest.add_argument("--no-persist", action="store_true")
    parse_archon_quest.set_defaults(handler=handle_parse_archon_quest)

    # parse event-quest：解析活动任务页面
    parse_event_quest = parse_commands.add_parser(
        "event-quest",
        aliases=["eventquest"],
        help="Parse a stored event quest page.",
    )
    parse_event_quest.add_argument("title", help="Event quest page title")
    parse_event_quest.add_argument("--source-namespace", default="pages")
    parse_event_quest.add_argument("--output-namespace", default=None)
    parse_event_quest.add_argument("--no-persist", action="store_true")
    parse_event_quest.set_defaults(handler=handle_parse_event_quest)

    # parse weapon：解析武器页面
    parse_weapon = parse_commands.add_parser("weapon", help="Parse a stored weapon page.")
    parse_weapon.add_argument("title", help="Weapon name")
    parse_weapon.add_argument("--source-namespace", default="pages")
    parse_weapon.add_argument("--output-namespace", default=None)
    parse_weapon.add_argument("--no-persist", action="store_true")
    parse_weapon.set_defaults(handler=handle_parse_weapon)

    # parse artifact：解析圣遗物套装页面
    parse_artifact = parse_commands.add_parser("artifact", help="Parse a stored artifact set page.")
    parse_artifact.add_argument("title", help="Artifact set name")
    parse_artifact.add_argument("--source-namespace", default="pages")
    parse_artifact.add_argument("--output-namespace", default=None)
    parse_artifact.add_argument("--no-persist", action="store_true")
    parse_artifact.set_defaults(handler=handle_parse_artifact)

    # parse monster：解析怪物页面
    parse_monster = parse_commands.add_parser("monster", help="Parse a stored monster page.")
    parse_monster.add_argument("title", help="Monster name")
    parse_monster.add_argument("--source-namespace", default="pages")
    parse_monster.add_argument("--output-namespace", default=None)
    parse_monster.add_argument("--no-persist", action="store_true")
    parse_monster.set_defaults(handler=handle_parse_monster)

    # parse food：解析食物页面
    parse_food = parse_commands.add_parser("food", help="Parse a stored food page.")
    parse_food.add_argument("title", help="Food page title")
    parse_food.add_argument("--source-namespace", default="pages")
    parse_food.add_argument("--output-namespace", default=None)
    parse_food.add_argument("--no-persist", action="store_true")
    parse_food.set_defaults(handler=handle_parse_food)

    # parse wildlife：解析野生动物页面
    parse_wildlife = parse_commands.add_parser("wildlife", help="Parse a stored wildlife page.")
    parse_wildlife.add_argument("title", help="Wildlife page title")
    parse_wildlife.add_argument("--source-namespace", default="pages")
    parse_wildlife.add_argument("--output-namespace", default=None)
    parse_wildlife.add_argument("--no-persist", action="store_true")
    parse_wildlife.set_defaults(handler=handle_parse_wildlife)

    # parse quest-item：解析任务道具页面
    parse_quest_item = parse_commands.add_parser(
        "quest-item",
        aliases=["questitem"],
        help="Parse a stored quest item page.",
    )
    parse_quest_item.add_argument("title", help="Quest item page title")
    parse_quest_item.add_argument("--source-namespace", default="pages")
    parse_quest_item.add_argument("--output-namespace", default=None)
    parse_quest_item.add_argument("--no-persist", action="store_true")
    parse_quest_item.set_defaults(handler=handle_parse_quest_item)

    # parse item：解析道具页面
    parse_item = parse_commands.add_parser("item", help="Parse a stored item page.")
    parse_item.add_argument("title", help="Item page title")
    parse_item.add_argument("--source-namespace", default="pages")
    parse_item.add_argument("--output-namespace", default=None)
    parse_item.add_argument("--no-persist", action="store_true")
    parse_item.set_defaults(handler=handle_parse_item)

    # parse material：解析材料页面
    parse_material = parse_commands.add_parser("material", help="Parse a stored material page.")
    parse_material.add_argument("title", help="Material page title")
    parse_material.add_argument("--source-namespace", default="pages")
    parse_material.add_argument("--output-namespace", default=None)
    parse_material.add_argument("--no-persist", action="store_true")
    parse_material.set_defaults(handler=handle_parse_material)

    # parse namecard：解析名片页面
    parse_namecard = parse_commands.add_parser(
        "namecard",
        aliases=["name-card"],
        help="Parse a stored name card page.",
    )
    parse_namecard.add_argument("title", help="Name card page title")
    parse_namecard.add_argument("--source-namespace", default="pages")
    parse_namecard.add_argument("--output-namespace", default=None)
    parse_namecard.add_argument("--no-persist", action="store_true")
    parse_namecard.set_defaults(handler=handle_parse_namecard)

    # parse secret-item：解析秘境页面
    parse_secret_item = parse_commands.add_parser(
        "secret-item",
        aliases=["secretitem"],
        help="Parse a stored secret item page.",
    )
    parse_secret_item.add_argument("title", help="Secret item page title")
    parse_secret_item.add_argument("--source-namespace", default="pages")
    parse_secret_item.add_argument("--output-namespace", default=None)
    parse_secret_item.add_argument("--no-persist", action="store_true")
    parse_secret_item.set_defaults(handler=handle_parse_secret_item)

    # parse book：解析书籍页面
    parse_book = parse_commands.add_parser("book", help="Parse a stored book page.")
    parse_book.add_argument("title", help="Book name")
    parse_book.add_argument("--source-namespace", default="pages")
    parse_book.add_argument("--output-namespace", default=None)
    parse_book.add_argument("--no-persist", action="store_true")
    parse_book.set_defaults(handler=handle_parse_book)

    # ========== store 子命令 ==========
    all_parser = subparsers.add_parser("all", help="Run the full crawl-parse pipeline for one or more entities.")
    _add_all_common_arguments(all_parser)
    all_parser.set_defaults(handler=handle_all_everything, resume=False)
    all_commands = all_parser.add_subparsers(dest="all_target", required=False)

    for entity_id in _ALL_STANDARD_ENTITY_IDS:
        entity_parser = all_commands.add_parser(entity_id, help=f"Run the full {entity_id} pipeline.")
        _add_all_common_arguments(entity_parser)
        entity_parser.set_defaults(handler=handle_all_standard_entity, entity_id=entity_id, resume=False)

    all_characters = all_commands.add_parser("characters", help="Run the full character pipeline, including voice pages.")
    _add_all_common_arguments(all_characters)
    all_characters.set_defaults(handler=handle_all_characters, resume=False)

    all_event_quests = all_commands.add_parser(
        "event-quests",
        help="Run the full event-quest pipeline, including related event pages.",
    )
    _add_all_common_arguments(all_event_quests)
    all_event_quests.set_defaults(handler=handle_all_event_quests, resume=False)

    all_chronicles = all_commands.add_parser("chronicles", help="Run the full chronicle pipeline.")
    _add_all_common_arguments(all_chronicles)
    all_chronicles.set_defaults(handler=handle_all_chronicles, resume=False)

    all_north_library = all_commands.add_parser("north-library", help="Run the North Library pipeline.")
    _add_all_common_arguments(all_north_library)
    all_north_library.set_defaults(handler=handle_all_north_library, resume=False)

    all_archon_quests = all_commands.add_parser("archon-quests", help="Run the full archon-quest pipeline.")
    _add_all_common_arguments(all_archon_quests, include_resume=True)
    all_archon_quests.set_defaults(handler=handle_all_archon_quests)

    all_character_quests = all_commands.add_parser(
        "character-quests",
        help="Run the full character-quest pipeline.",
    )
    _add_all_common_arguments(all_character_quests, include_resume=True)
    all_character_quests.set_defaults(handler=handle_all_character_quests)

    store_parser = subparsers.add_parser("store", help="Operate on locally stored JSON data.")
    store_commands = store_parser.add_subparsers(dest="store_action", required=True)

    # store put：创建或替换记录
    store_put = store_commands.add_parser(
        "put",
        aliases=["write", "save"],
        help="Create or replace a stored record.",
    )
    store_put.add_argument("namespace", help="Storage namespace")
    store_put.add_argument("key", help="Storage key")
    _add_payload_arguments(store_put)
    store_put.set_defaults(handler=handle_store_put)

    # store query：查询记录
    store_query = store_commands.add_parser(
        "query",
        aliases=["get", "read"],
        help="Read a stored record.",
    )
    store_query.add_argument("namespace", help="Storage namespace")
    store_query.add_argument("key", help="Storage key")
    store_query.set_defaults(handler=handle_store_query)

    # store update：合并更新字典
    store_update = store_commands.add_parser("update", help="Merge a JSON object into a stored record.")
    store_update.add_argument("namespace", help="Storage namespace")
    store_update.add_argument("key", help="Storage key")
    _add_payload_arguments(store_update)
    store_update.set_defaults(handler=handle_store_update)

    # store add：追加内容到列表或字典
    store_add = store_commands.add_parser(
        "add",
        aliases=["append"],
        help="Append to a stored list or add non-conflicting fields to a stored object.",
    )
    store_add.add_argument("namespace", help="Storage namespace")
    store_add.add_argument("key", help="Storage key")
    _add_payload_arguments(store_add)
    store_add.set_defaults(handler=handle_store_add)

    # store delete：删除记录
    store_delete = store_commands.add_parser(
        "delete",
        aliases=["remove"],
        help="Delete a stored record.",
    )
    store_delete.add_argument("namespace", help="Storage namespace")
    store_delete.add_argument("key", help="Storage key")
    store_delete.set_defaults(handler=handle_store_delete)

    # store exists：检查记录是否存在
    store_exists = store_commands.add_parser("exists", help="Check whether a stored record exists.")
    store_exists.add_argument("namespace", help="Storage namespace")
    store_exists.add_argument("key", help="Storage key")
    store_exists.set_defaults(handler=handle_store_exists)

    # store list：列出命名空间中的所有记录
    store_list = store_commands.add_parser("list", help="List stored JSON files in a namespace.")
    store_list.add_argument("namespace", help="Storage namespace")
    store_list.set_defaults(handler=handle_store_list)

    return parser


def _add_payload_arguments(parser: argparse.ArgumentParser) -> None:
    """
    为 store 子命令添加 payload 参数选项。

    payload 可以通过命令行内联 JSON 或从文件读取。
    """
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--payload", help="Inline JSON payload.")
    group.add_argument(
        "--payload-file",
        type=Path,
        help="Path to a JSON file that contains the payload.",
    )


def _add_all_common_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_resume: bool = False,
) -> None:
    """Add the shared options used by `python main.py all` commands."""
    parser.add_argument("--page-limit", type=int, default=None, help="Limit the number of pages to process.")
    parser.add_argument("--no-persist", action="store_true", help="Do not save crawled or parsed results.")
    if include_resume:
        parser.add_argument("--resume", action="store_true", help="Reuse existing aggregate output when available.")


def _load_payload(args: argparse.Namespace) -> Any:
    """
    从参数中加载 JSON payload。

    支持 --payload（内联）和 --payload-file（文件）两种方式。
    """
    if args.payload is not None:
        try:
            return json.loads(args.payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON passed via --payload: {exc}") from exc
    try:
        with args.payload_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in payload file {args.payload_file}: {exc}") from exc


def _print_json(payload: Any) -> None:
    """将对象格式化为 JSON 并打印到 stdout。"""
    try:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
    except UnicodeEncodeError:
        print(json.dumps(payload, ensure_ascii=True, indent=2, default=_json_default))


def _json_default(value: Any) -> str:
    """
    JSON 序列化回调函数。

    处理 pathlib.Path 等非标准 JSON 类型。
    """
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _page_metadata(payload: dict[str, Any], fallback_title: str) -> dict[str, Any]:
    """
    从页面 payload 中提取基本元数据。

    用于 crawl category-pages 命令构建输出结果。
    """
    pages = payload.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    return {
        "title": page.get("title", fallback_title),
        "page_id": page.get("pageid"),
    }


def _maybe_load_voice_payload(store: JsonFileStore, namespace: str, title: str) -> dict[str, Any] | None:
    """尝试读取与角色主页面配套的语音页面 payload。"""
    voice_title = f"{title}语音"
    if not store.exists(namespace, voice_title):
        return None
    payload = store.read(namespace, voice_title)
    pages = payload.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    revisions = page.get("revisions", [])
    if not revisions:
        return None
    wikitext = revisions[0].get("slots", {}).get("main", {}).get("*", "")
    return payload if wikitext else None


def _maybe_load_archon_series_context(
    runtime: CliRuntime,
    namespace: str,
) -> dict[str, tuple[str, str, str, str]]:
    """Load chapter/act context from the stored archon quest index when available."""
    list_title = "魔神任务"
    if not runtime.store.exists(namespace, list_title):
        return {}
    payload = runtime.store.read(namespace, list_title)
    entries = runtime.parser.parse_archon_quest_list_page(payload)
    return runtime.parser.build_archon_series_context(entries)


def _maybe_load_event_payload(
    store: JsonFileStore,
    parser: WikiTextParser,
    namespace: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """尝试读取活动任务页面对应的活动主页面 payload。"""
    record = parser.parse_event_quest_page(payload)
    event_title = record.event_name or record.related_event
    if not event_title or event_title == record.title or not store.exists(namespace, event_title):
        return None
    event_payload = store.read(namespace, event_title)
    pages = event_payload.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    revisions = page.get("revisions", [])
    if not revisions:
        return None
    wikitext = revisions[0].get("slots", {}).get("main", {}).get("*", "")
    return event_payload if wikitext else None


# ========== crawl 命令处理器 ==========


class _AllHelperCrawler:
    """Adapter that makes helper modules respect the current persist flag."""

    def __init__(self, runtime: CliRuntime, *, persist: bool) -> None:
        self.client = runtime.client
        self._crawler = runtime.crawler
        self._persist = persist

    def crawl_page(self, title: str, persist: bool = True) -> dict[str, Any]:
        return self._crawler.crawl_page(title, persist=self._persist)

    def crawl_category_members(self, category_name: str, persist: bool = True) -> list[str]:
        return self._crawler.crawl_category_members(category_name, persist=self._persist)

    def discover_character_quest_categories(self, persist: bool = True) -> dict[str, Any]:
        return self._crawler.discover_character_quest_categories(persist=self._persist)


def _payload_has_wikitext(payload: dict[str, Any]) -> bool:
    """Return True when the payload contains non-empty main-slot wikitext."""
    pages = payload.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    revisions = page.get("revisions", [])
    if not revisions:
        return False
    wikitext = revisions[0].get("slots", {}).get("main", {}).get("*", "")
    return bool(str(wikitext).strip())


def _apply_page_limit(titles: list[str], page_limit: int | None) -> list[str]:
    """Apply an optional page limit while preserving the original order."""
    if page_limit is None:
        return list(titles)
    return list(titles[:page_limit])


def _run_all_title_pipeline(
    runtime: CliRuntime,
    *,
    titles: list[str],
    output_namespace: str,
    persist: bool,
    process_title: Callable[[str], tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Run the shared crawl -> parse -> optional store loop used by `all` handlers."""
    results: list[dict[str, Any]] = []
    for title in titles:
        payload, parsed, extra = process_title(title)
        item = _page_metadata(payload, title)
        item.update(extra)
        if persist:
            item.setdefault("page_path", runtime.store.resolve_path("pages", title))
            item["parsed_path"] = runtime.store.write(output_namespace, title, parsed)
        else:
            item["parsed"] = parsed
        results.append(item)
    return results


def _resolve_all_standard_config(entity_id: str) -> Any:
    """Resolve one standard `all` entity against the shared ENTITY_CONFIGS table."""
    if entity_id not in ENTITY_CONFIGS or entity_id == "characters":
        raise ValueError(f"unsupported standard entity: {entity_id}")
    return ENTITY_CONFIGS[entity_id]


def _resolve_archon_index_act_name(entry: dict[str, str], record: dict[str, Any]) -> str:
    """Keep archon index act names aligned with the existing batch tool."""
    parsed_act_name = str(record.get("幕名称", "") or "")
    act = str(record.get("幕", "") or entry.get("act", ""))
    if parsed_act_name:
        return parsed_act_name
    if act:
        return act
    return entry.get("series_title", "") or entry.get("act_name", "")


def _character_quest_record_title(record: dict[str, Any]) -> str:
    """Extract the stable leaf-task title from a character-quest record."""
    value = record.get("任务名称", "")
    return value if isinstance(value, str) else ""


def _canonical_character_quest_title(title: str) -> str:
    """Normalize alternate character-quest page titles to their storage title."""
    normalized = title.strip()
    for suffix in ("（系列任务）", "(系列任务)", "（任务）", "(任务)"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].strip()
    return normalized


def _summarize_all_entity_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep the top-level `python main.py all` output compact."""
    summary: dict[str, Any] = {
        "entity": result["entity"],
        "persist": result["persist"],
    }
    for key in (
        "category",
        "selected_count",
        "quest_count",
        "index_count",
        "event_page_count",
        "output_path",
        "category_name",
        "title",
    ):
        if key in result:
            summary[key] = result[key]
    return summary


def handle_crawl_categories(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 crawl categories 命令：抓取 Wiki 分类列表。"""
    runtime.client.assert_api_allowed()
    result = runtime.crawler.crawl_categories(prefix=args.prefix, persist=not args.no_persist)
    _print_json(result)
    return 0


def handle_crawl_members(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 crawl members 命令：抓取分类成员列表。"""
    runtime.client.assert_api_allowed()
    result = runtime.crawler.crawl_category_members(args.category, persist=not args.no_persist)
    _print_json(result)
    return 0


def handle_crawl_page(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 crawl page 命令：抓取单个页面。"""
    runtime.client.assert_api_allowed()
    result = runtime.crawler.crawl_page(args.title, persist=not args.no_persist)
    _print_json(result)
    return 0


def handle_crawl_category_pages(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """
    处理 crawl category-pages 命令：批量抓取分类页面。

    依次获取分类成员，然后逐个抓取页面内容。
    """
    runtime.client.assert_api_allowed()
    members = runtime.crawler.crawl_category_members(args.category, persist=not args.no_persist)
    if args.page_limit is not None:
        members = members[: args.page_limit]

    result: list[dict[str, Any]] = []
    for title in members:
        payload = runtime.crawler.crawl_page(title, persist=not args.no_persist)
        page_metadata = _page_metadata(payload, title)
        if not args.no_persist:
            page_metadata["path"] = runtime.store.resolve_path("pages", title)
        result.append(page_metadata)

    _print_json(result)
    return 0


def handle_crawl_north_library(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """Handle crawl north-library: probe category, fetch page, parse, and persist JSON."""
    runtime.client.assert_api_allowed()
    _print_json(
        _build_north_library_response(
            runtime,
            title=args.title,
            output_namespace=args.output_namespace,
            persist=not args.no_persist,
        )
    )
    return 0


def handle_crawl_chronicle_pages(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 crawl chronicle-pages 命令：探测并抓取编年史分类页面。"""
    runtime.client.assert_api_allowed()
    result = runtime.crawler.crawl_chronicle_pages(
        page_limit=args.page_limit,
        persist=not args.no_persist,
    )
    _print_json(result)
    return 0


def handle_crawl_event_quests(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 crawl event-quests 命令：探测分类并抓取任务及相关活动页面。"""
    runtime.client.assert_api_allowed()
    category_name = runtime.crawler.discover_event_quest_category(persist=not args.no_persist)
    members = runtime.crawler.crawl_category_members(category_name, persist=not args.no_persist)
    if args.page_limit is not None:
        members = members[: args.page_limit]

    quest_pages: list[dict[str, Any]] = []
    related_event_titles: list[str] = []
    seen_event_titles: set[str] = set()

    for title in members:
        payload = runtime.crawler.crawl_page(title, persist=not args.no_persist)
        record = runtime.parser.parse_event_quest_page(payload)
        page_metadata = _page_metadata(payload, title)
        if not args.no_persist:
            page_metadata["path"] = runtime.store.resolve_path("pages", title)
        quest_pages.append(page_metadata)

        event_title = record.event_name or record.related_event
        if not event_title or event_title == record.title or event_title in seen_event_titles:
            continue
        seen_event_titles.add(event_title)
        related_event_titles.append(event_title)

    event_pages: list[dict[str, Any]] = []
    for title in related_event_titles:
        payload = runtime.crawler.crawl_page(title, persist=not args.no_persist)
        page_metadata = _page_metadata(payload, title)
        if not args.no_persist:
            page_metadata["path"] = runtime.store.resolve_path("pages", title)
        event_pages.append(page_metadata)

    _print_json(
        {
            "category": category_name,
            "quests": quest_pages,
            "events": event_pages,
        }
    )
    return 0


# ========== parse 命令处理器 ==========


def handle_parse_page(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse page 命令：解析通用页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    result = runtime.parser.parse_page(payload).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["page"]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0


def handle_parse_chronicle(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse chronicle 命令：解析提瓦特编年史页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    result = runtime.parser.parse_chronicle_page(payload).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["chronicle"]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0


def handle_parse_character(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse character 命令：解析角色页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    voice_payload = _maybe_load_voice_payload(runtime.store, args.source_namespace, args.title)
    result = runtime.parser.parse_character_page(payload, voice_payload=voice_payload).to_storage_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["character"]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0


def handle_parse_archon_quest(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse archon-quest 命令：解析魔神任务页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    series_context = _maybe_load_archon_series_context(runtime, args.source_namespace)
    result = runtime.parser.parse_archon_quest_page(payload, series_context=series_context).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["archon-quest"]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0


def handle_parse_event_quest(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse event-quest 命令：解析活动任务页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    event_payload = _maybe_load_event_payload(runtime.store, runtime.parser, args.source_namespace, payload)
    result = runtime.parser.parse_event_quest_page(payload, event_payload=event_payload).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["event-quest"]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0


def handle_parse_weapon(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse weapon 命令：解析武器页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    result = runtime.parser.parse_weapon_page(payload).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["weapon"]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0


def handle_parse_artifact(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse artifact 命令：解析圣遗物套装页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    result = runtime.parser.parse_artifact_set_page(payload).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["artifact"]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0


def handle_parse_monster(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse monster 命令：解析怪物页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    result = runtime.parser.parse_monster_page(payload).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["monster"]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0


def _handle_specialized_parse(
    args: argparse.Namespace,
    runtime: CliRuntime,
    *,
    parse_method: str,
    namespace_key: str,
) -> int:
    """Run one of the structured parse handlers that share the same flow."""
    payload = runtime.store.read(args.source_namespace, args.title)
    result = getattr(runtime.parser, parse_method)(payload).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES[namespace_key]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0


def handle_parse_food(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse food 命令：解析食物页面。"""
    return _handle_specialized_parse(args, runtime, parse_method="parse_food_page", namespace_key="food")


def handle_parse_wildlife(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse wildlife 命令：解析野生生物页面。"""
    return _handle_specialized_parse(
        args,
        runtime,
        parse_method="parse_wildlife_page",
        namespace_key="wildlife",
    )


def handle_parse_quest_item(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse quest-item 命令：解析任务道具页面。"""
    return _handle_specialized_parse(
        args,
        runtime,
        parse_method="parse_quest_item_page",
        namespace_key="quest-item",
    )


def handle_parse_item(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse item 命令：解析道具页面。"""
    return _handle_specialized_parse(args, runtime, parse_method="parse_item_page", namespace_key="item")


def handle_parse_material(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse material 命令：解析材料页面。"""
    return _handle_specialized_parse(
        args,
        runtime,
        parse_method="parse_material_page",
        namespace_key="material",
    )


def handle_parse_namecard(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse namecard 命令：解析名片页面。"""
    return _handle_specialized_parse(
        args,
        runtime,
        parse_method="parse_namecard_page",
        namespace_key="namecard",
    )


def handle_parse_secret_item(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse secret-item 命令：解析秘境页面。"""
    return _handle_specialized_parse(
        args,
        runtime,
        parse_method="parse_secret_item_page",
        namespace_key="secret-item",
    )


def handle_parse_book(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse book 命令：解析书籍页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    result = runtime.parser.parse_book_page(payload).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["book"]
        runtime.store.write(namespace, args.title, result)
    _print_json(result)
    return 0

# ========== store 命令处理器 ==========


def _build_north_library_response(
    runtime: CliRuntime,
    *,
    title: str,
    output_namespace: str | None,
    persist: bool,
) -> dict[str, Any]:
    """Run the integrated North Library pipeline and return its structured result."""
    crawl_result = runtime.crawler.crawl_north_library(title, persist=persist)
    payload = crawl_result.pop("payload")
    record = runtime.parser.parse_north_library_page(payload)
    record.library_category = crawl_result["category_name"]
    record.category_candidates = crawl_result["category_candidates"]
    parsed = record.to_dict()

    response: dict[str, Any] = {
        **crawl_result,
        "parsed": parsed,
    }
    if persist:
        namespace = output_namespace or _DEFAULT_PARSE_NAMESPACES["north-library"]
        response["page_path"] = runtime.store.resolve_path("pages", record.title)
        response["parsed_path"] = runtime.store.write(namespace, record.title, parsed)
    return response


def _run_all_standard_entity(args: argparse.Namespace, runtime: CliRuntime) -> dict[str, Any]:
    """Run the shared standard-entity pipeline for one category-backed entity."""
    persist = not args.no_persist
    runtime.client.assert_api_allowed()
    config = _resolve_all_standard_config(args.entity_id)
    parse_method = getattr(runtime.parser, config.parse_method)
    titles = runtime.crawler.crawl_category_members(config.category, persist=persist)
    titles = _apply_page_limit(titles, args.page_limit)

    def process_title(title: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        payload = runtime.crawler.crawl_page(title, persist=persist)
        parsed = parse_method(payload).to_dict()
        return payload, parsed, {}

    results = _run_all_title_pipeline(
        runtime,
        titles=titles,
        output_namespace=config.output_namespaces[0],
        persist=persist,
        process_title=process_title,
    )
    return {
        "entity": config.entity_id,
        "persist": persist,
        "category": config.category,
        "selected_count": len(results),
        "results": results,
    }


def handle_all_standard_entity(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """Handle `python main.py all <standard-entity>`."""
    _print_json(_run_all_standard_entity(args, runtime))
    return 0


def _run_all_characters(args: argparse.Namespace, runtime: CliRuntime) -> dict[str, Any]:
    """Run the character pipeline, including the matching voice page for each title."""
    persist = not args.no_persist
    runtime.client.assert_api_allowed()
    category = ENTITY_CONFIGS["characters"].category
    titles = runtime.crawler.crawl_category_members(category, persist=persist)
    titles = _apply_page_limit(titles, args.page_limit)

    def process_title(title: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        payload = runtime.crawler.crawl_page(title, persist=persist)
        voice_title = f"{title}语音"
        voice_payload = runtime.crawler.crawl_page(voice_title, persist=persist)
        parsed = runtime.parser.parse_character_page(
            payload,
            voice_payload=voice_payload if _payload_has_wikitext(voice_payload) else None,
        ).to_storage_dict()
        extra: dict[str, Any] = {
            "voice_title": voice_title,
        }
        if persist:
            extra["voice_page_path"] = runtime.store.resolve_path("pages", voice_title)
        return payload, parsed, extra

    results = _run_all_title_pipeline(
        runtime,
        titles=titles,
        output_namespace=_DEFAULT_PARSE_NAMESPACES["character"],
        persist=persist,
        process_title=process_title,
    )
    return {
        "entity": "characters",
        "persist": persist,
        "category": category,
        "selected_count": len(results),
        "results": results,
    }


def handle_all_characters(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """Handle `python main.py all characters`."""
    _print_json(_run_all_characters(args, runtime))
    return 0


def _run_all_event_quests(args: argparse.Namespace, runtime: CliRuntime) -> dict[str, Any]:
    """Run the event-quest pipeline, including related event main pages."""
    persist = not args.no_persist
    runtime.client.assert_api_allowed()
    category_name = runtime.crawler.discover_event_quest_category(persist=persist)
    titles = runtime.crawler.crawl_category_members(category_name, persist=persist)
    titles = _apply_page_limit(titles, args.page_limit)
    event_pages: list[dict[str, Any]] = []
    event_payloads: dict[str, dict[str, Any]] = {}

    def process_title(title: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        payload = runtime.crawler.crawl_page(title, persist=persist)
        preview = runtime.parser.parse_event_quest_page(payload)
        event_title = preview.event_name or preview.related_event or ""
        if event_title and event_title != preview.title and event_title not in event_payloads:
            event_payload = runtime.crawler.crawl_page(event_title, persist=persist)
            event_payloads[event_title] = event_payload
            page_result = _page_metadata(event_payload, event_title)
            if persist:
                page_result["page_path"] = runtime.store.resolve_path("pages", event_title)
            event_pages.append(page_result)
        parsed = runtime.parser.parse_event_quest_page(
            payload,
            event_payload=event_payloads.get(event_title),
        ).to_dict()
        extra = {"event_title": event_title} if event_title else {}
        return payload, parsed, extra

    results = _run_all_title_pipeline(
        runtime,
        titles=titles,
        output_namespace=_DEFAULT_PARSE_NAMESPACES["event-quest"],
        persist=persist,
        process_title=process_title,
    )
    return {
        "entity": "event-quests",
        "persist": persist,
        "category": category_name,
        "selected_count": len(results),
        "event_page_count": len(event_pages),
        "results": results,
        "event_pages": event_pages,
    }


def handle_all_event_quests(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """Handle `python main.py all event-quests`."""
    _print_json(_run_all_event_quests(args, runtime))
    return 0


def _run_all_chronicles(args: argparse.Namespace, runtime: CliRuntime) -> dict[str, Any]:
    """Run the hardcoded chronicle title list through crawl + parse."""
    persist = not args.no_persist
    runtime.client.assert_api_allowed()
    titles = _apply_page_limit(list(_ALL_CHRONICLE_TITLES), args.page_limit)

    def process_title(title: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        payload = runtime.crawler.crawl_page(title, persist=persist)
        parsed = runtime.parser.parse_chronicle_page(payload).to_dict()
        return payload, parsed, {}

    results = _run_all_title_pipeline(
        runtime,
        titles=titles,
        output_namespace=_DEFAULT_PARSE_NAMESPACES["chronicle"],
        persist=persist,
        process_title=process_title,
    )
    return {
        "entity": "chronicles",
        "persist": persist,
        "selected_count": len(results),
        "results": results,
    }


def handle_all_chronicles(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """Handle `python main.py all chronicles`."""
    _print_json(_run_all_chronicles(args, runtime))
    return 0


def _run_all_north_library(args: argparse.Namespace, runtime: CliRuntime) -> dict[str, Any]:
    """Run the integrated North Library pipeline behind `python main.py all north-library`."""
    persist = not args.no_persist
    runtime.client.assert_api_allowed()
    response = _build_north_library_response(
        runtime,
        title="北陆图书馆",
        output_namespace=None,
        persist=persist,
    )
    return {
        "entity": "north-library",
        "persist": persist,
        "selected_count": 1,
        **response,
    }


def handle_all_north_library(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """Handle `python main.py all north-library`."""
    _print_json(_run_all_north_library(args, runtime))
    return 0


def _run_all_archon_quests(args: argparse.Namespace, runtime: CliRuntime) -> dict[str, Any]:
    """Run the archon-quest batch flow inside the unified CLI."""
    persist = not args.no_persist
    runtime.client.assert_api_allowed()
    helper_crawler = _AllHelperCrawler(runtime, persist=persist)
    output_path = runtime.store.root / _DEFAULT_ARCHON_QUEST_OUTPUT.name
    list_payload = runtime.crawler.crawl_page(_DEFAULT_ARCHON_QUEST_LIST_TITLE, persist=persist)
    index_entries = runtime.parser.parse_archon_quest_list_page(list_payload)
    index_entries = expand_archon_index_entries(
        store=runtime.store,
        crawler=helper_crawler,
        parser=runtime.parser,
        index_entries=index_entries,
    )
    index_entries = _apply_page_limit(index_entries, args.page_limit)
    series_context = runtime.parser.build_archon_series_context(index_entries)

    existing_output = _load_existing_archon_output(output_path) if getattr(args, "resume", False) else {}
    existing_records = existing_output.get("quests", []) if isinstance(existing_output.get("quests"), list) else []
    record_by_title = {
        item.get("任务标题", {}).get("中文", ""): item
        for item in existing_records
        if isinstance(item, dict)
    }

    results: list[dict[str, Any]] = []
    for entry in index_entries:
        title = entry["title"]
        if getattr(args, "resume", False) and title in record_by_title:
            item: dict[str, Any] = {
                "title": title,
                "resumed": True,
            }
            if persist and runtime.store.exists(_ARCHON_QUEST_OUTPUT_NAMESPACE, title):
                item["parsed_path"] = runtime.store.resolve_path(_ARCHON_QUEST_OUTPUT_NAMESPACE, title)
            elif not persist:
                item["parsed"] = record_by_title[title]
            results.append(item)
            continue

        payload = runtime.crawler.crawl_page(title, persist=persist)
        record = runtime.parser.parse_archon_quest_page(payload, series_context=series_context).to_dict()
        item = _page_metadata(payload, title)
        if persist:
            item["page_path"] = runtime.store.resolve_path("pages", title)
            item["parsed_path"] = runtime.store.write(_ARCHON_QUEST_OUTPUT_NAMESPACE, title, record)
        else:
            item["parsed"] = record
        results.append(item)
        record_by_title[title] = record

    for entry in index_entries:
        record = record_by_title.get(entry["title"], {})
        if not isinstance(record, dict):
            continue
        entry["act_name"] = _resolve_archon_index_act_name(entry, record)

    ordered_records = [record_by_title[entry["title"]] for entry in index_entries if entry["title"] in record_by_title]
    if persist:
        runtime.store.write(_ARCHON_QUEST_INDEX_NAMESPACE, _DEFAULT_ARCHON_QUEST_LIST_TITLE, index_entries)
        _write_archon_output(
            output_path,
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "list_title": _DEFAULT_ARCHON_QUEST_LIST_TITLE,
                "quest_count": len(ordered_records),
                "index": index_entries,
                "quests": ordered_records,
            },
        )

    response: dict[str, Any] = {
        "entity": "archon-quests",
        "persist": persist,
        "selected_count": len(results),
        "quest_count": len(ordered_records),
        "index_count": len(index_entries),
        "results": results,
    }
    if persist:
        response["output_path"] = str(output_path)
    return response


def handle_all_archon_quests(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """Handle `python main.py all archon-quests`."""
    _print_json(_run_all_archon_quests(args, runtime))
    return 0


def _run_all_character_quests(args: argparse.Namespace, runtime: CliRuntime) -> dict[str, Any]:
    """Run the character-quest batch flow inside the unified CLI."""
    persist = not args.no_persist
    runtime.client.assert_api_allowed()
    helper_crawler = _AllHelperCrawler(runtime, persist=persist)
    output_path = runtime.store.root / _DEFAULT_CHARACTER_QUEST_OUTPUT.name
    category_probe = discover_character_categories(runtime.store, helper_crawler)
    category_names = [
        name
        for name in category_probe.get("categories", [])
        if isinstance(name, str) and name
    ]

    list_payload = runtime.crawler.crawl_page(_DEFAULT_CHARACTER_QUEST_LIST_TITLE, persist=persist)
    list_entries = runtime.parser.parse_character_quest_list_page(list_payload)
    series_context = runtime.parser.build_character_quest_series_context(list_entries)

    member_titles: list[str] = []
    seen_members: set[str] = set()
    for category_name in category_names:
        for title in load_or_crawl_category_members(runtime.store, helper_crawler, category_name):
            if title in seen_members:
                continue
            seen_members.add(title)
            member_titles.append(title)

    existing_output = _load_existing_character_quest_output(output_path) if getattr(args, "resume", False) else {}
    existing_records = existing_output.get("quests", []) if isinstance(existing_output.get("quests"), list) else []
    record_by_title = {
        _character_quest_record_title(item): item
        for item in existing_records
        if isinstance(item, dict) and _character_quest_record_title(item)
    }

    results: list[dict[str, Any]] = []
    selected_record_titles: list[str] = []
    selected_record_title_set: set[str] = set()
    for title in member_titles:
        if args.page_limit is not None and len(results) >= args.page_limit:
            break

        canonical_title = _canonical_character_quest_title(title)
        if getattr(args, "resume", False) and canonical_title in record_by_title:
            if canonical_title in selected_record_title_set:
                continue
            item: dict[str, Any] = {
                "title": canonical_title,
                "source_title": title,
                "resumed": True,
            }
            if persist and runtime.store.exists(_CHARACTER_QUEST_OUTPUT_NAMESPACE, canonical_title):
                item["parsed_path"] = runtime.store.resolve_path(_CHARACTER_QUEST_OUTPUT_NAMESPACE, canonical_title)
            elif not persist:
                item["parsed"] = record_by_title[canonical_title]
            results.append(item)
            selected_record_titles.append(canonical_title)
            selected_record_title_set.add(canonical_title)
            continue

        payload = load_or_crawl_page(runtime.store, helper_crawler, title)
        if is_character_quest_series_payload(payload):
            continue

        record = runtime.parser.parse_character_quest_page(payload, series_context=series_context).to_dict()
        record_title = _character_quest_record_title(record) or canonical_title or title
        if record_title in selected_record_title_set:
            continue

        item = _page_metadata(payload, title)
        if record_title != title:
            item["parsed_title"] = record_title
        if persist:
            item["page_path"] = runtime.store.resolve_path("pages", title)
            item["parsed_path"] = runtime.store.write(_CHARACTER_QUEST_OUTPUT_NAMESPACE, record_title, record)
        else:
            item["parsed"] = record
        results.append(item)
        selected_record_titles.append(record_title)
        selected_record_title_set.add(record_title)
        record_by_title[record_title] = record

    filtered_records = {
        title: record_by_title[title]
        for title in selected_record_titles
        if title in record_by_title
    }
    ordered_records = order_character_records(list_entries, filtered_records)
    index_entries = build_character_quest_index(list_entries, ordered_records)
    if persist:
        runtime.store.write(_CHARACTER_QUEST_INDEX_NAMESPACE, _DEFAULT_CHARACTER_QUEST_LIST_TITLE, index_entries)
        _write_character_quest_output(
            output_path,
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "list_title": _DEFAULT_CHARACTER_QUEST_LIST_TITLE,
                "categories": category_names,
                "quest_count": len(ordered_records),
                "index": index_entries,
                "quests": ordered_records,
            },
        )

    response: dict[str, Any] = {
        "entity": "character-quests",
        "persist": persist,
        "selected_count": len(results),
        "quest_count": len(ordered_records),
        "index_count": len(index_entries),
        "results": results,
    }
    if persist:
        response["output_path"] = str(output_path)
    return response


def handle_all_character_quests(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """Handle `python main.py all character-quests`."""
    _print_json(_run_all_character_quests(args, runtime))
    return 0


def _run_all_entity(entity_id: str, args: argparse.Namespace, runtime: CliRuntime) -> dict[str, Any]:
    """Dispatch one entity id to its internal `all` runner."""
    if entity_id in _ALL_STANDARD_ENTITY_IDS:
        return _run_all_standard_entity(
            argparse.Namespace(
                entity_id=entity_id,
                page_limit=args.page_limit,
                no_persist=args.no_persist,
            ),
            runtime,
        )
    if entity_id == "characters":
        return _run_all_characters(args, runtime)
    if entity_id == "event-quests":
        return _run_all_event_quests(args, runtime)
    if entity_id == "chronicles":
        return _run_all_chronicles(args, runtime)
    if entity_id == "north-library":
        return _run_all_north_library(args, runtime)
    if entity_id == "archon-quests":
        return _run_all_archon_quests(args, runtime)
    if entity_id == "character-quests":
        return _run_all_character_quests(args, runtime)
    raise ValueError(f"unsupported all entity: {entity_id}")


def handle_all_everything(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """Handle `python main.py all` with no subcommand."""
    summaries = [
        _summarize_all_entity_result(_run_all_entity(entity_id, args, runtime))
        for entity_id in _ALL_ENTITY_ORDER
    ]
    _print_json(
        {
            "entity": "all",
            "persist": not args.no_persist,
            "page_limit": args.page_limit,
            "entities": summaries,
        }
    )
    return 0


def handle_store_put(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 store put 命令：创建或替换记录。"""
    payload = _load_payload(args)
    path = runtime.store.write(args.namespace, args.key, payload)
    _print_json(
        {
            "namespace": args.namespace,
            "key": args.key,
            "path": path,
        }
    )
    return 0


def handle_store_query(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 store query 命令：读取记录。"""
    _print_json(runtime.store.read(args.namespace, args.key))
    return 0


def handle_store_update(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 store update 命令：合并更新字典。"""
    payload = _load_payload(args)
    _print_json(runtime.store.update(args.namespace, args.key, payload))
    return 0


def handle_store_add(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 store add 命令：追加内容。"""
    payload = _load_payload(args)
    _print_json(runtime.store.add(args.namespace, args.key, payload))
    return 0


def handle_store_delete(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 store delete 命令：删除记录。"""
    deleted = runtime.store.delete(args.namespace, args.key)
    _print_json(
        {
            "namespace": args.namespace,
            "key": args.key,
            "deleted": deleted,
        }
    )
    return 0


def handle_store_exists(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 store exists 命令：检查记录是否存在。"""
    _print_json(
        {
            "namespace": args.namespace,
            "key": args.key,
            "exists": runtime.store.exists(args.namespace, args.key),
        }
    )
    return 0


def handle_store_list(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 store list 命令：列出命名空间中的记录。"""
    _print_json(runtime.store.list_keys(args.namespace))
    return 0


def main(argv: list[str] | None = None, runtime: CliRuntime | None = None) -> int:
    """
    CLI 主入口函数。

    参数
    ----
    argv : list[str] | None
        命令行参数列表，默认为 sys.argv
    runtime : CliRuntime | None
        运行时环境，用于测试时注入 mock 对象

    返回
    ----
    int
        命令退出码，0 表示成功
    """
    args = build_parser().parse_args(argv)
    active_runtime = runtime or build_runtime(args.data_root)
    handler: CliHandler = args.handler
    return handler(args, active_runtime)
