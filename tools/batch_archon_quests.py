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
from get_genshin_wiki.exceptions import GetGenshinWikiError
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore
from tools.reparse_and_store import build_session

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "archon_quests.json"
DEFAULT_LIST_TITLE = "魔神任务"
INDEX_NAMESPACE = "parsed/archon-quest-index"
OUTPUT_NAMESPACE = "parsed/archon-quests"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch parse archon quest pages from the bilibili wiki.")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--list-title", default=DEFAULT_LIST_TITLE)
    parser.add_argument("--resume", action="store_true")
    return parser


def load_or_crawl_page(store: JsonFileStore, crawler: WikiCrawler, title: str) -> dict[str, Any]:
    if store.exists("pages", title):
        return store.read("pages", title)
    return crawler.crawl_page(title, persist=True)


def _resolve_index_act_name(entry: dict[str, str], record: dict[str, Any]) -> str:
    parsed_act_name = record.get("幕名称") or ""
    act = record.get("幕") or entry.get("act", "")
    if parsed_act_name:
        return parsed_act_name
    if act:
        return act
    return entry.get("series_title", "") or entry.get("act_name", "")


def expand_archon_index_entries(
    *,
    store: JsonFileStore,
    crawler: WikiCrawler,
    parser: WikiTextParser,
    index_entries: list[dict[str, str]],
) -> list[dict[str, str]]:
    expanded_entries: list[dict[str, str]] = []
    seen_titles: set[str] = set()

    for entry in index_entries:
        source_title = entry["title"]

        # Filter out internal reference titles that are not real wiki pages
        if source_title.startswith("任务-"):
            continue

        try:
            payload = load_or_crawl_page(store, crawler, source_title)
            parsed_page = parser.parse_page(payload)
        except GetGenshinWikiError:
            # Page not found or no revisions — skip silently
            continue

        page_type, _ = parser._select_archon_quest_template(parsed_page.templates)

        resolved_titles = [source_title]
        if page_type in {"系列任务", "多重系列任务"}:
            resolved_titles = parser.extract_archon_series_quest_titles(parsed_page.wikitext)
            if not resolved_titles:
                try:
                    rendered_titles = crawler.client.fetch_rendered_section_titles(source_title)
                except GetGenshinWikiError:
                    rendered_titles = []
                resolved_titles = parser.extract_archon_series_quest_titles(
                    parsed_page.wikitext,
                    rendered_section_titles=rendered_titles,
                )
            if not resolved_titles:
                resolved_titles = [source_title]

        for resolved_title in resolved_titles:
            if resolved_title in seen_titles:
                continue
            seen_titles.add(resolved_title)
            expanded_entries.append(
                {
                    **entry,
                    "title": resolved_title,
                    "series_title": source_title if resolved_title != source_title else entry.get("series_title", ""),
                }
            )

    return expanded_entries


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

    list_payload = load_or_crawl_page(store, crawler, list_title)
    index_entries = parser.parse_archon_quest_list_page(list_payload)
    index_entries = expand_archon_index_entries(
        store=store,
        crawler=crawler,
        parser=parser,
        index_entries=index_entries,
    )
    series_context = parser.build_archon_series_context(index_entries)

    existing_output = load_existing_output(output_path) if resume else {}
    existing_records = existing_output.get("quests", []) if isinstance(existing_output.get("quests"), list) else []
    record_by_title = {
        item.get("任务标题", {}).get("中文", ""): item
        for item in existing_records
        if isinstance(item, dict)
    }

    for entry in index_entries:
        title = entry["title"]
        if resume and title in record_by_title:
            continue
        quest_payload = load_or_crawl_page(store, crawler, title)
        record = parser.parse_archon_quest_page(quest_payload, series_context=series_context).to_dict()
        store.write(OUTPUT_NAMESPACE, title, record)
        record_by_title[title] = record

    for entry in index_entries:
        record = record_by_title.get(entry["title"], {})
        if not isinstance(record, dict):
            continue
        entry["act_name"] = _resolve_index_act_name(entry, record)

    store.write(INDEX_NAMESPACE, list_title, index_entries)

    ordered_records = [record_by_title[entry["title"]] for entry in index_entries if entry["title"] in record_by_title]
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "list_title": list_title,
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
