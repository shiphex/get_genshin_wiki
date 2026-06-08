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
from tools.reparse_and_store import build_session

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "character_quests.json"
DEFAULT_LIST_TITLE = "传说任务"
INDEX_NAMESPACE = "parsed/character-quest-index"
OUTPUT_NAMESPACE = "parsed/character-quests"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch parse character quest pages from the bilibili wiki.")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--list-title", default=DEFAULT_LIST_TITLE)
    parser.add_argument("--resume", action="store_true")
    return parser


def load_or_crawl_page(store: JsonFileStore, crawler: WikiCrawler, title: str) -> dict[str, Any]:
    if store.exists("pages", title):
        return store.read("pages", title)
    return crawler.crawl_page(title, persist=True)


def load_or_crawl_category_members(
    store: JsonFileStore,
    crawler: WikiCrawler,
    category_name: str,
) -> list[str]:
    if store.exists("category_members", category_name):
        payload = store.read("category_members", category_name)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, str)]
    return crawler.crawl_category_members(category_name, persist=True)


def discover_character_categories(store: JsonFileStore, crawler: WikiCrawler) -> dict[str, Any]:
    if store.exists("categories", "character-quests"):
        payload = store.read("categories", "character-quests")
        if isinstance(payload, dict):
            return payload
    return crawler.discover_character_quest_categories(persist=True)


def load_existing_output(output_path: Path) -> dict[str, Any]:
    if not output_path.exists():
        return {}
    with output_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def write_output(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _page_categories(payload: dict[str, Any]) -> list[str]:
    page = next(iter(payload.get("query", {}).get("pages", {}).values()), {})
    categories = page.get("categories", [])
    results: list[str] = []
    for item in categories:
        title = item.get("title", "")
        if not isinstance(title, str):
            continue
        normalized = title.split(":", 1)[1] if ":" in title else title
        normalized = normalized.strip()
        if normalized:
            results.append(normalized)
    return results


def is_character_quest_series_payload(payload: dict[str, Any]) -> bool:
    categories = set(_page_categories(payload))
    return "系列任务" in categories or "多重系列任务" in categories


def _record_title(record: dict[str, Any]) -> str:
    title = record.get("任务名称", "")
    return title if isinstance(title, str) else ""


def _canonical_character_quest_title(title: str) -> str:
    normalized = title.strip()
    for suffix in ("（系列任务）", "(系列任务)", "（任务）", "(任务)"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].strip()
    return normalized


def _record_group_key(record: dict[str, Any]) -> str:
    for key in ("所属任务", "所属幕名称", "任务名称"):
        value = record.get(key, "")
        if isinstance(value, str) and value:
            return value
    return ""


def _order_group_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(records) <= 1:
        return list(records)
    by_title = {
        _record_title(record): record
        for record in records
        if _record_title(record)
    }
    if len(by_title) != len(records):
        return sorted(records, key=lambda item: _record_title(item))

    starts = [
        title
        for title, record in by_title.items()
        if record.get("前置任务", "") not in by_title
    ]
    ordered: list[dict[str, Any]] = []
    visited: set[str] = set()
    for start in starts or sorted(by_title):
        current = start
        while current and current not in visited and current in by_title:
            visited.add(current)
            record = by_title[current]
            ordered.append(record)
            next_title = record.get("后续任务", "")
            current = next_title if isinstance(next_title, str) else ""

    for title in sorted(by_title):
        if title in visited:
            continue
        ordered.append(by_title[title])
    return ordered


def build_character_quest_index(
    list_entries: list[dict[str, str]],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped_records: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped_records.setdefault(_record_group_key(record), []).append(record)

    index_entries: list[dict[str, Any]] = []
    consumed_groups: set[str] = set()
    for entry in list_entries:
        group_key = entry.get("title", "")
        group_records = _order_group_records(grouped_records.get(group_key, []))
        if not group_records:
            continue
        consumed_groups.add(group_key)
        index_entries.append(
            {
                "title": group_key,
                "chapter_name": entry.get("chapter_name", ""),
                "act": entry.get("act", ""),
                "act_name": entry.get("act_name", ""),
                "region": entry.get("region", ""),
                "quest_type": entry.get("quest_type", ""),
                "related_character": entry.get("related_character", ""),
                "tasks": [_record_title(record) for record in group_records if _record_title(record)],
            }
        )

    for group_key in sorted(grouped_records):
        if group_key in consumed_groups:
            continue
        group_records = _order_group_records(grouped_records[group_key])
        first_record = group_records[0]
        index_entries.append(
            {
                "title": group_key,
                "chapter_name": first_record.get("所属章", ""),
                "act": first_record.get("所属幕", ""),
                "act_name": first_record.get("所属幕名称", ""),
                "region": first_record.get("任务地区", ""),
                "quest_type": first_record.get("任务类型", ""),
                "related_character": first_record.get("相关角色", ""),
                "tasks": [_record_title(record) for record in group_records if _record_title(record)],
            }
        )
    return index_entries


def order_character_records(
    list_entries: list[dict[str, str]],
    record_by_title: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped_records: dict[str, list[dict[str, Any]]] = {}
    for record in record_by_title.values():
        grouped_records.setdefault(_record_group_key(record), []).append(record)

    ordered: list[dict[str, Any]] = []
    consumed_titles: set[str] = set()
    for entry in list_entries:
        group_key = entry.get("title", "")
        for record in _order_group_records(grouped_records.get(group_key, [])):
            title = _record_title(record)
            if not title or title in consumed_titles:
                continue
            consumed_titles.add(title)
            ordered.append(record)

    for title in sorted(record_by_title):
        if title in consumed_titles:
            continue
        ordered.append(record_by_title[title])
    return ordered


def run_batch(
    *,
    data_root: Path,
    output_path: Path,
    list_title: str,
    resume: bool,
) -> dict[str, Any]:
    store = JsonFileStore(data_root)
    client = MediaWikiClient(session=build_session())
    crawler = WikiCrawler(client=client, store=store)
    parser = WikiTextParser()

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
    seen_members: set[str] = set()
    for category_name in category_names:
        for title in load_or_crawl_category_members(store, crawler, category_name):
            if title in seen_members:
                continue
            seen_members.add(title)
            member_titles.append(title)

    existing_output = load_existing_output(output_path) if resume else {}
    existing_records = existing_output.get("quests", []) if isinstance(existing_output.get("quests"), list) else []
    record_by_title = {
        _record_title(item): item
        for item in existing_records
        if isinstance(item, dict) and _record_title(item)
    }

    for title in member_titles:
        canonical_title = _canonical_character_quest_title(title)
        if resume and canonical_title in record_by_title:
            continue
        payload = load_or_crawl_page(store, crawler, title)
        if is_character_quest_series_payload(payload):
            continue
        record = parser.parse_character_quest_page(payload, series_context=series_context).to_dict()
        record_title = _record_title(record) or canonical_title or title
        store.write(OUTPUT_NAMESPACE, record_title, record)
        record_by_title[record_title] = record

    ordered_records = order_character_records(list_entries, record_by_title)
    index_entries = build_character_quest_index(list_entries, ordered_records)
    store.write(INDEX_NAMESPACE, list_title, index_entries)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "list_title": list_title,
        "categories": category_names,
        "quest_count": len(ordered_records),
        "index": index_entries,
        "quests": ordered_records,
    }
    write_output(output_path, output)
    return output


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_batch(
        data_root=args.data_root,
        output_path=args.output,
        list_title=args.list_title,
        resume=args.resume,
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
