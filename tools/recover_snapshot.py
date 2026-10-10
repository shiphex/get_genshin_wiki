"""Recover a frozen snapshot without crawling, models, or input writes."""
from __future__ import annotations

import argparse
import collections
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mwparserfromhell as mw

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.recovery.audit import audit_page
from get_genshin_wiki.recovery.display import display_text, replay_unit
from get_genshin_wiki.recovery.source import SourcePage, stable_id
from get_genshin_wiki.storage import JsonFileStore


@contextmanager
def offline_guard():
    def forbidden(*args, **kwargs):
        raise RuntimeError("network access forbidden during offline recovery")

    with ExitStack() as stack:
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection", "socket.getaddrinfo", "requests.sessions.Session.request"):
            stack.enter_context(patch(target, forbidden))
        yield


def snapshot_manifest(root: Path):
    files = []
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        files.append({"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    fingerprint = hashlib.sha256(json.dumps(files, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"file_count": len(files), "fingerprint_sha256": fingerprint, "files": files}


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")


def validate_paths(input_root: Path, output_root: Path):
    if not input_root.is_dir() or not (input_root / "pages").is_dir():
        raise ValueError("input root must contain a frozen pages directory")
    if output_root == input_root or output_root.is_relative_to(input_root) or input_root.is_relative_to(output_root):
        raise ValueError("input and output directories must be disjoint")
    if any(part.lower() in {"raw", "pages", "parsed", "category_members"} for part in output_root.parts):
        raise ValueError("output root must be outside existing raw/parsed storage")
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise ValueError("output root is non-empty; use a new recovery directory")


def _business_record(parser, payload, source, resolver):
    """Reuse existing pure parse APIs; never run a batch runtime or crawler."""
    # Only read the static entity registry; importing it does not create clients.
    from tools.reparse_and_store import ENTITY_CONFIGS

    page = next(iter(payload["query"]["pages"].values()))
    categories = {c.get("title", "").split(":", 1)[-1] for c in page.get("categories", [])} | set(parser.parse_categories(source.text))
    names = {str(t.name).strip() for t in mw.parse(source.text).filter_templates()}
    if names & {"角色", "角色资料", "角色/信息"} and not source.title.endswith("语音"):
        voices = resolver(source.title + "语音")
        voice_payload = voices[0]["payload"] if len(voices) == 1 and not SourcePage.from_payload(voices[0]["payload"]).missing else None
        return "parsed/characters", parser.parse_character_page(payload, voice_payload=voice_payload).to_dict()
    if "任务" in names and categories & {"传说任务", "部族纪闻"}:
        return "parsed/character-quests", parser.parse_character_quest_page(payload).to_dict()
    if "任务" in names and "魔神任务" in categories:
        return "parsed/archon-quests", parser.parse_archon_quest_page(payload).to_dict()
    if "任务" in names or "剧情" in names:
        return "parsed/event-quests", parser.parse_event_quest_page(payload).to_dict()
    for config in ENTITY_CONFIGS.values():
        if config.parse_method and config.category in categories:
            return config.output_namespaces[0], getattr(parser, config.parse_method)(payload).to_dict()
    if "书籍" in names:
        return "parsed/books", parser.parse_book_page(payload).to_dict()
    if source.title == "北陆图书馆":
        return "parsed/north-library", parser.parse_north_library_page(payload).to_dict()
    if source.title.startswith("提瓦特编年史"):
        return "parsed/chronicles", parser.parse_chronicle_page(payload).to_dict()
    return "parsed/pages", parser.parse_page(payload).to_dict()


def validate_unit(unit, sources):
    source = sources[unit["source"]["raw_file"]]
    if unit["source"]["wikitext_sha256"] != source.wikitext_hash or replay_unit(source.text, unit) != unit["text"]:
        raise ValueError(f"unit cannot replay original source: {unit['unit_id']}")
    if unit["branch_path"] is None:
        if unit["branch_status"] != "unresolved":
            raise ValueError("unknown branch cannot be marked resolved")
        return
    for index, step in enumerate(unit["branch_path"]):
        label_source = step.get("label_source")
        if label_source:
            provider = sources[label_source["raw_file"]]
            if display_text(provider.text[label_source["start"]:label_source["end"]]) != step["label"]:
                raise ValueError("branch label cannot replay original source")
        content_source = step.get("content_source")
        if content_source and not (unit["type"] == "option" and index == len(unit["branch_path"]) - 1):
            if unit["source"]["raw_file"] != content_source["raw_file"] or not content_source["start"] <= unit["source"]["start"] <= unit["source"]["end"] <= content_source["end"]:
                raise ValueError("unit is outside its explicit branch response")


def run_recovery(*, input_root: Path, output_root: Path, offline: bool, manifest_path: Path | None = None):
    if not offline:
        raise ValueError("--offline is required; online recovery is not supported")
    input_root, output_root = Path(input_root).resolve(), Path(output_root).resolve()
    validate_paths(input_root, output_root)
    before = snapshot_manifest(input_root)
    if manifest_path:
        expected = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if before["files"] != expected["files"] or before["fingerprint_sha256"] != expected["fingerprint_sha256"]:
            raise ValueError("frozen snapshot does not match the supplied hash baseline")
    with offline_guard():
        return _run(input_root, output_root, before)


def _run(input_root, output_root, before):
    sources, payloads, by_title = {}, {}, collections.defaultdict(list)
    failures = []
    for path in sorted((input_root / "pages").glob("*.json")):
        raw_file = path.relative_to(input_root).as_posix()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = SourcePage.from_payload(payload, raw_file)
        except (ValueError, KeyError, TypeError) as exc:
            failures.append({"raw_file": raw_file, "status": "unsupported", "rule": "invalid_page_payload", "message": str(exc)})
            continue
        sources[raw_file], payloads[raw_file] = source, payload
        by_title[source.title].append({"raw_file": raw_file, "payload": payload})
    resolver = lambda title: by_title.get(title, [])
    output_root.mkdir(parents=True, exist_ok=True)
    store = JsonFileStore(output_root)
    parser = WikiTextParser()
    units, scenes = {}, {}
    issues, dependencies, page_results, records = list(failures), [], [], []
    regions_by_file = collections.defaultdict(list)
    for number, (raw_file, source) in enumerate(sources.items(), 1):
        result = parser.recover_page(payloads[raw_file], raw_file=raw_file, resolve_page=resolver)
        for unit in result["units"]:
            if unit["unit_id"] in units:
                existing = units[unit["unit_id"]]
                for consumer in unit.get("consumed_by", []):
                    if consumer not in existing.setdefault("consumed_by", []):
                        existing["consumed_by"].append(consumer)
            else:
                units[unit["unit_id"]] = unit
        for scene in result["scenes"]:
            scenes.setdefault(scene["scene_id"], scene)
        issues.extend(result["issues"])
        dependencies.extend(result["dependencies"])
        for region in result["regions"]:
            regions_by_file[region["source"]["raw_file"]].append(region)
        page_result = {"source": source.source(), "status": "needs_source" if source.missing else "partial" if result["issues"] else "processed",
                       "unit_ids": [u["unit_id"] for u in result["units"]], "parsed_file": None,
                       "issue_count": len(result["issues"])}
        if not source.missing and source.text:
            try:
                namespace, record = _business_record(parser, payloads[raw_file], source, resolver)
                record.update(source_title=source.title, page_id=source.page_id, source=source.source(), text_unit_ids=page_result["unit_ids"])
                if len(by_title[source.title]) > 1:
                    page_result["status"] = "unresolved"
                    issues.append({"rule": "ambiguous_storage_title", "status": "unsupported", "source": source.source()})
                else:
                    written = store.write(namespace, source.title, record)
                    page_result["parsed_file"] = written.relative_to(output_root).as_posix()
                    if namespace == "parsed/character-quests":
                        records.append(record)
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                page_result["status"] = "unresolved"
                issues.append({"rule": "business_parse_error", "status": "unsupported", "source": source.source(), "message": str(exc)})
        page_results.append(page_result)
        if number % 250 == 0:
            print(f"Recovered {number}/{len(sources)} cached pages", file=sys.stderr, flush=True)
    if records:
        from tools.batch_character_quests import build_character_quest_index, order_character_records
        ordered = order_character_records([], {r["source_title"]: r for r in records})
        write_json(output_root / "character_quests.json", {"quest_count": len(ordered), "quests": ordered, "index": build_character_quest_index([], ordered)})
    ordered_units = sorted(units.values(), key=lambda u: (u["source"]["raw_file"], u["source"]["start"], u["source"]["end"], u["type"]))
    for unit in ordered_units:
        if unit.get("consumed_by"):
            unit["consumed_by"].sort(key=lambda c: json.dumps(c, ensure_ascii=False, sort_keys=True))
        validate_unit(unit, sources)
    write_jsonl(output_root / "text_units.jsonl", ordered_units)
    write_jsonl(output_root / "scenes.jsonl", sorted(scenes.values(), key=lambda s: (s["source"]["raw_file"], s["source"]["start"], s["scene_id"])))
    unique_issues = {stable_id(issue): issue for issue in issues}
    write_jsonl(output_root / "issues.jsonl", sorted(unique_issues.values(), key=lambda i: json.dumps(i, ensure_ascii=False, sort_keys=True)))
    unique_dependencies = {stable_id(d): d for d in dependencies}
    write_jsonl(output_root / "dependencies.jsonl", sorted(unique_dependencies.values(), key=lambda d: json.dumps(d, ensure_ascii=False, sort_keys=True)))
    unit_by_file = collections.defaultdict(list)
    for unit in ordered_units:
        unit_by_file[unit["source"]["raw_file"]].append(unit)
    dispositions, characters = collections.Counter(), collections.Counter()
    unresolved_samples, unresolved_pages = [], set()
    with (output_root / "candidates.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for source in sources.values():
            candidates = audit_page(source, regions_by_file[source.raw_file], unit_by_file[source.raw_file])
            for candidate in candidates:
                dispositions[candidate["disposition"]] += 1
                characters.update(candidate["chinese_character_counts"])
                if candidate["disposition"] in {"unsupported", "needs_source"}:
                    unresolved_pages.add(source.title)
                    if len(unresolved_samples) < 8:
                        unresolved_samples.append({"page_title": source.title, "text": candidate["text"][:160], "disposition": candidate["disposition"]})
                handle.write(json.dumps(candidate, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    for page_result in page_results:
        page_result["provided_unit_ids"] = [u["unit_id"] for u in unit_by_file[page_result["source"]["raw_file"]]]
        if page_result["source"]["page_title"] in unresolved_pages and page_result["status"] == "processed":
            page_result["status"] = "partial"
    write_jsonl(output_root / "pages.jsonl", page_results + failures)
    after = snapshot_manifest(input_root)
    if before != after:
        raise ValueError("input snapshot changed during recovery; output is not validated")
    write_json(output_root / "input_manifest.json", before)
    issue_rules = collections.Counter(i["rule"] for i in unique_issues.values())
    candidate_denominator = dispositions["exported"] + dispositions["unsupported"] + dispositions["needs_source"]
    character_denominator = characters["exported"] + characters["unsupported"] + characters["needs_source"]
    problem_categories = {}
    for rule, count in issue_rules.items():
        matching = [i for i in unique_issues.values() if i["rule"] == rule]
        affected = {i.get("source", {}).get("page_title", i.get("raw_file", "")) for i in matching}
        problem_categories[rule] = {"count": count, "affected_page_count": len(affected),
                                    "examples": [{"source": i.get("source"), "raw": i.get("raw", i.get("message", ""))[:160]} for i in matching[:3]]}
    report = {"schema_version": 1, "status": "validated_with_unresolved_sources" if unresolved_pages or issues else "validated",
              "offline": True, "snapshot_fingerprint_sha256": before["fingerprint_sha256"],
              "input_file_count": before["file_count"], "input_hashes_unchanged": True,
              "page_count": len(sources) + len(failures), "unit_count": len(ordered_units), "scene_count": len(scenes),
              "unit_types": dict(collections.Counter(u["type"] for u in ordered_units)),
              "source_replay": {"checked": len(ordered_units), "failures": 0},
              "branch_checks": {"checked": sum(bool(u["branch_path"]) for u in ordered_units), "unresolved_units": sum(u["branch_path"] is None for u in ordered_units), "failures": 0},
              "candidate_dispositions": dict(dispositions), "chinese_character_dispositions": dict(characters),
              "candidate_recovery_fraction": dispositions["exported"] / candidate_denominator if candidate_denominator else None,
              "chinese_character_recovery_fraction": characters["exported"] / character_denominator if character_denominator else None,
              "coverage_definition": "exported / (exported + unsupported + needs_source); metadata and explicit non-story excluded; unknown candidates retained; media needs_source is counted separately in dispositions",
              "unresolved_page_count": len(unresolved_pages), "issue_rules": dict(issue_rules), "unresolved_samples": unresolved_samples,
              "dependency_statuses": dict(collections.Counter(d["status"] for d in unique_dependencies.values()))}
    report["problem_categories"] = problem_categories
    report["source_kinds"] = dict(collections.Counter(u["source_kind"] for u in ordered_units))
    report["page_statuses"] = dict(collections.Counter(p["status"] for p in page_results + failures))
    write_json(output_root / "summary.json", report)
    (output_root / "summary.md").write_text(
        "# 冻结快照恢复摘要\n\n" + f"页面 {report['page_count']}；文本单元 {report['unit_count']}；场景 {report['scene_count']}。\n\n"
        + f"原始文件 {before['file_count']} 份，运行前后哈希一致。来源重放 {len(ordered_units)} 条通过。\n\n"
        + "这是已缓存来源的恢复实验。未知节点、依赖和媒体缺失保留在机器清单中，不代表整款游戏完整覆盖。\n\n"
        + "详细指标见 summary.json；候选节点见 candidates.jsonl；未解决规则见 issues.jsonl。\n", encoding="utf-8")
    manifest = snapshot_manifest(output_root)
    manifest["excludes"] = ["output_manifest.json"]
    write_json(output_root / "output_manifest.json", manifest)
    return report


def main(argv=None):
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--input-root", type=Path, required=True)
    command.add_argument("--output-root", type=Path, required=True)
    command.add_argument("--offline", action="store_true")
    command.add_argument("--manifest", type=Path, help="Optional authoritative input hash baseline")
    args = command.parse_args(argv)
    try:
        report = run_recovery(input_root=args.input_root, output_root=args.output_root, offline=args.offline, manifest_path=args.manifest)
    except (ValueError, RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"output": str(args.output_root), "page_count": report["page_count"], "unit_count": report["unit_count"], "status": report["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
