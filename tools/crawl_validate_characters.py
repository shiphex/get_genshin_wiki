from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from get_genshin_wiki.client import MediaWikiClient
from get_genshin_wiki.crawler import WikiCrawler
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore

DEFAULT_TITLES = [
    "哥伦比娅",
    "阿蕾奇诺",
    "芙宁娜",
    "那维莱特",
    "钟离",
    "温迪",
    "雷电将军",
    "纳西妲",
    "胡桃",
    "神里绫华",
]

CORE_REQUIRED_FIELDS = (
    "title",
    "page_id",
    "summary",
    "attributes",
    "sections",
    "templates",
    "element",
    "weapon_type",
)
STORY_REQUIRED_FIELDS = (
    "story_records",
    "voice_records",
)


def build_session() -> requests.Session:
    """Create a session that ignores broken proxy env vars in this workspace."""
    session = requests.Session()
    session.trust_env = False
    return session


def build_runtime(data_root: Path) -> tuple[JsonFileStore, WikiCrawler, WikiTextParser]:
    """Assemble store, crawler, and parser for the batch job."""
    store = JsonFileStore(data_root)
    client = MediaWikiClient(session=build_session())
    crawler = WikiCrawler(client=client, store=store)
    parser = WikiTextParser()
    client.assert_api_allowed()
    return store, crawler, parser


def page_has_wikitext(payload: dict[str, Any]) -> bool:
    """Check whether the raw page payload contains non-empty main-slot content."""
    pages = payload.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    revisions = page.get("revisions", [])
    if not revisions:
        return False
    return bool(revisions[0].get("slots", {}).get("main", {}).get("*", "").strip())


def missing_fields(record: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    """Return record fields that are empty or missing."""
    missing: list[str] = []
    for key in keys:
        value = record.get(key)
        if value in (None, "", [], {}, ()):
            missing.append(key)
    return missing


def validate_character(
    title: str,
    payload: dict[str, Any],
    voice_payload: dict[str, Any] | None,
    character_record: dict[str, Any],
    story_record: dict[str, Any],
    store: JsonFileStore,
) -> dict[str, Any]:
    """Validate stored raw and parsed data for one character."""
    page_title = character_record.get("title", "")
    raw_ok = page_has_wikitext(payload)
    wikitext = next(iter(payload.get("query", {}).get("pages", {}).values()), {}).get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
    stored_paths = {
        "page": str(store.resolve_path("pages", title)),
        "voice_page": str(store.resolve_path("pages", f"{title}语音")),
        "character": str(store.resolve_path("parsed/characters", title)),
        "character_story": str(store.resolve_path("parsed/character-stories", title)),
    }
    file_presence = {
        "page": store.exists("pages", title),
        "voice_page": store.exists("pages", f"{title}语音"),
        "character": store.exists("parsed/characters", title),
        "character_story": store.exists("parsed/character-stories", title),
    }
    core_missing = missing_fields(character_record, CORE_REQUIRED_FIELDS)
    story_missing = missing_fields(story_record, STORY_REQUIRED_FIELDS)
    warnings: list[str] = []
    if not character_record.get("talents"):
        warnings.append("talents")
    if not character_record.get("constellations"):
        warnings.append("constellations")
    if not character_record.get("story_records"):
        warnings.append("story_records")
    if not character_record.get("full_name"):
        warnings.append("full_name")
    if not character_record.get("introduction"):
        warnings.append("introduction")
    if not character_record.get("categories"):
        warnings.append("categories")

    critical_issues: list[str] = []
    if page_title != title:
        critical_issues.append("title_mismatch")
    if not raw_ok:
        critical_issues.append("missing_wikitext")
    if not all(file_presence.values()):
        critical_issues.append("storage_missing")
    if voice_payload is None or not page_has_wikitext(voice_payload):
        critical_issues.append("missing_voice_page")
    critical_issues.extend(f"core:{field}" for field in core_missing)
    critical_issues.extend(f"story:{field}" for field in story_missing)
    if "壹·人物" in wikitext and not character_record.get("character_introductions"):
        critical_issues.append("missing_character_introductions")
    if "贰·故事" in wikitext and not character_record.get("story_sections"):
        critical_issues.append("missing_story_sections")

    return {
        "title": title,
        "page_id": character_record.get("page_id"),
        "raw_ok": raw_ok,
        "storage_paths": stored_paths,
        "storage_exists": file_presence,
        "counts": {
            "attributes": len(character_record.get("attributes", {})),
            "talents": len(character_record.get("talents", [])),
            "constellations": len(character_record.get("constellations", [])),
            "story_records": len(character_record.get("story_records", [])),
            "voice_records": len(character_record.get("voice_records", [])),
            "adventure_notes": len(character_record.get("adventure_notes", [])),
            "character_introductions": len(character_record.get("character_introductions", [])),
            "story_sections": len(character_record.get("story_sections", [])),
        },
        "core_missing_fields": core_missing,
        "story_missing_fields": story_missing,
        "warnings": sorted(set(warnings)),
        "critical_issues": critical_issues,
        "ok": not critical_issues,
    }


def run_batch(data_root: Path, titles: list[str]) -> dict[str, Any]:
    """Crawl, parse, store, and validate a batch of character pages."""
    store, crawler, parser = build_runtime(data_root)
    store.write("category_members", "batch::10-characters", titles)

    results: list[dict[str, Any]] = []
    for title in titles:
        payload = crawler.crawl_page(title, persist=True)
        voice_title = f"{title}语音"
        voice_payload = crawler.crawl_page(voice_title, persist=True)
        usable_voice_payload = voice_payload if page_has_wikitext(voice_payload) else None
        character_record = parser.parse_character_page(
            payload,
            voice_payload=usable_voice_payload,
        ).to_dict()
        story_record = parser.parse_character_story_page(
            payload,
            voice_payload=usable_voice_payload,
        )
        store.write("parsed/characters", title, character_record)
        store.write("parsed/character-stories", title, story_record)
        results.append(validate_character(title, payload, voice_payload, character_record, story_record, store))

    summary = {
        "requested_count": len(titles),
        "ok_count": sum(1 for item in results if item["ok"]),
        "warning_count": sum(1 for item in results if item["warnings"]),
        "critical_count": sum(1 for item in results if item["critical_issues"]),
        "titles": titles,
    }
    report = {
        "summary": summary,
        "results": results,
    }
    store.write("reports", "character-integrity-report", report)
    return report


def parse_args() -> argparse.Namespace:
    """Parse batch script arguments."""
    parser = argparse.ArgumentParser(description="Crawl, parse, store, and validate 10 character pages.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        help="Root directory used by JsonFileStore.",
    )
    parser.add_argument(
        "--title",
        dest="titles",
        action="append",
        default=None,
        help="Character title to include. Repeat for multiple titles. Defaults to the built-in 10-character batch.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the batch job and print the report summary."""
    args = parse_args()
    titles = args.titles or list(DEFAULT_TITLES)
    report = run_batch(args.data_root, titles)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if report["summary"]["critical_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
