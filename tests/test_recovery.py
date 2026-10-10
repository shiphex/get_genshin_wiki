from __future__ import annotations

import hashlib
import json
import socket
import sys
from types import ModuleType
from pathlib import Path
from unittest.mock import patch

import pytest

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore
from tests.helpers import build_page_payload

FIXTURES = Path(__file__).parent / "fixtures" / "recovery"
CASES = json.loads((FIXTURES / "regression_cases.json").read_text(encoding="utf-8"))["fixtures"]
EXPECTED_QUOTES = json.loads((FIXTURES / "expected_quotes.json").read_text(encoding="utf-8"))


def recover(text: str, *, title="测试任务", page_id=7, resolver=None):
    parser = WikiTextParser()
    assert callable(getattr(parser, "recover_page", None)), "missing source-aware recovery API"
    return parser.recover_page(
        build_page_payload(title, text, page_id=page_id), raw_file="pages/test.json", resolve_page=resolver
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_frozen_page_recovery_matches_original_identity_and_quote_anchors(case):
    raw = (FIXTURES / case["raw_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == case["file_sha256"]
    payload = json.loads(raw)
    parser = WikiTextParser()
    assert callable(getattr(parser, "recover_page", None)), "missing source-aware recovery API"
    result = parser.recover_page(payload, raw_file=case["raw_file"])
    assert result["source"]["page_title"] == case["page_title"]
    assert result["source"]["page_id"] == case["page_id"]
    assert result["source"]["wikitext_sha256"] == case["wikitext_sha256"]
    if case["case_id"] == "case_19":
        assert result["units"] == []
        assert any(i["status"] == "needs_source" for i in result["issues"])
        return
    if case["case_id"] == "case_18":
        assert result["dependencies"]
        assert any(i["status"] == "needs_source" for i in result["issues"])
        return
    text = parser.extract_page_metadata(payload)[2]
    for expected in EXPECTED_QUOTES.get(case["case_id"], []):
        assert any(u["text"] == expected["text"] and u["speaker"] == expected["speaker"]
                   and u["source"]["start"] == expected["start"] and u["source"]["end"] == expected["end"]
                   for u in result["units"]), (case["case_id"], expected)
    for anchor in case.get("literal_quote_anchors", []):
        matching = [u for u in result["units"] if anchor["text"] in u["text"]]
        assert matching, (case["case_id"], anchor)
        assert any(u["source"]["start"] <= anchor["start"] < u["source"]["end"] for u in matching)
    for unit in result["units"]:
        src = unit["source"]
        assert 0 <= src["start"] < src["end"] <= len(text)
        assert unit["speaker"] is None or "{{" not in unit["speaker"]
        assert unit["branch_path"] is not None or unit["branch_status"] == "unresolved"
    if case["case_id"] == "case_01":
        assert len(result["scenes"]) >= 7
        assert any(s["empty"] for s in result["scenes"])
        assert any(u["type"] == "narration" and "调配完毕" in u["text"] for u in result["units"])
    if case["case_id"] in ("case_04", "case_05", "case_14"):
        assert any(u["branch_path"] for u in result["units"])
        assert any(p["kind"] == "tab" for u in result["units"] for p in u["branch_path"] or [])
    if case["case_id"] == "case_15":
        assert len({u["scene_id"] for u in result["units"] if u["type"] == "book"}) == 3
        assert all("{{颜色" not in u["text"] for u in result["units"])
    if case["case_id"] == "case_17":
        assert sum(u["type"] == "voice" for u in result["units"]) >= 60


def test_nested_choices_and_repeated_lines_have_distinct_source_positions():
    text = """==任务剧情==
===同名场景===
*派蒙：重复。
{{剧情选项|选项1=甲|剧情1=*派蒙：甲回应。
{{剧情选项|选项1=内甲|剧情1=*？？？：内回应。|选项2=内乙|剧情2=*：空说话者。}}
|选项2=乙|剧情2=*派蒙：乙回应。}}
===同名场景===
*派蒙：重复。
"""
    result = recover(text)
    units = result["units"]
    repeats = [u for u in units if u["text"] == "重复。"]
    assert len(repeats) == 2
    assert repeats[0]["source"]["start"] != repeats[1]["source"]["start"]
    assert repeats[0]["scene_id"] != repeats[1]["scene_id"]
    inner = next(u for u in units if u["text"] == "内回应。")
    assert inner["speaker"] == "？？？"
    assert [p["label"] for p in inner["branch_path"]] == ["甲", "内甲"]
    assert next(u for u in units if u["text"] == "空说话者。")["speaker"] == ""
    assert next(u for u in units if u["text"] == "乙回应。")["branch_path"][0]["label"] == "乙"
    assert repeats[0]["branch_path"] == []
    assert [u["unit_id"] for u in units] == [u["unit_id"] for u in recover(text)["units"]]


def test_display_wrappers_and_unknown_templates_are_not_silently_erased():
    result = recover("==任务剧情==\n===<big>{{颜色|红|场景}}</big>===\n*{{#tag:span|派蒙}}：{{颜色|蓝|保留50%战斗力量。}}\n{{未知模板|隐藏中文}}")
    assert result["scenes"][0]["title"] == "场景"
    unit = next(u for u in result["units"] if "保留50%" in u["text"])
    assert unit["speaker"] == "派蒙"
    assert unit["text"] == "保留50%战斗力量。"
    assert any(i["rule"] == "unknown_template" and "隐藏中文" in i["raw"] for i in result["issues"])


def test_redirect_cycles_ambiguities_and_missing_dependencies_remain_unresolved():
    pages = {"甲": build_page_payload("甲", "#重定向:[[乙]]", page_id=1),
             "乙": build_page_payload("乙", "#重定向:[[甲]]", page_id=2)}
    resolver = lambda title: [{"raw_file": title + ".json", "payload": pages[title]}] if title in pages else []
    result = recover("#重定向:[[甲]]", resolver=resolver)
    assert result["units"] == []
    assert any(i["rule"] == "redirect_cycle" for i in result["issues"])
    ambiguous = lambda title: [{"raw_file": "1.json", "payload": pages["甲"]}, {"raw_file": "2.json", "payload": pages["乙"]}]
    assert any(i["rule"] == "ambiguous_dependency" for i in recover("#重定向:[[甲]]", resolver=ambiguous)["issues"])
    assert any(i["status"] == "needs_source" for i in recover("{{:缺失正文}}") ["issues"])


def test_missing_branch_label_does_not_turn_a_response_into_linear_dialogue():
    result = recover("==任务剧情==\n===剧情===\n{{剧情选项|剧情1=*派蒙：归属不明。}}")
    unit = next(u for u in result["units"] if u["text"] == "归属不明。")
    assert unit["branch_path"] is None
    assert unit["branch_status"] == "unresolved"


def test_unknown_option_display_retains_response_with_unresolved_branch():
    result = recover("==任务剧情==\n===场景===\n{{剧情选项|选项1={{未知显示|甲}}|剧情1=*派蒙：真实回应。}}")
    unit = next(u for u in result["units"] if u["text"] == "真实回应。")
    assert unit["branch_path"] is None
    assert any(i["rule"] == "unresolved_choice" for i in result["issues"])


def test_unknown_tab_label_and_speaker_template_remain_explicitly_unresolved():
    result = recover("==任务剧情==\n===场景===\n<tabber>{{未知标签|甲}}=*派蒙：原文回应。</tabber>\n{{人物对话|角色={{未知姓名|某人}}|内容=保留正文。}}")
    response = next(u for u in result["units"] if u["text"] == "原文回应。")
    assert response["branch_path"] is None
    spoken = next(u for u in result["units"] if u["text"] == "保留正文。")
    assert spoken["speaker"] == ""
    assert spoken["speaker_status"] == "unresolved"


def test_nested_plot_container_keeps_ancestor_choice_path():
    result = recover("==任务剧情==\n===场景===\n{{剧情选项|选项1=甲|剧情1={{剧情|段落名称1.1=内部|内容1.1=*派蒙：嵌套正文。}}}}")
    unit = next(u for u in result["units"] if u["text"] == "嵌套正文。")
    assert [p["label"] for p in unit["branch_path"]] == ["甲"]


def test_cached_plain_template_consumption_excludes_documentation():
    provider = build_page_payload("模板:旁白段落", "<noinclude>填写提示，不是剧情。</noinclude><includeonly>已缓存的原文旁白。</includeonly>", page_id=8)
    resolver = lambda title: [{"raw_file": "pages/template.json", "payload": provider}] if title == "模板:旁白段落" else []
    result = recover("==任务剧情==\n===场景===\n{{旁白段落}}", resolver=resolver)
    unit = next(u for u in result["units"] if u["text"] == "已缓存的原文旁白。")
    assert unit["source"]["page_id"] == 8
    assert not any("填写提示" in u["text"] for u in result["units"])
    assert any(d["status"] == "consumed" for d in result["dependencies"])


def test_cached_template_visibility_is_applied_before_business_extraction():
    provider = build_page_payload("模板:旁白", "<onlyinclude>真实旁白。</onlyinclude><noinclude>{{任务|任务剧情=*派蒙：填写示例。}}</noinclude>", page_id=8)
    resolver = lambda title: [{"raw_file": "pages/provider.json", "payload": provider}] if title == "模板:旁白" else []
    result = recover("==任务剧情==\n===场景===\n{{旁白}}", resolver=resolver)
    assert any(u["text"] == "真实旁白。" for u in result["units"])
    assert not any("填写示例" in u["text"] for u in result["units"])
    provider = build_page_payload("模板:旁白", "<onlyinclude>{{任务|任务剧情=*派蒙：真实正文。}}</onlyinclude>{{任务|任务剧情=*派蒙：不应转入正文。}}", page_id=8)
    result = recover("==任务剧情==\n===场景===\n{{旁白}}", resolver=resolver)
    assert [u["text"] for u in result["units"]] == ["真实正文。"]
    assert recover('<noinclude>{{任务|任务剧情=*派蒙：填写示例。}}</noinclude>')["units"] == []


def test_repeated_provider_consumption_retains_all_scene_and_branch_contexts():
    provider = build_page_payload("模板:旁白", "<onlyinclude>原文旁白。</onlyinclude>", page_id=8)
    resolver = lambda title: [{"raw_file": "pages/provider.json", "payload": provider}] if title == "模板:旁白" else []
    result = recover("==任务剧情==\n===甲场景===\n{{旁白}}\n===乙场景===\n{{旁白}}", resolver=resolver)
    assert len(result["units"]) == 1
    assert len({c["scene_id"] for c in result["units"][0]["consumed_by"]}) == 2
    result = recover("==任务剧情==\n===场景===\n{{剧情选项|选项1=甲|剧情1={{旁白}}|选项2=乙|剧情2={{旁白}}}}", resolver=resolver)
    unit = next(u for u in result["units"] if u["text"] == "原文旁白。")
    assert {c["branch_path"][0]["label"] for c in unit["consumed_by"]} == {"甲", "乙"}


def test_inline_display_audit_separates_visible_style_and_unknown_arguments():
    from get_genshin_wiki.recovery.audit import audit_page
    from get_genshin_wiki.recovery.source import SourcePage

    text = "==任务剧情==\n===场景===\n*派蒙：{{颜色|红|正文|未知=隐藏中文}}"
    page = SourcePage.from_payload(build_page_payload("测试任务", text, page_id=7), "pages/test.json")
    result = recover(text)
    assert result["units"][0]["text"] == "正文"
    candidates = audit_page(page, result["regions"], result["units"])
    assert next(c for c in candidates if c["text"] == "正文")["disposition"] == "exported"
    assert next(c for c in candidates if c["text"] == "红")["disposition"] == "metadata"
    assert next(c for c in candidates if c["text"] == "隐藏中文")["disposition"] == "unsupported"
    assert any(i["rule"] == "unsupported_display_argument" for i in result["issues"])


def test_fold_unknown_argument_stays_unsupported():
    from get_genshin_wiki.recovery.audit import audit_page
    from get_genshin_wiki.recovery.source import SourcePage

    text = "==任务剧情==\n===场景===\n{{折叠|标题=普通标题|内容=*派蒙：正文。|未支持剧情=隐藏中文}}"
    page = SourcePage.from_payload(build_page_payload("测试任务", text, page_id=7), "pages/test.json")
    result = recover(text)
    candidates = audit_page(page, result["regions"], result["units"])
    assert next(c for c in candidates if c["text"] == "隐藏中文")["disposition"] == "unsupported"
    assert any(i["rule"] == "unsupported_fold_argument" for i in result["issues"])


def test_scene_title_unknown_display_argument_stays_in_source_inventory():
    from get_genshin_wiki.recovery.audit import audit_page
    from get_genshin_wiki.recovery.source import SourcePage

    text = "==任务剧情==\n==={{颜色|红|场景|未知=场景隐藏中文}}===\n*派蒙：正文。"
    page = SourcePage.from_payload(build_page_payload("测试任务", text, page_id=7), "pages/test.json")
    result = recover(text)
    candidates = audit_page(page, result["regions"], result["units"])
    assert next(c for c in candidates if c["text"] == "场景隐藏中文")["disposition"] == "unsupported"


def test_character_dialogue_template_keeps_explicit_speaker():
    result = recover("==任务剧情==\n===对话===\n{{人物对话|角色={{颜色|蓝|派蒙}}|内容=你好。}}")
    unit = next(u for u in result["units"] if u["text"] == "你好。")
    assert unit["speaker"] == "派蒙"
    assert unit["type"] == "dialogue"


def test_self_closing_markup_inside_character_container_does_not_invent_text():
    result = recover('<div><br />{{角色|介绍=原有介绍。}}<img src="local.png" /></div>')
    assert any(u["text"] == "原有介绍。" for u in result["units"])
    assert all("None" not in u["text"] for u in result["units"])


def test_unclosed_attribute_quote_preserves_nested_source_offsets():
    result = recover('<div style="unterminated>{{角色|介绍=原有介绍。}}</div>')
    unit = next(u for u in result["units"] if u["text"] == "原有介绍。")
    assert unit["source"]["start"] == 33


def test_legacy_event_parser_uses_plot_container_and_shared_display_rules():
    case = CASES[0]
    payload = json.loads((FIXTURES / case["raw_file"]).read_text(encoding="utf-8"))
    record = WikiTextParser().parse_event_quest_page(payload)
    assert len(record.dialogue) == 6
    assert any("能在这里见到你" in item.content for group in record.dialogue for item in group.dialogue)
    case = next(c for c in CASES if c["case_id"] == "case_15")
    book = WikiTextParser().parse_book_page(json.loads((FIXTURES / case["raw_file"]).read_text(encoding="utf-8")))
    assert all("{{颜色" not in volume.content for volume in book.volumes)


def test_character_voice_consumption_retains_actual_provider_source():
    owner = next(c for c in CASES if c["case_id"] == "case_16")
    voice = next(c for c in CASES if c["case_id"] == "case_17")
    payload = json.loads((FIXTURES / owner["raw_file"]).read_text(encoding="utf-8"))
    resolver = lambda title: [{"raw_file": voice["raw_file"], "payload": json.loads((FIXTURES / voice["raw_file"]).read_text(encoding="utf-8"))}] if title == "七七语音" else []
    parser = WikiTextParser()
    assert callable(getattr(parser, "recover_page", None))
    result = parser.recover_page(payload, raw_file=owner["raw_file"], resolve_page=resolver)
    units = [u for u in result["units"] if u["type"] == "voice"]
    assert len(units) >= 60
    assert all(u["source"]["page_id"] == 4088 for u in units)
    assert any(d["target_title"] == "七七语音" and d["status"] == "consumed" for d in result["dependencies"])


def test_batch_same_display_name_survives_storage_aggregation_resume_and_index(tmp_path):
    from tools.batch_character_quests import run_batch
    from tools.generate_character_quest_index import run_generate_index

    store = JsonFileStore(tmp_path)
    cases = [c for c in CASES if c["family"] == "same_display_title"]
    store.write("categories", "character-quests", {"categories": ["传说任务"]})
    store.write("category_members", "传说任务", [c["page_title"] for c in cases])
    store.write("pages", "传说任务", build_page_payload("传说任务", "==传说任务和部族纪闻==\n*[[休憩系列]]"))
    for case in cases:
        store.write("pages", case["page_title"], json.loads((FIXTURES / case["raw_file"]).read_text(encoding="utf-8")))
    output = tmp_path / "quests.json"
    with patch("requests.sessions.Session.request", side_effect=AssertionError("network forbidden")):
        result = run_batch(data_root=tmp_path, output_path=output, list_title="传说任务", resume=False)
        assert result["quest_count"] == 4
        assert {r["source_title"] for r in result["quests"]} == {c["page_title"] for c in cases}
        assert all(store.exists("parsed/character-quests", c["page_title"]) for c in cases)
        assert run_batch(data_root=tmp_path, output_path=output, list_title="传说任务", resume=True)["quest_count"] == 4
        indexed = run_generate_index(data_root=tmp_path, output_path=tmp_path / "index.json", list_title="传说任务")
        assert indexed["quest_count"] == 4
        assert {r["source_title"] for r in indexed["index"]} == {c["page_title"] for c in cases}


def test_offline_export_records_every_candidate_and_rejects_overwrites(tmp_path):
    import importlib.util

    assert importlib.util.find_spec("tools.recover_snapshot") is not None, "missing offline entrypoint"
    from tools.recover_snapshot import run_recovery

    out = tmp_path / "recovery"
    with patch("socket.socket.connect", side_effect=AssertionError("socket forbidden")), patch("requests.sessions.Session.request", side_effect=AssertionError("HTTP forbidden")), patch("get_genshin_wiki.client.MediaWikiClient.__init__", side_effect=AssertionError("client initialization forbidden")):
        report = run_recovery(input_root=FIXTURES, output_root=out, offline=True)
    units = [json.loads(line) for line in (out / "text_units.jsonl").read_text(encoding="utf-8").splitlines()]
    candidates = [json.loads(line) for line in (out / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(units) > 1000
    assert report["page_count"] == 19
    assert candidates and all(c["disposition"] in {"exported", "metadata", "non_story", "needs_source", "unsupported"} for c in candidates)
    assert len({u["unit_id"] for u in units}) == len(units)
    with pytest.raises(ValueError, match="non-empty"):
        run_recovery(input_root=FIXTURES, output_root=out, offline=True)
    with pytest.raises(ValueError):
        run_recovery(input_root=FIXTURES, output_root=FIXTURES / "new-output", offline=True)
    with pytest.raises(ValueError, match="offline"):
        run_recovery(input_root=FIXTURES, output_root=tmp_path / "online", offline=False)


def test_independent_inventory_keeps_omitted_chinese_and_explains_speaker_positions():
    from get_genshin_wiki.recovery.audit import audit_page
    from get_genshin_wiki.recovery.source import SourcePage

    text = "==任务剧情==\n===场景===\n*派蒙：已保存。\n{{未知|尚未支持的文字}}\n"
    page = SourcePage.from_payload(build_page_payload("测试任务", text, page_id=7), "pages/test.json")
    result = recover(text)
    candidates = audit_page(page, result["regions"], result["units"])
    assert any("尚未支持的文字" in c["text"] and c["disposition"] == "unsupported" for c in candidates)
    assert any("已保存。" in c["text"] and c["disposition"] == "exported" for c in candidates)
    # Remove all exporter evidence: the independent source inventory must remain.
    omitted = audit_page(page, [], [])
    assert len(omitted) == len(candidates)
    assert any("已保存。" in c["text"] and c["disposition"] == "unsupported" for c in omitted)


def test_visible_link_target_is_audited_as_body_text():
    from get_genshin_wiki.recovery.audit import audit_page
    from get_genshin_wiki.recovery.source import SourcePage

    text = "==任务剧情==\n===场景===\n*派蒙：看[[月亮]]。"
    page = SourcePage.from_payload(build_page_payload("测试任务", text, page_id=7), "pages/test.json")
    result = recover(text)
    candidates = audit_page(page, result["regions"], result["units"])
    assert any(c["text"] == "月亮" and c["disposition"] == "exported" for c in candidates)


def test_unknown_business_field_is_not_reclassified_as_metadata():
    from get_genshin_wiki.recovery.audit import audit_page
    from get_genshin_wiki.recovery.source import SourcePage

    text = "{{任务|任务名称=测试任务|未支持剧情=真实未提取中文。}}"
    page = SourcePage.from_payload(build_page_payload("测试任务", text, page_id=7), "pages/test.json")
    result = recover(text)
    candidates = audit_page(page, result["regions"], result["units"])
    assert any(c["text"] == "真实未提取中文。" and c["disposition"] == "unsupported" for c in candidates)


def test_recovery_runs_are_identical_and_baseline_mismatch_prevents_output(tmp_path):
    from tools.recover_snapshot import run_recovery, snapshot_manifest

    before = snapshot_manifest(FIXTURES)
    one, two = tmp_path / "one", tmp_path / "two"
    run_recovery(input_root=FIXTURES, output_root=one, offline=True)
    run_recovery(input_root=FIXTURES, output_root=two, offline=True)
    for name in ("text_units.jsonl", "scenes.jsonl", "candidates.jsonl", "dependencies.jsonl", "summary.json"):
        assert (one / name).read_bytes() == (two / name).read_bytes(), name
    output_manifest = json.loads((one / "output_manifest.json").read_text(encoding="utf-8"))
    assert "summary.md" in {item["path"] for item in output_manifest["files"]}
    assert snapshot_manifest(FIXTURES) == before
    baseline = tmp_path / "bad-manifest.json"
    baseline.write_text(json.dumps({"files": [], "fingerprint_sha256": "wrong"}), encoding="utf-8")
    with pytest.raises(ValueError, match="hash baseline"):
        run_recovery(input_root=FIXTURES, output_root=tmp_path / "bad", offline=True, manifest_path=baseline)
    assert not (tmp_path / "bad").exists()


def test_offline_guard_blocks_direct_http_and_dns():
    import requests
    from tools.recover_snapshot import offline_guard

    with offline_guard():
        with pytest.raises(RuntimeError, match="forbidden"):
            requests.get("https://example.invalid")
        with pytest.raises(RuntimeError, match="forbidden"):
            socket.getaddrinfo("example.invalid", 443)


def test_unknown_sources_remain_unresolved_with_model_sdks_forbidden():
    class ForbiddenSDK(ModuleType):
        def __getattr__(self, name):
            raise AssertionError("model access forbidden")

    poisoned = {name: ForbiddenSDK(name) for name in ("openai", "anthropic", "litellm", "transformers")}
    with patch.dict(sys.modules, poisoned):
        result = recover("==任务剧情==\n===场景===\n{{未知剧情模板|不能补写的原文}}\n{{:未缓存来源}}")
    assert result["units"] == []
    assert any("不能补写的原文" in issue["raw"] for issue in result["issues"])
    assert any(issue["status"] == "needs_source" for issue in result["issues"])

