"""Semantic regressions from the independent twelve-page 0605 audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.recovery.display import replay_unit
from tests.helpers import build_page_payload

FIXTURES = Path(__file__).parent / "fixtures" / "audit_fixes"


def payload(suffix):
    path = next(FIXTURES.glob(f"*__{suffix}.json"))
    provenance = json.loads((FIXTURES / "provenance.json").read_text(encoding="utf-8"))
    expected_hash = next(row["sha256"] for row in provenance if row["file"] == path.name)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
    return json.loads(path.read_bytes())


def test_real_followup_keeps_55_speeches_and_seven_choices_in_source_order():
    parser = WikiTextParser()
    raw = payload("ef7a3ea1cd")
    expected = json.loads((FIXTURES / "followup_expected.json").read_text(encoding="utf-8"))
    record = parser.parse_event_quest_page(raw)
    dialogues = [entry for step in record.dialogue for entry in step.dialogue if entry.type in {"角色/NPC", "旅行者"}]
    options = [value for step in record.dialogue for entry in step.dialogue for value in entry.options]
    assert len(dialogues) == 343
    assert len(options) == 68
    assert [(row.speaker, row.content) for row in dialogues[-55:]] == [
        (row["speaker"], row["text"]) for row in expected["dialogues"]
    ]
    assert options[-7:] == [row["text"] for row in expected["options"]]
    assert not any("您来了，勇者殿下" in row.content for row in dialogues)
    assert not any("勇者嘛…则是" in row.content for row in dialogues)
    recovery = parser.recover_page(raw)
    text = parser.extract_page_metadata(raw)[2]
    assert all(replay_unit(text, u) == u["text"] for u in recovery["units"])


@pytest.mark.parametrize("heading", ["后续剧情", "后日谈剧情", "额外对话", "支线剧情"])
def test_plot_heading_variants_keep_story_but_stop_at_non_story_sibling(heading):
    text = f"==任务剧情==\n*派蒙：之前。\n=={heading}==\n*温迪：之后。\n==任务奖励==\n*原石：三十。"
    lines = WikiTextParser().parse_archon_quest_page(build_page_payload("测试", text)).dialogues
    assert [(row.speaker, row.text) for row in lines] == [("派蒙", "之前。"), ("温迪", "之后。")]


def test_dialogue_flow_subheading_does_not_close_its_parent_story_region():
    text = "==任务剧情==\n===与温迪对话===\n*温迪：之前。\n===前往教堂===\n*派蒙：之后。"
    record = WikiTextParser().parse_archon_quest_page(build_page_payload("测试", text))
    assert [(row.speaker, row.text) for row in record.dialogues] == [("温迪", "之前。"), ("派蒙", "之后。")]


@pytest.mark.parametrize("method", ["parse_archon_quest_page", "parse_character_quest_page", "parse_event_quest_page"])
def test_attached_blackout_is_separate_from_speech_in_every_business_adapter(method):
    text = "==任务剧情==\n===场景===\n*温迪：原句。{{黑幕|编辑提示}}\n*派蒙：继续。"
    parser = WikiTextParser()
    raw = build_page_payload("测试", text)
    record = getattr(parser, method)(raw)
    pairs = [(e.speaker, e.content) for s in record.dialogue for e in s.dialogue] if method == "parse_event_quest_page" else [(e.speaker, e.text) for e in record.dialogues]
    assert pairs == [("温迪", "原句。"), ("派蒙", "继续。")]
    recovered = parser.recover_page(raw)
    note = next(u for u in recovered["units"] if u["type"] == "annotation")
    assert note["speaker"] is None and note["text"] == "编辑提示"
    assert text[note["source"]["start"]:note["source"]["end"]] == "编辑提示"
    spoken = next(u for u in recovered["units"] if u["speaker"] == "温迪")
    assert not any(span["start"] <= note["source"]["start"] < span["end"] for span in spoken["text_spans"])
    assert all(replay_unit(text, u) == u["text"] for u in recovered["units"])


def test_real_inline_name_hint_is_not_appended_to_paimon_speech():
    parser = WikiTextParser()
    raw = payload("eee6ab4b6c")
    record = parser.parse_event_quest_page(raw)
    line = next(e for s in record.dialogue for e in s.dialogue if e.content.startswith("四倍甜日落果？"))
    assert line.speaker == "派蒙" and line.content == "四倍甜日落果？那不会是…"
    result = parser.recover_page(raw)
    assert any(u["type"] == "annotation" and u["text"] == "砂糖" for u in result["units"])


def test_blackouts_in_books_and_ambiguous_standalone_blackouts_are_not_deleted():
    text = "{{书籍|卷1名=书|卷1内容=原文{{黑幕|隐藏正文}}。}}\n==任务剧情==\n===场景===\n*温迪：{{黑幕|只有隐藏文本}}"
    result = WikiTextParser().recover_page(build_page_payload("测试", text))
    assert any(u["type"] == "book" and u["text"] == "原文隐藏正文。" for u in result["units"])
    assert any("只有隐藏文本" in u["text"] for u in result["units"])
    assert any(i["rule"] == "ambiguous_blackout_content" for i in result["issues"])


def test_real_morse_speech_keeps_translation_in_separate_annotations():
    parser = WikiTextParser()
    raw = payload("de71869e1b")
    result = parser.recover_page(raw)
    units = [u for u in result["units"] if u["type"] == "dialogue" and u["speaker"] == "「特尔克西」"]
    assert any(u["text"] == "-.. -... .-- -...？" for u in units)
    assert not any("法语" in u["text"] for u in units)
    assert any(u["type"] == "annotation" and u["text"] == "ça va?（法语，你好吗？）" for u in result["units"])
    text = parser.extract_page_metadata(raw)[2]
    assert all(replay_unit(text, u) == u["text"] for u in result["units"])


def test_explicit_punctuation_only_speech_is_not_discarded_as_a_separator():
    text = "==任务剧情==\n===场景===\n*机械：---{{黑幕|译文}}"
    record = WikiTextParser().parse_archon_quest_page(build_page_payload("测试", text))
    assert [(u.speaker, u.text) for u in record.dialogues] == [("机械", "---")]


def test_speaker_editor_request_is_separated_but_childhood_qualifier_is_preserved():
    parser = WikiTextParser()
    raw = payload("14f4e694ea")
    result = parser.recover_page(raw)
    assert any(u["speaker"] == "路人" and u["type"] == "dialogue" for u in result["units"])
    assert not any("有缘人" in (u["speaker"] or "") for u in result["units"])
    assert any(u["type"] == "annotation" and u["text"] == "未知，等待有缘人补全" for u in result["units"])
    assert any(u["speaker"] == "小艾梅莉埃" and u["speaker_status"] == "unresolved" for u in result["units"])
    assert any(i["rule"] == "ambiguous_speaker_blackout" for i in result["issues"])


@pytest.mark.parametrize("raw_speaker,expected,status", [
    ("{{黑幕|未知，等待有缘人补全}}路人", "路人", "resolved"),
    ("{{黑幕|小}}温迪", "小温迪", "unresolved"),
])
def test_character_dialogue_explicit_speaker_uses_the_same_annotation_rules(raw_speaker, expected, status):
    text = f"==任务剧情==\n===场景===\n{{{{人物对话|角色={raw_speaker}|内容=原文。}}}}"
    result = WikiTextParser().recover_page(build_page_payload("测试", text))
    spoken = next(u for u in result["units"] if u["type"] == "dialogue")
    assert spoken["speaker"] == expected and spoken["speaker_status"] == status
    if status == "resolved":
        assert any(u["type"] == "annotation" and "补全" in u["text"] for u in result["units"])


def test_real_document_accounts_are_retained_as_narration_not_animal_speakers():
    record = WikiTextParser().parse_character_quest_page(payload("7085f7cb33"))
    accounts = [
        "十一号盗宝鼬：大郎，6岁。", "十二号盗宝鼬：长次，8岁。", "八号陆鳗鳗：康奎尔，35岁。",
        "三号将军蟹：小春，25岁。", "五号妖狸：久住，60岁。", "九号陆鳗鳗：德沃沙克，40岁。",
    ]
    found = [row for row in record.dialogues if any(text in row.text for text in accounts)]
    assert len(found) == 6
    assert all(row.dialogue_type == "narration" and not row.speaker for row in found)
    assert [row.text for row in found] == accounts
    assert any(row.speaker == "八重神子" for row in record.dialogues)


@pytest.mark.parametrize("title", ["商会账目", "调查日志", "旅人的留言", "某处档案"])
def test_document_scope_prevents_colon_keys_from_becoming_speakers(title):
    text = f"==任务剧情==\n===场景===\n{{{{折叠|标题={title}|内容=编号：甲。<br>备注：乙。}}}}\n*派蒙：看到记录了。"
    record = WikiTextParser().parse_archon_quest_page(build_page_payload("测试", text))
    assert all(not row.speaker for row in record.dialogues[:-1])
    assert "编号：甲。" in "\n".join(row.text for row in record.dialogues)
    assert record.dialogues[-1].speaker == "派蒙"


def test_real_colon_ended_narration_is_retained_in_recovery_and_business_json():
    parser = WikiTextParser()
    raw = payload("d6ba260bf8")
    expected = "你们本以为一切已经结束，却再次有光在你们身后亮起，那是哈夫丹的灵魂在散发出最后的光芒。他向戴因说道："
    result = parser.recover_page(raw)
    unit = next(u for u in result["units"] if u["text"] == expected)
    assert unit["speaker"] is None and unit["type"] == "narration"
    record = parser.parse_archon_quest_page(raw)
    assert any(row.text == expected and not row.speaker and row.dialogue_type == "narration" for row in record.dialogues)
    assert any(row.speaker == "哈夫丹" for row in record.dialogues)


@pytest.mark.parametrize("line", ["旁白结束于此：", "*温迪：", "<span>叙述：</span>"])
def test_empty_colon_suffix_retains_text_and_explicit_diagnostic(line):
    text = f"==任务剧情==\n===场景===\n{line}\n*派蒙：之后。"
    result = WikiTextParser().recover_page(build_page_payload("测试", text))
    assert len(result["units"]) == 2
    assert result["units"][0]["type"] == "narration"
    assert result["units"][0]["text"].endswith("：")
    assert any(i["rule"] == "empty_speech_after_colon" for i in result["issues"])
