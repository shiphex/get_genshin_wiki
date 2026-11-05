"""Offline V2.3.1 rebuild. Never replace inputs or accept unexplained deltas.

The baseline parser runs in a separate process from a local git archive.
The output contains input/, snapshot/, baseline-business/, and audit evidence.
Only snapshot/ belongs in the delivered data ZIP.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SOURCE_SHA256 = "13b71711bde300d5f1833e64d29381a1c32cb7e70da106d76bf1126f9c862ed1"
RECOVERY_REL = "recovery/full-offline-v2.3.1"
TASKS = ("archon-quests", "character-quests", "event-quests")
RAW_DIRS = ("pages", "categories", "category_members")


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def safe_extract(archive, root):
    """Validate the entire ZIP before creating any output (including on Windows)."""
    root = Path(root).resolve()
    if root.exists():
        raise FileExistsError(root)
    with zipfile.ZipFile(archive) as z:
        seen = set()
        for item in z.infolist():
            name = item.filename
            parts = PurePosixPath(name).parts
            key = name.rstrip("/").casefold()
            if (not parts or name.startswith("/") or "\\" in name or ":" in name
                    or any(p in {"..", "."} or p.endswith((" ", ".")) for p in parts)
                    or key in seen or stat.S_ISLNK(item.external_attr >> 16)
                    or not (root / name).resolve().is_relative_to(root)):
                raise ValueError(f"unsafe ZIP member: {name}")
            seen.add(key)
        root.mkdir(parents=True)
        z.extractall(root)


def _unit_key(unit):
    source = unit["source"]
    return (source.get("raw_file"), source["end"], unit.get("scene_id"),
            json.dumps(unit.get("branch_path"), sort_keys=True),
            unit["type"] == "annotation")


def audit_units(text, old, new):
    """Explain semantic unit deltas using source positions, never text matching."""
    from get_genshin_wiki.recovery.display import display_text, omit_source_spans, replay_unit

    before = defaultdict(deque)
    for unit in old["units"]:
        before[_unit_key(unit)].append(unit)
    changes = []
    for unit in new["units"]:
        queue = before[_unit_key(unit)]
        previous = queue.popleft() if queue else None
        if previous == unit:
            continue
        if replay_unit(text, unit) != unit["text"]:
            raise ValueError("unexplained non-replayable text")
        source = unit["source"]
        raw = text[source["start"]:source["end"]]
        speaker_source = unit.get("speaker_source") or unit.get("narration_label_source")
        if speaker_source and unit["speaker"] is not None:
            speaker_raw = text[speaker_source["start"]:speaker_source["end"]]
            if display_text(omit_source_spans(speaker_raw, speaker_source["start"],
                                            unit.get("speaker_excluded_spans", []))) != unit["speaker"]:
                raise ValueError("unexplained speaker identity without source")
        delimiter = text[speaker_source["end"]:source["start"]].strip() if speaker_source else ""
        ruby_issue = next((i for i in old.get("issues", [])
                           if i["rule"] == "unknown_template" and "<rp" in i.get("raw", "").lower()
                           and i["source"]["start"] <= source["start"]
                           and source["end"] <= i["source"]["end"]), None)
        if previous is None and ruby_issue:
            reason = "ruby_fallback_metadata"
            _validate_added_ruby(text, unit)
        elif previous is not None and delimiter == ":" and unit["type"] in {"dialogue", "narration", "option"}:
            # The old unit must cover this same original line, including its label.
            if not (previous["source"]["start"] <= speaker_source["start"]
                    and previous["source"]["end"] == source["end"]):
                raise ValueError("unexplained speaker source mismatch")
            reason = "ascii_speaker_separator"
            _validate_ascii_change(text, previous, unit, speaker_source)
        else:
            raise ValueError(f"unexplained recovery delta: {source}: {raw[:100]}")
        changes.append({"reason": reason, "before": previous, "after": unit,
                        "raw": text[(previous or unit)["source"]["start"]:source["end"]]})
    remaining = [u for queue in before.values() for u in queue]
    if remaining:
        raise ValueError(f"unexplained removed recovery units: {remaining[0]['source']}")
    audit_diagnostics(old, new, changes)
    return changes


def _projection_fields(text, unit):
    from get_genshin_wiki.recovery.display import display_projection
    from get_genshin_wiki.recovery.source import stable_id
    source = unit["source"]
    visible, _, unsupported = display_projection(text[source["start"]:source["end"]], source["start"])
    spans = [{**source, "start": left, "end": right} for left, right in visible
             if not any(s["start"] <= left and right <= s["end"] for s in unit.get("excluded_spans", []))]
    identity = source["page_id"], source["page_title"], source["raw_file"]
    unit_id = stable_id("unit", identity, source["wikitext_sha256"], source["start"], source["end"], unit["type"])
    if unit.get("excluded_spans") or unit.get("speaker_excluded_spans"):
        unit_id = stable_id(unit_id, "separated_inline_blackouts",
                            unit.get("excluded_spans", []), unit.get("speaker_excluded_spans", []))
    return spans, "partial" if unsupported else "resolved", unit_id


def _validate_ascii_change(text, old, new, label_source):
    from get_genshin_wiki.recovery.display import display_text
    from get_genshin_wiki.recovery.extract import ascii_speaker_label
    expected = copy.deepcopy(old)
    label = display_text(text[label_source["start"]:label_source["end"]])
    if not ascii_speaker_label(label, new["text"]) or label_source["start"] != old["source"]["start"]:
        raise ValueError("unexplained ASCII speaker label")
    start = label_source["end"] + 1
    while start < old["source"]["end"] and text[start].isspace():
        start += 1
    expected["source"] = {**old["source"], "start": start}
    expected["text"] = display_text(text[start:old["source"]["end"]])
    expected["type"] = "narration" if label == "旁白" else "dialogue"
    expected["speaker"] = None if label == "旁白" else label
    expected["speaker_status"] = "not_applicable" if label == "旁白" else "resolved"
    expected["source_kind"] = "wiki_editorial" if old["source_kind"] == "wiki_editorial" else "game_excerpt"
    for key in ("narration_kind", "document_id", "document_title", "classification_reason"):
        expected.pop(key, None)
    if label == "旁白":
        expected["narration_kind"] = "narrative"
        expected["narration_label_source"] = label_source
        expected.pop("speaker_source", None)
    else:
        expected["speaker_source"] = label_source
    spans, status, unit_id = _projection_fields(text, expected)
    expected.update(text_spans=spans, display_status=status, unit_id=unit_id)
    if expected != new:
        fields = sorted(k for k in expected.keys() | new.keys() if expected.get(k) != new.get(k))
        raise ValueError("unexplained ASCII field changes: " + ", ".join(fields))


def _validate_added_ruby(text, unit):
    spans, status, unit_id = _projection_fields(text, unit)
    allowed = {"unit_id", "type", "text", "speaker", "scene_id", "speaker_status", "branch_path", "branch_status",
               "source", "source_kind", "text_spans", "display_status", "speaker_source", "consumed_by"}
    if (set(unit) - allowed or unit["text_spans"] != spans or unit["display_status"] != status
            or unit["unit_id"] != unit_id
            or unit["branch_status"] != ("unresolved" if unit["branch_path"] is None else "resolved")
            or unit["speaker_status"] != ("resolved" if unit["speaker"] else "not_applicable")
            or unit["source_kind"] != ("unknown" if unit["type"] == "description" else "game_excerpt")
            or (unit["speaker"] and unit["type"] != "dialogue")):
        raise ValueError("unexplained ruby unit fields")


def audit_diagnostics(old, new, changes):
    from get_genshin_wiki.recovery.extract import ascii_speaker_label
    from get_genshin_wiki.recovery.display import display_text
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True)
    before, after = Counter(map(encode, old.get("issues", []))), Counter(map(encode, new.get("issues", [])))
    result = []
    for direction, values in (("removed", before - after), ("added", after - before)):
        for encoded, count in values.items():
            issue = json.loads(encoded)
            source = issue.get("source", {})
            affected = [c for c in changes if c.get("before") and c["before"]["source"] == source]
            allowed = direction == "removed" and (
                issue["rule"] in {"unclassified_narration", "unattributed_break_fragment"} and affected
                or issue["rule"] == "unknown_template" and "<rp" in issue.get("raw", "").lower()
                and any(c["reason"] == "ruby_fallback_metadata"
                        and source.get("start", -1) <= c["after"]["source"]["start"]
                        and c["after"]["source"]["end"] <= source.get("end", -1) for c in changes))
            if direction == "added" and issue["rule"] == "ambiguous_ascii_speaker":
                label, colon, body = issue.get("raw", "").partition(":")
                allowed = bool(colon and not ascii_speaker_label(display_text(label), display_text(body)))
            if not allowed:
                raise ValueError("unexplained diagnostic delta: " + issue["rule"])
            result.append(dict(direction=direction, count=count, issue=issue))
    return result


def business_rows(record, family):
    if family == "event-quests":
        for s, scene in enumerate(record["剧情对话"]):
            for i, row in enumerate(scene["对话"]):
                yield f"/剧情对话/{s}/对话/{i}", row
    else:
        for i, row in enumerate(record["对话"]):
            yield f"/对话/{i}", row


def _pointers(record, family, recovery):
    """Carry source identity through the real adapter, including grouped choices."""
    from get_genshin_wiki.recovery.legacy import archon_dialogues, character_dialogues, event_steps
    tagged = copy.deepcopy(recovery)
    for index, unit in enumerate(tagged["units"]):
        unit["text"] = str(index)
    def project(value):
        if family == "event-quests":
            return {"剧情对话": [s.to_dict() for s in event_steps(value)]}
        adapter = character_dialogues if family == "character-quests" else archon_dialogues
        return {"对话": [r.to_dict() for r in adapter(value)]}
    actual = dict(business_rows(record, family))
    projected = dict(business_rows(project(recovery), family))
    if actual != projected:
        raise ValueError("business row type/flow/content does not match source projection")
    result = {}
    for pointer, row in business_rows(project(tagged), family):
        if "内容" in row:
            result[_unit_key(recovery["units"][int(row["内容"])])] = pointer
        else:
            for index, token in enumerate(row.get("选项", [])):
                result[_unit_key(recovery["units"][int(token)])] = f"{pointer}/选项/{index}"
    return result


def build_business(input_root, destination, audit_root):
    """Run under either code root; use only pure parse APIs and cached context."""
    from get_genshin_wiki.parser import WikiTextParser
    from get_genshin_wiki.storage import JsonFileStore
    from tools.refresh_parsed_offline import METHODS, _has_text
    from tools.recover_snapshot import offline_guard
    from get_genshin_wiki.cli import _maybe_load_event_payload

    parser, store = WikiTextParser(), JsonFileStore(input_root)
    arc = read(input_root / "archon_quests.json") if (input_root / "archon_quests.json").exists() else None
    char = read(input_root / "character_quests.json") if (input_root / "character_quests.json").exists() else None
    arc_context = parser.build_archon_series_context(arc["index"]) if arc else {}
    char_index = parser.parse_character_quest_list_page(store.read("pages", "传说任务")) if store.exists("pages", "传说任务") else []
    char_context = parser.build_character_quest_series_context(char_index)
    records, counts = {}, {}
    with offline_guard():
        for family, method in METHODS.items():
            paths = sorted((input_root / "parsed" / family).glob("*.json"))
            for path in paths:
                raw_path = input_root / "pages" / path.name
                payload, old = read(raw_path), read(path)
                title, _, text = parser.extract_page_metadata(payload)
                if store.build_filename(title) != path.name:
                    raise ValueError(f"source identity mismatch: {path}")
                kwargs = {}
                if family == "characters" and store.exists("pages", title + "语音"):
                    voice = store.read("pages", title + "语音")
                    if _has_text(voice):
                        kwargs["voice_payload"] = voice
                elif family == "archon-quests":
                    kwargs["series_context"] = arc_context
                elif family == "character-quests":
                    kwargs["series_context"] = char_context
                elif family == "event-quests":
                    kwargs["event_payload"] = _maybe_load_event_payload(store, parser, "pages", payload)
                record = getattr(parser, method)(payload, **kwargs)
                if family == "north-library":
                    record.library_category = old.get("library_category", "")
                    record.category_candidates = old.get("category_candidates", [])
                value = record.to_storage_dict() if family == "characters" else record.to_dict()
                target = destination / path.relative_to(input_root)
                if value == old:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
                else:
                    write(target, value)
                records[(family, title)] = value
                if family in TASKS:
                    write(audit_root / family / path.name, parser.recover_page(payload, raw_file="pages/" + path.name))
            counts[family] = len(paths)
            print(f"Business {family}: {len(paths)}", flush=True)
        expanded_char_index = build_expanded_character_index(
            char_index, [records[("character-quests", r["source_title"])] for r in char["quests"]]
        ) if char else []
        for name, aggregate, family in (
                ("archon_quests.json", arc, "archon-quests"),
                ("character_quests.json", char, "character-quests")):
            if aggregate is None:
                continue
            result = copy.deepcopy(aggregate)
            titles = [r.get("source_title") or r["任务标题"]["中文"] for r in aggregate["quests"]]
            if len(set(titles)) != len(titles) or set(titles) != {t for f, t in records if f == family}:
                raise ValueError("aggregate inventory mismatch")
            result["quests"] = [records[(family, title)] for title in titles]
            if family == "character-quests":
                result["index"] = expanded_char_index
            write(destination / name, result)
        for namespace, title in (("archon-quest-index", "魔神任务"), ("character-quest-index", "传说任务")):
            for path in (input_root / "parsed" / namespace).glob("*.json"):
                if namespace == "archon-quest-index":
                    # Some series names came from rendered headings unavailable
                    # in raw pages. The frozen expanded index is cached context,
                    # not permission to ask the live Wiki for replacement names.
                    value = read(path)
                    context = {e["title"]: e for e in arc["index"]}
                    if len({e["title"] for e in value}) != len(value) or any(
                            e != context.get(e["title"]) or not store.exists("pages", e["title"])
                            for e in value):
                        raise ValueError("frozen expanded archon index is inconsistent")
                else:
                    value = expanded_char_index
                write(destination / path.relative_to(input_root), value)
    write(audit_root / "inventory.json", counts)


def build_expanded_character_index(list_entries, records):
    from tools.batch_character_quests import build_character_quest_index
    return build_character_quest_index(list_entries, copy.deepcopy(records))


def validate_aggregates(frozen, snapshot):
    checked = 0
    for name, family in (("archon_quests.json", "archon-quests"),
                         ("character_quests.json", "character-quests")):
        if not (frozen / name).is_file():
            continue
        original, generated = read(frozen / name), read(snapshot / name)
        metadata = lambda value: {k: v for k, v in value.items() if k not in {"quests", "index"}}
        if metadata(original) != metadata(generated):
            raise ValueError("aggregate metadata changed: " + name)
        records = {}
        for path in (snapshot / "parsed" / family).glob("*.json"):
            row = read(path)
            title = row.get("source_title") or row["任务标题"]["中文"]
            if title in records:
                raise ValueError("aggregate duplicate identity: " + title)
            records[title] = row
        titles = [r.get("source_title") or r["任务标题"]["中文"] for r in original["quests"]]
        if len(titles) != len(set(titles)) or set(titles) != records.keys():
            raise ValueError("aggregate inventory differs: " + name)
        if generated["quests"] != [records[title] for title in titles]:
            raise ValueError("aggregate differs from single-page records: " + name)
        if family == "archon-quests" and generated["index"] != original["index"]:
            raise ValueError("aggregate frozen archon context changed")
        if family == "character-quests":
            paths = list((snapshot / "parsed/character-quest-index").glob("*.json"))
            if len(paths) != 1 or generated["index"] != read(paths[0]):
                raise ValueError("aggregate character index differs")
        checked += len(titles)
    return checked


def audit_business(input_root, baseline, snapshot, old_audit, new_audit):
    from get_genshin_wiki.parser import WikiTextParser
    parser = WikiTextParser()
    candidates, changes, pointer_changes, diagnostic_changes = [], [], [], []
    for path in sorted((input_root / "parsed").rglob("*.json")):
        relative = path.relative_to(input_root)
        old, reproduced, new = read(path), read(baseline / relative), read(snapshot / relative)
        if old != reproduced:
            raise ValueError(f"frozen baseline not reproduced: {relative}")
        family = relative.parts[1]
        if family not in TASKS:
            if old != new:
                raw = parser.extract_page_metadata(read(input_root / "pages" / path.name))[2]
                # The only non-dialogue display change is removal of rp fallback text.
                fields = [k for k in old.keys() | new.keys() if old.get(k) != new.get(k)] if isinstance(old, dict) else []
                if not fields or "<rp" not in raw.lower() or any(
                        not isinstance(old.get(k), str) or old[k].replace("(", "").replace(")", "") != new.get(k)
                        for k in fields):
                    raise ValueError(f"unexplained business delta: {relative}")
                changes.append({"file": relative.as_posix(), "reason": "ruby_fallback_metadata",
                                "fields": fields, "before": old, "after": new})
            continue
        before, after = read(old_audit / family / path.name), read(new_audit / family / path.name)
        text = parser.extract_page_metadata(read(input_root / "pages" / path.name))[2]
        delta = audit_units(text, before, after)
        diagnostic_changes.extend(dict(file=relative.as_posix(), **d) for d in audit_diagnostics(before, after, delta))
        key = "剧情对话" if family == "event-quests" else "对话"
        metadata = [k for k in old.keys() | new.keys() if k != key and old.get(k) != new.get(k)]
        if set(metadata) - {"相关角色"} or (old != new and not delta):
            raise ValueError(f"unexplained task metadata: {relative}: {metadata}")
        if metadata:
            if family != "archon-quests":
                raise ValueError("unexplained related-character metadata")
            from get_genshin_wiki.recovery.legacy import archon_dialogues
            payload = read(input_root / "pages" / path.name)
            parsed = parser.parse_page(payload)
            _, template = parser._select_archon_quest_template(parsed.templates)
            explicit = parser._resolve_raw_value(parsed.templates, ("出场人物",),
                                                 preferred_params=template, wikitext=parsed.wikitext)
            expected_roles = parser._extract_archon_related_npcs(explicit, parsed.sections,
                                                                dialogues=archon_dialogues(after))
            if new["相关角色"] != expected_roles:
                raise ValueError("unexplained derived related-character metadata")
        old_ptr, new_ptr = _pointers(old, family, before), _pointers(new, family, after)
        old_rows, new_rows = dict(business_rows(old, family)), dict(business_rows(new, family))
        changed_by_old = {}
        for change in delta:
            previous, unit = change["before"], change["after"]
            old_pointer = old_ptr.get(_unit_key(previous)) if previous else None
            new_pointer = new_ptr.get(_unit_key(unit))
            row = dict(file=relative.as_posix(), reason=change["reason"], old_pointer=old_pointer,
                       new_pointer=new_pointer, source=unit["source"], branch_path=unit["branch_path"],
                       before=old_rows.get(old_pointer), after=new_rows.get(new_pointer), raw=change["raw"])
            pointer_changes.append(row)
            if old_pointer:
                changed_by_old[old_pointer] = row
        for pointer, row in old_rows.items():
            if row.get("类型") in {"narration", "旁白"} and re.match(r"^[^：:\n]{1,40}:\S", row.get("内容", "")):
                change = changed_by_old.get(pointer)
                candidates.append(dict(file=relative.as_posix(), old_pointer=pointer, before=row,
                                       disposition="confirmed_fixed" if change else "unresolved",
                                       reason=change["reason"] if change else "template_syntax_requires_separate_investigation",
                                       change=change))
        if old != new:
            changes.append(dict(file=relative.as_posix(), recovery_changes=delta,
                                metadata_changes={k: {"before": old.get(k), "after": new.get(k)} for k in metadata}))
    return dict(changed_files=len(changes), business_changes=changes, pointer_changes=pointer_changes,
                diagnostic_changes=diagnostic_changes,
                candidate_count=len(candidates), candidate_dispositions=dict(Counter(c["disposition"] for c in candidates)),
                candidates=candidates)


def rebuild_snapshot(source_zip, output_root, *, expected_sha256=SOURCE_SHA256,
                     baseline_commit="release/V2.3.0", business_only=False, finish_staged=False):
    output_root = Path(output_root).resolve()
    if output_root.exists() and not finish_staged:
        raise FileExistsError(output_root)
    source_zip = Path(source_zip).resolve()
    if finish_staged:
        verify_checkpoint(output_root, source_zip, expected_sha256, baseline_commit)
    if digest(source_zip) != expected_sha256:
        raise ValueError("source ZIP SHA-256 mismatch")
    frozen, snapshot = output_root / "input", output_root / "snapshot"
    raw_input = output_root / "raw-input"
    baseline_code = output_root / "baseline-code"
    if not finish_staged:
        output_root.mkdir(parents=True)
        safe_extract(source_zip, frozen)
        shutil.copytree(frozen, snapshot)
        raw_input.mkdir()
        for name in RAW_DIRS:
            shutil.copytree(frozen / name, raw_input / name)
        # Archive the exact tracked baseline; never switch the user's checkout.
        code = subprocess.run(["git", "archive", "--format=zip", baseline_commit, "get_genshin_wiki", "tools"],
                              cwd=PROJECT_ROOT, check=True, capture_output=True).stdout
        safe_extract(io.BytesIO(code), baseline_code)
    elif (snapshot / RECOVERY_REL).exists():
        partial = (snapshot / RECOVERY_REL).resolve()
        saved = (output_root / "failed-recovery-before-diagnostic-fix").resolve()
        if not partial.is_relative_to(output_root) or not saved.is_relative_to(output_root) or saved.exists():
            raise ValueError("unsafe checkpoint recovery move")
        partial.rename(saved)
    for code_root, destination, audit in (
            (baseline_code, output_root / "baseline-business", output_root / "baseline-audit"),
            (PROJECT_ROOT, snapshot, output_root / "current-audit")):
        if finish_staged and code_root == baseline_code:
            continue
        subprocess.run([sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()), "_worker",
                        str(code_root), str(frozen), str(destination), str(audit)], check=True, cwd=PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT))
    from tools.recover_snapshot import offline_guard, run_recovery, snapshot_manifest
    with offline_guard():
        report = audit_business(frozen, output_root / "baseline-business", snapshot,
                                output_root / "baseline-audit", output_root / "current-audit")
        report.update(offline=True, version="2.3.1", source_zip=source_zip.name,
                      source_zip_sha256=expected_sha256, baseline_commit=baseline_commit,
                      code_source_sha256=snapshot_manifest(PROJECT_ROOT / "get_genshin_wiki")["fingerprint_sha256"],
                      input_manifest=snapshot_manifest(raw_input), recovery_path=RECOVERY_REL,
                      index_context="Frozen expanded archon index cross-checked with aggregate context and cached pages; character index reparsed.",
                      validated_baseline_checkpoint_reused=finish_staged,
                      status="business_validated" if business_only else "validated",
                      limitation="Repository candidates differ from downstream 565 flags; no full-corpus error-rate claim.")
        if not business_only:
            if not finish_staged:
                subprocess.run([sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()), "_recovery",
                                str(baseline_code), str(raw_input), str(output_root / "baseline-recovery")],
                               check=True, cwd=PROJECT_ROOT)
            report["recovery"] = run_recovery(input_root=raw_input, output_root=snapshot / RECOVERY_REL, offline=True)
            report["recovery_changes"] = audit_recovery(raw_input, output_root / "baseline-recovery",
                                                        snapshot / RECOVERY_REL)
        report["acceptance"] = verify_known_regressions(frozen, snapshot)
        report["aggregate_records_checked"] = validate_aggregates(frozen, snapshot)
        for name in RAW_DIRS:
            if snapshot_manifest(frozen / name) != snapshot_manifest(snapshot / name):
                raise ValueError("raw input changed")
        original_names = {p.relative_to(frozen / "parsed").as_posix() for p in (frozen / "parsed").rglob("*.json")}
        new_names = {p.relative_to(snapshot / "parsed").as_posix() for p in (snapshot / "parsed").rglob("*.json")}
        if original_names != new_names:
            raise ValueError("parsed inventory changed")
        report["parsed_file_count"] = len(new_names)
        write(snapshot / "reports/parser-v2.3.1/audit.json", report)
        write(output_root / "report.json", report)
    print(json.dumps({k: report[k] for k in ("status", "changed_files", "candidate_count", "candidate_dispositions", "parsed_file_count")}), flush=True)
    return report


def verify_checkpoint(root, source_zip, expected_sha256, baseline_commit):
    """Reuse only an intact old baseline; always regenerate every current output."""
    from tools.recover_snapshot import snapshot_manifest
    from tools.refresh_parsed_offline import _verify_manifest
    if not (root / "baseline-recovery/output_manifest.json").is_file():
        raise ValueError("validated baseline checkpoint required")
    if (root / "report.json").exists():
        raise ValueError("completed snapshots cannot be replaced")
    if digest(source_zip) != expected_sha256:
        raise ValueError("baseline source ZIP hash mismatch")
    for name in ("input", "raw-input", "snapshot", "baseline-code", "baseline-business", "baseline-audit"):
        tree = root / name
        if tree.is_symlink() or any(p.is_symlink() for p in tree.rglob("*")):
            raise ValueError("symlink in baseline checkpoint")
    with zipfile.ZipFile(source_zip) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            path = root / "input" / member.filename
            if not path.is_file() or hashlib.sha256(archive.read(member)).hexdigest() != digest(path):
                raise ValueError("baseline frozen input changed")
    expected_raw = []
    for name in RAW_DIRS:
        expected_raw.extend({**entry, "path": name + "/" + entry["path"]}
                            for entry in snapshot_manifest(root / "input" / name)["files"])
    if sorted(expected_raw, key=lambda row: row["path"]) != snapshot_manifest(root / "raw-input")["files"]:
        raise ValueError("baseline raw input differs")
    archived_code = subprocess.run(["git", "archive", "--format=zip", baseline_commit, "get_genshin_wiki", "tools"],
                                   cwd=PROJECT_ROOT, check=True, capture_output=True).stdout
    with zipfile.ZipFile(io.BytesIO(archived_code)) as archive:
        for member in archive.infolist():
            if not member.is_dir() and hashlib.sha256(archive.read(member)).hexdigest() != digest(root / "baseline-code" / member.filename):
                raise ValueError("baseline parser code changed")
    _verify_manifest(root / "baseline-recovery")
    if read(root / "baseline-recovery/input_manifest.json") != snapshot_manifest(root / "raw-input"):
        raise ValueError("baseline recovery input mismatch")
    summary = read(root / "baseline-recovery/summary.json")
    if summary["source_replay"]["failures"] or summary["branch_checks"]["failures"]:
        raise ValueError("baseline validation failures")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_recovery":
        code_root, input_root, output_root = map(Path, sys.argv[2:])
        sys.path.insert(0, str(code_root))
        from tools.recover_snapshot import run_recovery
        run_recovery(input_root=input_root, output_root=output_root, offline=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "_worker":
        code_root, input_root, destination, audit_root = map(Path, sys.argv[2:])
        sys.path.insert(0, str(code_root))
        build_business(input_root, destination, audit_root)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "package":
        parser = argparse.ArgumentParser(description="Package two identical validated rebuilds.")
        parser.add_argument("--first", type=Path, required=True)
        parser.add_argument("--second", type=Path, required=True)
        parser.add_argument("--destination", type=Path, required=True)
        args = parser.parse_args(sys.argv[2:])
        package_snapshot(args.first, args.second, args.destination)
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-sha256", default=SOURCE_SHA256)
    parser.add_argument("--baseline-commit", default="release/V2.3.0")
    parser.add_argument("--business-only", action="store_true", help="Audit staging only; no delivery/recovery verification")
    parser.add_argument("--finish-staged", action="store_true",
                        help="For failed staging only: hash-check old baseline, reparse all current outputs, retain failed recovery")
    args = parser.parse_args()
    rebuild_snapshot(args.source_zip, args.output_root, expected_sha256=args.expected_sha256,
                     baseline_commit=args.baseline_commit, business_only=args.business_only, finish_staged=args.finish_staged)


def package_snapshot(first, second, destination):
    from tools.recover_snapshot import snapshot_manifest
    first, second, destination = (Path(p).resolve() for p in (first, second, destination))
    if first == second or first.is_relative_to(second) or second.is_relative_to(first):
        raise ValueError("repeat runs must be distinct disjoint directories")
    manifest = snapshot_manifest(first / "snapshot")
    if manifest != snapshot_manifest(second / "snapshot"):
        raise ValueError("repeat snapshots are not byte-identical")
    report = read(first / "report.json")
    other = read(second / "report.json")
    for candidate in (report, other):
        if candidate["status"] != "validated" or candidate["recovery"]["source_replay"]["failures"]:
            raise ValueError("full validation required before packaging")
    for key in ("source_zip_sha256", "baseline_commit", "code_source_sha256", "input_manifest"):
        if report[key] != other[key]:
            raise ValueError("repeat provenance mismatch: " + key)
    aggregate_checks = [validate_aggregates(run / "input", run / "snapshot") for run in (first, second)]
    if snapshot_manifest(PROJECT_ROOT / "get_genshin_wiki")["fingerprint_sha256"] != report["code_source_sha256"]:
        raise ValueError("parser source changed after rebuilding")
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, check=True, capture_output=True).stdout
    if dirty.strip():
        raise ValueError("commit code and tests before packaging")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True).stdout.strip()
    release = dict(version="2.3.1", parser_code_commit=commit, source_zip_sha256=report["source_zip_sha256"],
                   code_source_sha256=report["code_source_sha256"], input_manifest=report["input_manifest"],
                   snapshot_manifest=manifest, repeat_identical=True, recovery_path=RECOVERY_REL,
                   acceptance=report["acceptance"], candidate_dispositions=report["candidate_dispositions"],
                   aggregate_records_checked=aggregate_checks)
    destination.mkdir(parents=True, exist_ok=False)
    write(destination / "release_manifest.json", release)
    archive_path = destination / "genshin_wiki_data_20260605_20261105_v2.3.1.zip"
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
        for entry in manifest["files"]:
            archive.write(first / "snapshot" / entry["path"], entry["path"])
        archive.write(destination / "release_manifest.json", "reports/parser-v2.3.1/release_manifest.json")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        for entry in manifest["files"]:
            h = hashlib.sha256()
            with archive.open(entry["path"]) as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    h.update(block)
            if h.hexdigest() != entry["sha256"]:
                raise ValueError("ZIP member hash mismatch: " + entry["path"])
    checksum = digest(archive_path)
    (destination / (archive_path.name + ".sha256")).write_text(checksum + "  " + archive_path.name + "\n", encoding="ascii")
    write(destination / "delivery.json", dict(zip=archive_path.name, sha256=checksum, parser_code_commit=commit,
                                              repeat_identical=True, zip_members_verified=len(manifest["files"]) + 1))
    shutil.copyfile(first / "report.json", destination / "audit.json")
    print(json.dumps(read(destination / "delivery.json")), flush=True)
    return release


def audit_recovery(raw_input, before_root, after_root):
    from get_genshin_wiki.recovery.source import SourcePage
    groups = []
    for root in (before_root, after_root):
        pages = defaultdict(lambda: {"units": [], "issues": []})
        for name, field in (("text_units", "units"), ("issues", "issues")):
            with (root / (name + ".jsonl")).open(encoding="utf-8") as handle:
                for line in handle:
                    value = json.loads(line)
                    raw_file = value.get("source", {}).get("raw_file") or value.get("raw_file") or "__global__"
                    pages[raw_file][field].append(value)
        groups.append(pages)
    changes, diagnostics = [], []
    for raw_file in sorted(groups[0].keys() | groups[1].keys()):
        old, new = groups[0][raw_file], groups[1][raw_file]
        if old == new:
            continue
        if not (raw_input / raw_file).is_file():
            raise ValueError("unexplained global recovery diagnostic delta")
        text = SourcePage.from_payload(read(raw_input / raw_file), raw_file).text
        delta = audit_units(text, old, new)
        changes.extend(delta)
        diagnostics.extend(dict(file=raw_file, **d) for d in audit_diagnostics(old, new, delta))
    return dict(unit_changes=changes, diagnostic_changes=diagnostics)


def verify_known_regressions(frozen, snapshot):
    expected = [
        ("character-quests", "b8c0d1a9aa", "阿佩普", "「龙王」自世界之外取得漆黑之力，带领我们反抗外来者定义的秩序。", "与阿佩普交谈"),
        ("character-quests", "b8c0d1a9aa", "阿佩普", "嗯，后来「阿赫玛尔」在「娜布·玛莉卡塔」的帮助下获得了这种力量。", "与阿佩普交谈"),
        ("archon-quests", "2832f60895", "派蒙", "芙卡洛斯摧毁了水神的神座，归还了力量，你变成了完全状态的元素龙王…", "◆与那维莱特对话"),
        ("archon-quests", "2832f60895", "丝柯克", "你的身上，现在带着「第三降临者的遗骨」吧？", "◆与那维莱特对话"),
        ("archon-quests", "2832f60895", "丝柯克", "嗯…用你们常用的说法，好像应该叫…「神之心」？", "◆与那维莱特对话"),
        ("archon-quests", "2832f60895", "那维莱特", "你所说的「第三降临者」，指的是谁？又是在什么时候死去的？", "◆与那维莱特对话"),
        ("archon-quests", "2832f60895", "丝柯克", "师父之前没有和我提过，可能对我来说是无足轻重的信息。", "◆与那维莱特对话"),
    ]
    found = []
    for family, suffix, speaker, text, flow in expected:
        path = next((snapshot / "parsed" / family).glob("*" + suffix + ".json"))
        matches = [(i, r) for i, r in enumerate(read(path)["对话"]) if r["内容"] == text]
        if len(matches) != 1 or matches[0][1] != dict(说话者=speaker, 内容=text, 类型="character", 所属任务流程=flow):
            raise ValueError("known regression failed: " + text)
        found.append(dict(file=path.relative_to(snapshot).as_posix(), pointer=f"/对话/{matches[0][0]}", speaker=speaker, text=text))
    suffix = "*e4ed1de066.json"
    blocks = []
    for root in (frozen, snapshot):
        rows = read(next((root / "parsed/archon-quests").glob(suffix)))["对话"]
        index = next(i for i, r in enumerate(rows) if r["内容"] == "哎呀，最后还是把家里的仓鼠找回来了啊。")
        blocks.append(rows[index:index + 17])
    if len(blocks[0]) != 17 or blocks[0] != blocks[1]:
        raise ValueError("taking-heart 17-line cutscene changed")
    return dict(known_speeches=found, taking_heart_17_lines_unchanged=True)


if __name__ == "__main__":
    main()
