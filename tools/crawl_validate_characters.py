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

CHARACTER_STORAGE_GROUPS = (
    "角色",
    "角色故事",
    "冒险笔记",
    "权能",
    "壹·人物",
    "贰·故事",
    "角色语音",
)
CHARACTER_INFO_KEYS = (
    "名称",
    "称号",
    "全名",
    "所属",
    "出身",
    "种族",
    "介绍",
    "神之眼描述",
    "元素属性",
    "武器类型",
    "命之座",
    "特殊料理",
    "性别",
    "羁绊属性",
    "昵称/外号",
    "衣装名称",
    "归属",
    "职业",
)
CHARACTER_NON_EMPTY_INFO_KEYS = (
    "名称",
    "介绍",
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
    store: JsonFileStore,
) -> dict[str, Any]:
    """Validate stored raw and parsed data for one character."""
    character_info = character_record.get("角色", {})
    raw_ok = page_has_wikitext(payload)
    wikitext = next(iter(payload.get("query", {}).get("pages", {}).values()), {}).get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
    stored_paths = {
        "page": str(store.resolve_path("pages", title)),
        "voice_page": str(store.resolve_path("pages", f"{title}语音")),
        "character": str(store.resolve_path("parsed/characters", title)),
    }
    file_presence = {
        "page": store.exists("pages", title),
        "voice_page": store.exists("pages", f"{title}语音"),
        "character": store.exists("parsed/characters", title),
    }
    missing_groups = [group for group in CHARACTER_STORAGE_GROUPS if group not in character_record]
    missing_info_keys = (
        list(CHARACTER_INFO_KEYS)
        if not isinstance(character_info, dict)
        else [field for field in CHARACTER_INFO_KEYS if field not in character_info]
    )
    empty_info_keys = [] if not isinstance(character_info, dict) else missing_fields(character_info, CHARACTER_NON_EMPTY_INFO_KEYS)
    warnings: list[str] = []
    for group_name in ("冒险笔记", "权能", "壹·人物", "贰·故事"):
        if group_name in character_record and not character_record.get(group_name):
            warnings.append(group_name)

    critical_issues: list[str] = []
    if not isinstance(character_info, dict) or character_info.get("名称", "") != title:
        critical_issues.append("title_mismatch")
    if not raw_ok:
        critical_issues.append("missing_wikitext")
    if not all(file_presence.values()):
        critical_issues.append("storage_missing")
    if voice_payload is None or not page_has_wikitext(voice_payload):
        critical_issues.append("missing_voice_page")
    critical_issues.extend(f"group:{field}" for field in missing_groups)
    critical_issues.extend(f"character:{field}" for field in missing_info_keys)
    critical_issues.extend(f"character:{field}" for field in empty_info_keys)
    if not character_record.get("角色故事"):
        critical_issues.append("missing_story_records")
    if not character_record.get("角色语音"):
        critical_issues.append("missing_voice_records")
    if "壹·人物" in wikitext and not character_record.get("壹·人物"):
        warnings.append("壹·人物")
    if "贰·故事" in wikitext and not character_record.get("贰·故事"):
        warnings.append("贰·故事")

    return {
        "title": title,
        "page_id": None,
        "raw_ok": raw_ok,
        "storage_paths": stored_paths,
        "storage_exists": file_presence,
        "counts": {
            "角色信息字段数": len(character_info) if isinstance(character_info, dict) else 0,
            "角色故事": len(character_record.get("角色故事", {})),
            "角色语音": len(character_record.get("角色语音", {})),
            "冒险笔记": len(character_record.get("冒险笔记", {})),
            "壹·人物": len(character_record.get("壹·人物", {})),
            "贰·故事": len(character_record.get("贰·故事", {})),
        },
        "core_missing_fields": missing_groups + missing_info_keys + empty_info_keys,
        "story_missing_fields": [],
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
        ).to_storage_dict()
        store.write("parsed/characters", title, character_record)
        results.append(validate_character(title, payload, voice_payload, character_record, store))

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
