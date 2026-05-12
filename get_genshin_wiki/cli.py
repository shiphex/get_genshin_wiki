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
from pathlib import Path
from typing import Any, Callable

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
    "character": "parsed/characters",
    "weapon": "parsed/artifacts",
    "artifact": "parsed/weapons",
    "monster": "parsed/monsters",
    "food": "parsed/foods",
    "wildlife": "parsed/wildlife",
    "quest-item": "parsed/quest-items",
    "item": "parsed/items",
    "material": "parsed/materials",
    "namecard": "parsed/namecards",
    "secret-item": "parsed/secret-items",
    "book": "parsed/books",
}


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
    client = MediaWikiClient()
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

    # parse character：解析角色页面
    parse_character = parse_commands.add_parser("character", help="Parse a stored character page.")
    parse_character.add_argument("title", help="Character name")
    parse_character.add_argument("--source-namespace", default="pages")
    parse_character.add_argument("--output-namespace", default=None)
    parse_character.add_argument("--no-persist", action="store_true")
    parse_character.set_defaults(handler=handle_parse_character)

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
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))


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


# ========== crawl 命令处理器 ==========


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


def handle_parse_character(args: argparse.Namespace, runtime: CliRuntime) -> int:
    """处理 parse character 命令：解析角色页面。"""
    payload = runtime.store.read(args.source_namespace, args.title)
    result = runtime.parser.parse_character_page(payload).to_dict()
    if not args.no_persist:
        namespace = args.output_namespace or _DEFAULT_PARSE_NAMESPACES["character"]
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
