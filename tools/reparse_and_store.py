from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from get_genshin_wiki.client import MediaWikiClient
from get_genshin_wiki.crawler import WikiCrawler
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore

REPORT_NAMESPACE = "reports"
REPORT_KEY = "todo-batch-report"
PYTEST_JUNIT_FILENAME = "todo-batch-pytest.xml"
DEFAULT_LIMIT = 15
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data"

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
ARTIFACT_SLOTS = ("时之沙", "死之羽", "理之冠", "生之花", "空之杯")


@dataclass(frozen=True)
class EntityConfig:
    """Batch configuration for one wiki entity category."""

    entity_id: str
    category: str
    parse_method: str | None
    output_namespaces: tuple[str, ...]
    required_fields: tuple[str, ...]
    nested_required_fields: dict[str, tuple[str, ...]] = field(default_factory=dict)
    list_item_required_fields: dict[str, tuple[str, ...]] = field(default_factory=dict)
    requires_voice_page: bool = False


@dataclass
class BatchRuntime:
    """Runtime dependencies shared by batch scripts."""

    data_root: Path
    store: JsonFileStore
    client: MediaWikiClient
    crawler: WikiCrawler
    parser: WikiTextParser


ENTITY_CONFIGS: dict[str, EntityConfig] = {
    "characters": EntityConfig(
        entity_id="characters",
        category="角色",
        parse_method=None,
        output_namespaces=("parsed/characters",),
        required_fields=CHARACTER_STORAGE_GROUPS,
        requires_voice_page=True,
    ),
    "weapons": EntityConfig(
        entity_id="weapons",
        category="武器",
        parse_method="parse_weapon_page",
        output_namespaces=("parsed/weapons",),
        required_fields=(
            "名称",
            "类型",
            "介绍",
            "突破武器材料序列",
            "突破高级材料序列",
            "突破普通材料序列",
            "获取途径",
            "锻造材料",
            "精炼材料",
            "故事",
        ),
    ),
    "artifacts": EntityConfig(
        entity_id="artifacts",
        category="圣遗物套装",
        parse_method="parse_artifact_set_page",
        output_namespaces=("parsed/artifacts",),
        required_fields=("名称", "获取方式", *ARTIFACT_SLOTS),
        nested_required_fields={slot: ("名称", "描述", "故事") for slot in ARTIFACT_SLOTS},
    ),
    "monsters": EntityConfig(
        entity_id="monsters",
        category="怪物",
        parse_method="parse_monster_page",
        output_namespaces=("parsed/monsters",),
        required_fields=(
            "title",
            "monster_class",
            "monster_category",
            "monster_type",
            "location",
            "drop_materials",
            "description",
        ),
    ),
    "books": EntityConfig(
        entity_id="books",
        category="书籍",
        parse_method="parse_book_page",
        output_namespaces=("parsed/books",),
        required_fields=("title", "genre", "country", "volumes", "page_id"),
        list_item_required_fields={"volumes": ("name", "description", "location", "content")},
    ),
    "foods": EntityConfig(
        entity_id="foods",
        category="食物",
        parse_method="parse_food_page",
        output_namespaces=("parsed/foods",),
        required_fields=("名称", "类型", "介绍", "所需食材", "食谱获取方式", "特殊料理", "特殊料理角色"),
        nested_required_fields={"介绍": ("普通料理", "完美料理", "失败料理")},
    ),
    "wildlife": EntityConfig(
        entity_id="wildlife",
        category="野生生物",
        parse_method="parse_wildlife_page",
        output_namespaces=("parsed/wildlife",),
        required_fields=("名称", "类型", "种类", "描述", "出现地点", "能否捕捉", "钓鱼信息"),
        nested_required_fields={"钓鱼信息": ("钓鱼鱼饵", "钓鱼时间", "钓鱼地点")},
    ),
    "quest-items": EntityConfig(
        entity_id="quest-items",
        category="任务道具",
        parse_method="parse_quest_item_page",
        output_namespaces=("parsed/quest-items",),
        required_fields=("名称", "类型", "描述", "相关任务", "获取方式", "内容"),
    ),
    "items": EntityConfig(
        entity_id="items",
        category="道具",
        parse_method="parse_item_page",
        output_namespaces=("parsed/items",),
        required_fields=("名称", "类型", "来源", "用途", "介绍"),
    ),
    "materials": EntityConfig(
        entity_id="materials",
        category="材料",
        parse_method="parse_material_page",
        output_namespaces=("parsed/materials",),
        required_fields=("名称", "类型", "来源", "介绍", "用途"),
    ),
    "namecards": EntityConfig(
        entity_id="namecards",
        category="名片",
        parse_method="parse_namecard_page",
        output_namespaces=("parsed/namecards",),
        required_fields=("名称", "获取方式", "描述"),
    ),
    "secret-items": EntityConfig(
        entity_id="secret-items",
        category="秘境",
        parse_method="parse_secret_item_page",
        output_namespaces=("parsed/secret-items",),
        required_fields=("名称", "类型", "介绍", "掉落"),
    ),
}

DEFAULT_ENTITY_ORDER = tuple(ENTITY_CONFIGS.keys())


def build_session() -> requests.Session:
    """Create a session that ignores broken proxy environment variables."""
    session = requests.Session()
    session.trust_env = False
    return session


def build_runtime(data_root: Path, *, assert_api_allowed: bool = False) -> BatchRuntime:
    """Assemble the batch runtime."""
    store = JsonFileStore(data_root)
    client = MediaWikiClient(session=build_session())
    crawler = WikiCrawler(client=client, store=store)
    parser = WikiTextParser()
    if assert_api_allowed:
        client.assert_api_allowed()
    return BatchRuntime(
        data_root=data_root,
        store=store,
        client=client,
        crawler=crawler,
        parser=parser,
    )


def resolve_entity_configs(selected: list[str] | None = None) -> list[EntityConfig]:
    """Resolve CLI-selected entities to concrete configs while preserving default order."""
    if not selected:
        return [ENTITY_CONFIGS[entity_id] for entity_id in DEFAULT_ENTITY_ORDER]
    unknown = sorted(set(selected).difference(ENTITY_CONFIGS))
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(f"unknown entities: {joined}")
    wanted = set(selected)
    return [ENTITY_CONFIGS[entity_id] for entity_id in DEFAULT_ENTITY_ORDER if entity_id in wanted]


def page_has_wikitext(payload: dict[str, Any]) -> bool:
    """Check whether a stored API payload has non-empty main-slot wikitext."""
    pages = payload.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    revisions = page.get("revisions", [])
    if not revisions:
        return False
    return bool(revisions[0].get("slots", {}).get("main", {}).get("*", "").strip())


def missing_fields(record: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    """Return missing or empty keys from a record."""
    missing: list[str] = []
    for key in keys:
        value = record.get(key)
        if value in (None, "", [], {}, ()):
            missing.append(key)
    return missing


def compute_pass_rate(passed: int, total: int) -> float:
    """Compute a percentage pass rate with two decimal places."""
    if total <= 0:
        return 0.0
    return round((passed / total) * 100, 2)


def build_stats(total: int, passed: int, failed: int) -> dict[str, Any]:
    """Build a stable count/pass-rate summary."""
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": compute_pass_rate(passed, total),
    }


def _collect_nested_missing(
    record: dict[str, Any],
    required_map: dict[str, tuple[str, ...]],
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for field, required_keys in required_map.items():
        nested = record.get(field)
        if not isinstance(nested, dict):
            missing[field] = list(required_keys)
            continue
        nested_missing = missing_fields(nested, required_keys)
        if nested_missing:
            missing[field] = nested_missing
    return missing


def _collect_list_item_missing(
    record: dict[str, Any],
    required_map: dict[str, tuple[str, ...]],
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for field, required_keys in required_map.items():
        items = record.get(field)
        if not isinstance(items, list) or not items:
            missing[field] = list(required_keys)
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                missing[f"{field}[{index}]"] = list(required_keys)
                continue
            item_missing = missing_fields(item, required_keys)
            if item_missing:
                missing[f"{field}[{index}]"] = item_missing
    return missing


def _validate_secret_item_drops(record: dict[str, Any]) -> dict[str, list[str]]:
    domain_type = str(record.get("类型", ""))
    drops = record.get("掉落")
    if not isinstance(drops, dict):
        if "圣遗物秘境" in domain_type:
            return {"掉落": ["圣遗物1", "圣遗物2"]}
        if "BOSS秘境" in domain_type:
            return {"掉落": ["材料1", "材料2", "材料3"]}
        if "武器突破材料秘境" in domain_type:
            return {"掉落": ["武器突破材料1", "武器突破材料2", "武器突破材料3"]}
        return {"掉落": ["天赋技能材料1", "天赋技能材料2", "天赋技能材料3"]}
    if "圣遗物秘境" in domain_type:
        required = ("圣遗物1", "圣遗物2")
    elif "BOSS秘境" in domain_type:
        required = ("材料1", "材料2", "材料3")
    elif "武器突破材料秘境" in domain_type:
        required = ("武器突破材料1", "武器突破材料2", "武器突破材料3")
    else:
        required = ("天赋技能材料1", "天赋技能材料2", "天赋技能材料3")
    nested_missing = missing_fields(drops, required)
    return {"掉落": nested_missing} if nested_missing else {}


def validate_generic_record(
    config: EntityConfig,
    title: str,
    payload: dict[str, Any],
    record: dict[str, Any],
    store: JsonFileStore,
) -> dict[str, Any]:
    """Validate one non-character entity record."""
    raw_ok = page_has_wikitext(payload)
    storage_exists = {
        "page": store.exists("pages", title),
        "parsed": store.exists(config.output_namespaces[0], title),
    }
    missing_top_level = missing_fields(record, config.required_fields)
    missing_nested = _collect_nested_missing(record, config.nested_required_fields)
    missing_list_items = _collect_list_item_missing(record, config.list_item_required_fields)
    if config.entity_id == "secret-items":
        secret_item_missing = _validate_secret_item_drops(record)
        if secret_item_missing:
            missing_nested.update(secret_item_missing)

    issues: list[str] = []
    if not raw_ok:
        issues.append("missing_wikitext")
    if not all(storage_exists.values()):
        issues.append("storage_missing")
    issues.extend(f"field:{field}" for field in missing_top_level)
    for field, nested_missing in missing_nested.items():
        issues.extend(f"{field}:{name}" for name in nested_missing)
    for field, item_missing in missing_list_items.items():
        issues.extend(f"{field}:{name}" for name in item_missing)

    return {
        "title": title,
        "raw_ok": raw_ok,
        "storage_exists": storage_exists,
        "missing_fields": missing_top_level,
        "missing_nested_fields": missing_nested,
        "missing_list_item_fields": missing_list_items,
        "issues": issues,
        "warnings": [],
        "ok": not issues,
    }


def _load_voice_payload(store: JsonFileStore, title: str) -> dict[str, Any] | None:
    voice_title = f"{title}语音"
    if not store.exists("pages", voice_title):
        return None
    payload = store.read("pages", voice_title)
    return payload if page_has_wikitext(payload) else None


def validate_character_records(
    title: str,
    payload: dict[str, Any],
    voice_payload: dict[str, Any] | None,
    character_record: dict[str, Any],
    store: JsonFileStore,
) -> dict[str, Any]:
    """Validate stored raw and parsed character data."""
    character_info = character_record.get("角色", {})
    raw_ok = page_has_wikitext(payload)
    wikitext = next(iter(payload.get("query", {}).get("pages", {}).values()), {}).get("revisions", [{}])[0].get(
        "slots",
        {},
    ).get("main", {}).get("*", "")
    storage_exists = {
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

    issues: list[str] = []
    if not isinstance(character_info, dict) or character_info.get("名称", "") != title:
        issues.append("title_mismatch")
    if not raw_ok:
        issues.append("missing_wikitext")
    if not all(storage_exists.values()):
        issues.append("storage_missing")
    if voice_payload is None or not page_has_wikitext(voice_payload):
        issues.append("missing_voice_page")
    issues.extend(f"group:{field}" for field in missing_groups)
    issues.extend(f"character:{field}" for field in missing_info_keys)
    issues.extend(f"character:{field}" for field in empty_info_keys)
    if not character_record.get("角色故事"):
        issues.append("missing_story_records")
    if not character_record.get("角色语音"):
        issues.append("missing_voice_records")
    if "壹·人物" in wikitext and not character_record.get("壹·人物"):
        warnings.append("壹·人物")
    if "贰·故事" in wikitext and not character_record.get("贰·故事"):
        warnings.append("贰·故事")

    return {
        "title": title,
        "page_id": None,
        "raw_ok": raw_ok,
        "storage_exists": storage_exists,
        "missing_fields": missing_groups + missing_info_keys + empty_info_keys,
        "missing_nested_fields": {},
        "missing_list_item_fields": {},
        "issues": issues,
        "warnings": sorted(set(warnings)),
        "ok": not issues,
    }


def _read_payload(store: JsonFileStore, title: str) -> dict[str, Any]:
    return store.read("pages", title)


def _parse_character(runtime: BatchRuntime, title: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    payload = _read_payload(runtime.store, title)
    voice_payload = _load_voice_payload(runtime.store, title)
    character_record = runtime.parser.parse_character_page(payload, voice_payload=voice_payload).to_storage_dict()
    runtime.store.write("parsed/characters", title, character_record)
    return character_record, voice_payload


def _parse_generic(runtime: BatchRuntime, config: EntityConfig, title: str) -> dict[str, Any]:
    payload = _read_payload(runtime.store, title)
    record = getattr(runtime.parser, config.parse_method)(payload).to_dict()
    runtime.store.write(config.output_namespaces[0], title, record)
    return record


def _build_crawl_error_result(title: str, reason: str, details: str) -> dict[str, Any]:
    return {
        "title": title,
        "raw_ok": False,
        "storage_exists": {},
        "missing_fields": [],
        "missing_nested_fields": {},
        "missing_list_item_fields": {},
        "issues": [reason],
        "warnings": [],
        "ok": False,
        "error": details,
    }


def _process_entity(
    runtime: BatchRuntime,
    config: EntityConfig,
    *,
    limit: int,
    fetch_pages: bool,
) -> dict[str, Any]:
    entity_failures: list[str] = []
    try:
        if fetch_pages:
            titles = runtime.crawler.crawl_category_members(config.category, persist=True)
        else:
            titles = runtime.store.read("category_members", config.category)
    except FileNotFoundError:
        titles = []
        entity_failures.append("missing_category_members")

    member_count = len(titles)
    if member_count < limit:
        entity_failures.append("insufficient_members")
    selected_titles = titles[:limit]

    results: list[dict[str, Any]] = []
    crawled_count = 0
    parsed_count = 0

    for title in selected_titles:
        if fetch_pages:
            try:
                payload = runtime.crawler.crawl_page(title, persist=True)
                crawled_count += 1 if page_has_wikitext(payload) else 0
                if config.requires_voice_page:
                    runtime.crawler.crawl_page(f"{title}语音", persist=True)
            except Exception as exc:  # noqa: BLE001
                results.append(_build_crawl_error_result(title, "crawl_error", str(exc)))
                continue
        else:
            try:
                payload = _read_payload(runtime.store, title)
            except FileNotFoundError:
                results.append(_build_crawl_error_result(title, "missing_page_payload", "page payload not found"))
                continue
            crawled_count += 1 if page_has_wikitext(payload) else 0

        try:
            if config.entity_id == "characters":
                character_record, voice_payload = _parse_character(runtime, title)
                parsed_count += 1
                results.append(
                    validate_character_records(
                        title,
                        payload,
                        voice_payload,
                        character_record,
                        runtime.store,
                    )
                )
            else:
                record = _parse_generic(runtime, config, title)
                parsed_count += 1
                results.append(validate_generic_record(config, title, payload, record, runtime.store))
        except Exception as exc:  # noqa: BLE001
            results.append(_build_crawl_error_result(title, "parse_error", str(exc)))

    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    failure_reasons = sorted({reason for item in results for reason in item["issues"]}.union(entity_failures))
    return {
        "entity": config.entity_id,
        "category": config.category,
        "requested_count": limit,
        "member_count": member_count,
        "selected_count": len(selected_titles),
        "crawled_count": crawled_count,
        "parsed_count": parsed_count,
        "validation_passed": passed,
        "validation_failed": failed,
        "failure_reasons": failure_reasons,
        "output_namespaces": list(config.output_namespaces),
        "results": results,
    }


def summarize_validation(entity_reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize validation outcomes across entity reports."""
    total = sum(report["selected_count"] for report in entity_reports)
    passed = sum(report["validation_passed"] for report in entity_reports)
    failed = sum(report["validation_failed"] for report in entity_reports)
    return build_stats(total=total, passed=passed, failed=failed)


def summarize_entity_report(entity_report: dict[str, Any]) -> dict[str, Any]:
    """Return the stable per-entity summary shape written into reports."""
    return {
        "entity": entity_report["entity"],
        "category": entity_report["category"],
        "requested_count": entity_report["requested_count"],
        "member_count": entity_report["member_count"],
        "selected_count": entity_report["selected_count"],
        "crawled_count": entity_report["crawled_count"],
        "parsed_count": entity_report["parsed_count"],
        "validation_passed": entity_report["validation_passed"],
        "validation_failed": entity_report["validation_failed"],
        "failure_reasons": entity_report["failure_reasons"],
        "output_namespaces": entity_report["output_namespaces"],
    }


def parse_junit_summary(path: Path) -> dict[str, Any]:
    """Parse a junit XML report into compact pytest summary counts."""
    tree = ET.parse(path)
    root = tree.getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise ValueError(f"could not find testsuite in {path}")
    collected = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    failed = failures + errors
    passed = max(collected - failed - skipped, 0)
    return {
        "collected": collected,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": compute_pass_rate(passed, collected),
    }


def run_pytest_suite(project_root: Path, data_root: Path) -> dict[str, Any]:
    """Run the test suite and capture a compact summary plus junit XML."""
    reports_dir = data_root / REPORT_NAMESPACE
    reports_dir.mkdir(parents=True, exist_ok=True)
    junit_path = reports_dir / PYTEST_JUNIT_FILENAME
    command = [sys.executable, "-m", "pytest", "-q", "tests", f"--junitxml={junit_path}"]
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    summary = parse_junit_summary(junit_path) if junit_path.exists() else {
        "collected": 0,
        "passed": 0,
        "failed": 1,
        "skipped": 0,
        "pass_rate": 0.0,
    }
    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    stderr_lines = [line for line in completed.stderr.splitlines() if line.strip()]
    return {
        **summary,
        "exit_code": completed.returncode,
        "junit_path": str(junit_path),
        "summary_line": stdout_lines[-1] if stdout_lines else "",
        "stderr_tail": stderr_lines[-5:],
    }


def write_report(store: JsonFileStore, report: dict[str, Any], key: str = REPORT_KEY) -> Path:
    """Persist the final batch report."""
    return store.write(REPORT_NAMESPACE, key, report)


def run_batch(
    *,
    data_root: Path,
    entity_ids: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    fetch_pages: bool,
    include_pytest: bool,
    report_key: str = REPORT_KEY,
) -> dict[str, Any]:
    """Run one full batch workflow and return the persisted report payload."""
    configs = resolve_entity_configs(entity_ids)
    runtime = build_runtime(data_root, assert_api_allowed=fetch_pages)
    entity_reports = [
        _process_entity(runtime, config, limit=limit, fetch_pages=fetch_pages)
        for config in configs
    ]
    validation_summary = summarize_validation(entity_reports)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "crawl-and-parse" if fetch_pages else "parse-only",
        "entities": [summarize_entity_report(report) for report in entity_reports],
        "results": {report["entity"]: report["results"] for report in entity_reports},
        "validation": validation_summary,
    }
    if include_pytest:
        report["pytest"] = run_pytest_suite(PROJECT_ROOT, data_root)

    report_path = write_report(runtime.store, report, key=report_key)
    report["report_path"] = str(report_path)
    runtime.store.write(REPORT_NAMESPACE, report_key, report)
    return report


def print_report_summary(report: dict[str, Any]) -> None:
    """Print the most important report summary as JSON."""
    payload = {
        "mode": report["mode"],
        "validation": report["validation"],
        "pytest": report.get("pytest"),
        "report_path": report["report_path"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
