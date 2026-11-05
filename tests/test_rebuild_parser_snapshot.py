import copy
import subprocess
import sys
import zipfile

import pytest

from get_genshin_wiki.parser import WikiTextParser
from tests.helpers import build_page_payload
from tools import rebuild_parser_snapshot as rebuild


def test_archive_traversal_is_rejected_before_any_extraction(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("pages/valid.json", "{}")
        z.writestr("../escape.json", "{}")
    target = tmp_path / "input"
    with pytest.raises(ValueError, match="unsafe"):
        rebuild.safe_extract(archive, target)
    assert not target.exists()
    assert not (tmp_path / "escape.json").exists()


def test_existing_output_is_never_modified(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep"
    sentinel.write_text("original")
    with pytest.raises(FileExistsError):
        rebuild.rebuild_snapshot(tmp_path / "unused.zip", target)
    assert sentinel.read_text() == "original"


def test_unexplained_recovery_change_blocks_delivery():
    text = "==任务剧情==\n===场景===\n*派蒙：原句。"
    result = WikiTextParser().recover_page(build_page_payload("测试", text))
    modified = copy.deepcopy(result)
    modified["units"][0]["text"] = "无来源的新句。"
    with pytest.raises(ValueError, match="unexplained"):
        rebuild.audit_units(text, result, modified)


def test_ascii_speaker_change_maps_duplicate_speeches_by_source_not_text():
    text = "==任务剧情==\n===场景===\n*派蒙:重复。\n*派蒙:重复。"
    current = WikiTextParser().recover_page(build_page_payload("测试", text))
    old = copy.deepcopy(current)
    for unit in old["units"]:
        unit["source"]["start"] = unit["speaker_source"]["start"]
        unit["text"] = "派蒙:重复。"
        unit["type"] = "narration"
        unit["speaker"] = None
        unit.pop("speaker_source")
    changes = rebuild.audit_units(text, old, current)
    assert len(changes) == 2
    assert [c["reason"] for c in changes] == ["ascii_speaker_separator"] * 2
    assert changes[0]["after"]["source"]["start"] < changes[1]["after"]["source"]["start"]
    assert all(c["before"]["source"]["end"] == c["after"]["source"]["end"] for c in changes)


def test_speaker_identity_must_replay_its_own_source():
    text = "==任务剧情==\n===场景===\n*派蒙:原句。"
    old = WikiTextParser().recover_page(build_page_payload("测试", text))
    new = copy.deepcopy(old)
    old["units"][0]["source"]["start"] = old["units"][0]["speaker_source"]["start"]
    old["units"][0].update(speaker=None, type="narration", text="派蒙:原句。")
    old["units"][0].pop("speaker_source")
    new["units"][0]["speaker"] = "无来源的角色"
    with pytest.raises(ValueError, match="speaker"):
        rebuild.audit_units(text, old, new)


def test_nonidentical_repeat_cannot_be_packaged(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for root, text in ((first, "first"), (second, "different")):
        (root / "snapshot").mkdir(parents=True)
        (root / "snapshot/body.json").write_text(text)
    with pytest.raises(ValueError, match="repeat"):
        rebuild.package_snapshot(first, second, tmp_path / "delivery")
    assert not (tmp_path / "delivery").exists()


def test_a_single_run_cannot_claim_independent_repeat(tmp_path):
    run = tmp_path / "run"
    (run / "snapshot").mkdir(parents=True)
    with pytest.raises(ValueError, match="distinct"):
        rebuild.package_snapshot(run, run, tmp_path / "delivery")
    assert not (tmp_path / "delivery").exists()


@pytest.mark.parametrize("field,value", [
    ("source_kind", "wiki_editorial"), ("display_status", "partial"),
    ("text_spans", []), ("branch_status", "unresolved"),
])
def test_valid_ascii_fix_does_not_authorize_other_unit_corruption(field, value):
    text = "==任务剧情==\n===场景===\n*派蒙:原句。"
    new = WikiTextParser().recover_page(build_page_payload("测试", text))
    old = copy.deepcopy(new)
    u = old["units"][0]
    u["source"]["start"] = u["speaker_source"]["start"]
    u.update(speaker=None, type="narration", text="派蒙:原句。", source_kind="unknown", narration_kind="unknown")
    u.pop("speaker_source")
    new["units"][0][field] = value
    with pytest.raises(ValueError, match="unexplained"):
        rebuild.audit_units(text, old, new)


def test_unrelated_unknown_diagnostic_cannot_disappear():
    text = "==任务剧情==\n===场景===\n*派蒙：原句。"
    old = WikiTextParser().recover_page(build_page_payload("测试", text))
    new = copy.deepcopy(old)
    old["issues"].append({"rule": "unknown_template", "source": old["units"][0]["source"], "raw": "{{未知}}"})
    with pytest.raises(ValueError, match="diagnostic"):
        rebuild.audit_units(text, old, new)


def test_duplicate_options_and_narration_keep_branch_pointers():
    from get_genshin_wiki.recovery.legacy import character_dialogues
    text = "==任务剧情==\n===场景===\n{{剧情选项|选项1=重复|剧情1=*重复|选项2=重复|剧情2=*重复}}"
    recovery = WikiTextParser().recover_page(build_page_payload("测试", text))
    record = {"对话": [r.to_dict() for r in character_dialogues(recovery)]}
    pointers = rebuild._pointers(record, "character-quests", recovery)
    assert [pointers[rebuild._unit_key(u)] for u in recovery["units"]] == [
        "/对话/0", "/对话/2", "/对话/1", "/对话/3",
    ]


def test_index_building_cannot_mutate_aggregate_records():
    records = [
        {"source_title": "第一日", "任务名称": "幕间小憩", "所属任务": "系列", "后续任务": "幕间小憩"},
        {"source_title": "第三日", "任务名称": "幕间小憩", "所属任务": "系列", "前置任务": "幕间小憩"},
    ]
    original = copy.deepcopy(records)
    rebuild.build_expanded_character_index([], records)
    assert records == original


def test_aggregate_cannot_add_unrelated_diagnostics(tmp_path):
    frozen, snapshot = tmp_path / "input", tmp_path / "snapshot"
    record = {"source_title": "测试", "任务名称": "任务"}
    summary = {"quests": [record], "index": []}
    rebuild.write(frozen / "character_quests.json", summary)
    rebuild.write(snapshot / "parsed/character-quests/page.json", record)
    changed = copy.deepcopy(summary)
    changed["quests"][0]["reference_issues"] = [{"rule": "unrelated"}]
    rebuild.write(snapshot / "character_quests.json", changed)
    with pytest.raises(ValueError, match="aggregate"):
        rebuild.validate_aggregates(frozen, snapshot)


def test_uncertain_ascii_diagnostic_supports_full_coverage_audit(tmp_path):
    from tools.recover_snapshot import run_recovery
    source, output = tmp_path / "input", tmp_path / "recovery"
    rebuild.write(source / "pages/page.json", build_page_payload(
        "测试", "==任务剧情==\n===场景===\n*时间:10:30"))
    report = run_recovery(input_root=source, output_root=output, offline=True)
    assert report["source_replay"]["failures"] == 0
    assert report["issue_rules"]["ambiguous_ascii_speaker"] == 1


def test_finish_staged_requires_a_validated_baseline_before_writing(tmp_path):
    root = tmp_path / "partial"
    rebuild.write(root / "snapshot/keep.json", {"keep": True})
    with pytest.raises(ValueError, match="baseline"):
        rebuild.rebuild_snapshot(tmp_path / "unused.zip", root, finish_staged=True)
    assert rebuild.read(root / "snapshot/keep.json") == {"keep": True}


def test_finish_staged_cli_loads_project_from_another_directory(tmp_path):
    root = tmp_path / "partial"
    root.mkdir()
    result = subprocess.run([
        sys.executable, "-B", "-X", "utf8", rebuild.__file__, "--source-zip", str(tmp_path / "unused.zip"),
        "--output-root", str(root), "--finish-staged",
    ], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode != 0
    assert "validated baseline checkpoint required" in result.stderr
