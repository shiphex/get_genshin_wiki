from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from get_genshin_wiki.client import MediaWikiClient
from get_genshin_wiki.crawler import WikiCrawler
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore
from tools.batch_character_quests import (
    _canonical_character_quest_title,
    _record_title,
    discover_character_categories,
    is_character_quest_series_payload,
    load_or_crawl_category_members,
    load_or_crawl_page,
    order_character_records,
)
from tools.reparse_and_store import build_session

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "character_quest_index.json"
DEFAULT_LIST_TITLE = "传说任务"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a character quest index document.")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--list-title", default=DEFAULT_LIST_TITLE)
    return parser


def write_output(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def generate_character_quest_index_document(
    *,
    store: JsonFileStore,
    crawler: WikiCrawler,
    parser: WikiTextParser,
    list_title: str,
) -> dict[str, Any]:
    category_probe = discover_character_categories(store, crawler)
    category_names = [
        name
        for name in category_probe.get("categories", [])
        if isinstance(name, str) and name
    ]

    list_payload = load_or_crawl_page(store, crawler, list_title)
    list_entries = parser.parse_character_quest_list_page(list_payload)
    series_context = parser.build_character_quest_series_context(list_entries)

    member_titles: list[str] = []
    seen_titles: set[str] = set()
    for category_name in category_names:
        for title in load_or_crawl_category_members(store, crawler, category_name):
            if title in seen_titles:
                continue
            seen_titles.add(title)
            member_titles.append(title)

    record_by_title: dict[str, dict[str, Any]] = {}
    for title in member_titles:
        payload = load_or_crawl_page(store, crawler, title)
        if is_character_quest_series_payload(payload):
            continue
        record = parser.parse_character_quest_page(payload, series_context=series_context).to_dict()
        record_title = _record_title(record) or _canonical_character_quest_title(title) or title
        record_by_title[record_title] = record

    ordered_records = order_character_records(list_entries, record_by_title)
    index_items = [
        {
            "title": record.get("任务名称", ""),
            "region": record.get("任务地区", ""),
            "quest_type": record.get("任务类型", ""),
            "chapter_name": record.get("所属章", ""),
            "act": record.get("所属幕", ""),
            "act_name": record.get("所属幕名称", ""),
            "related_quest": record.get("所属任务", ""),
            "related_character": record.get("相关角色", ""),
            "前置任务": record.get("前置任务", ""),
            "后续任务": record.get("后续任务", ""),
        }
        for record in ordered_records
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "list_title": list_title,
        "categories": category_names,
        "quest_count": len(index_items),
        "index": index_items,
    }


def run_generate_index(
    *,
    data_root: Path,
    output_path: Path,
    list_title: str,
) -> dict[str, Any]:
    store = JsonFileStore(data_root)
    client = MediaWikiClient(session=build_session())
    crawler = WikiCrawler(client=client, store=store)
    parser = WikiTextParser()

    report = generate_character_quest_index_document(
        store=store,
        crawler=crawler,
        parser=parser,
        list_title=list_title,
    )
    write_output(output_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_generate_index(
        data_root=args.data_root,
        output_path=args.output,
        list_title=args.list_title,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "quest_count": report["quest_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
