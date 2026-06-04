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
from tools.batch_archon_quests import expand_archon_index_entries, load_or_crawl_page
from tools.reparse_and_store import build_session

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "archon_quest_index.json"
DEFAULT_LIST_TITLE = "魔神任务"
FIRST_ARCHON_QUEST_TITLE = "流浪者的足迹"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an archon quest index document.")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--list-title", default=DEFAULT_LIST_TITLE)
    return parser


def write_output(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _build_index_entry(
    *,
    title: str,
    chapter: str,
    chapter_name: str,
    act: str,
    act_name: str,
    series_title: str,
    prerequisite_title: str,
    follow_up_title: str,
) -> dict[str, str]:
    return {
        "title": title,
        "chapter": chapter,
        "chapter_name": chapter_name,
        "act": act,
        "act_name": act_name,
        "series_title": series_title,
        "前置任务名称": prerequisite_title,
        "后续任务名称": follow_up_title,
    }


def _resolve_reference_title(references: list[Any]) -> str:
    if not references:
        return ""
    return getattr(references[0], "title", "") or ""


def _resolve_index_act_name(entry: dict[str, str], record: dict[str, Any]) -> str:
    parsed_act_name = record.get("幕名称") or ""
    act = record.get("幕") or entry.get("act", "")
    if parsed_act_name:
        return parsed_act_name
    if act:
        return act
    return entry.get("series_title", "") or entry.get("act_name", "")


def _build_first_quest_entry(
    *,
    store: JsonFileStore,
    crawler: WikiCrawler,
    parser: WikiTextParser,
    series_context: dict[str, Any],
    fallback_next_title: str,
) -> dict[str, str]:
    follow_up_title = fallback_next_title
    try:
        payload = load_or_crawl_page(store, crawler, FIRST_ARCHON_QUEST_TITLE)
        record = parser.parse_archon_quest_page(payload, series_context=series_context)
        follow_up_title = _resolve_reference_title(record.follow_up_quests) or fallback_next_title
    except GetGenshinWikiError:
        pass

    return _build_index_entry(
        title=FIRST_ARCHON_QUEST_TITLE,
        chapter="",
        chapter_name="",
        act="",
        act_name="",
        series_title="",
        prerequisite_title="",
        follow_up_title=follow_up_title,
    )


def generate_archon_quest_index_document(
    *,
    store: JsonFileStore,
    crawler: WikiCrawler,
    parser: WikiTextParser,
    list_title: str,
) -> dict[str, Any]:
    list_payload = load_or_crawl_page(store, crawler, list_title)
    list_entries = parser.parse_archon_quest_list_page(list_payload)
    expanded_entries = expand_archon_index_entries(
        store=store,
        crawler=crawler,
        parser=parser,
        index_entries=list_entries,
    )
    expanded_entries = [entry for entry in expanded_entries if entry.get("title") != FIRST_ARCHON_QUEST_TITLE]
    series_context = parser.build_archon_series_context(expanded_entries)

    index_items: list[dict[str, str]] = [
        _build_first_quest_entry(
            store=store,
            crawler=crawler,
            parser=parser,
            series_context=series_context,
            fallback_next_title=expanded_entries[0]["title"] if expanded_entries else "",
        )
    ]

    for entry in expanded_entries:
        prerequisite_title = ""
        follow_up_title = ""
        resolved_act_name = entry.get("act_name", "")
        try:
            payload = load_or_crawl_page(store, crawler, entry["title"])
            record = parser.parse_archon_quest_page(payload, series_context=series_context)
            prerequisite_title = _resolve_reference_title(record.prerequisites)
            follow_up_title = _resolve_reference_title(record.follow_up_quests)
            record_payload = record.to_dict()
            resolved_act_name = _resolve_index_act_name(entry, record_payload)
        except GetGenshinWikiError:
            pass

        index_items.append(
            _build_index_entry(
                title=entry["title"],
                chapter=entry.get("chapter", ""),
                chapter_name=entry.get("chapter_name", ""),
                act=entry.get("act", ""),
                act_name=resolved_act_name,
                series_title=entry.get("series_title", ""),
                prerequisite_title=prerequisite_title,
                follow_up_title=follow_up_title,
            )
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "list_title": list_title,
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

    report = generate_archon_quest_index_document(
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
