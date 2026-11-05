"""Regression coverage based on the unmodified 2026-06-05 MediaWiki page."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.recovery.display import replay_unit
from tests.helpers import build_page_payload

FIXTURES = Path(__file__).parent / "fixtures" / "fold_dialogue"
PAGE = FIXTURES / "尾声的尾声__e4ed1de066.json"
# Spoken text transcribed from the supplied page; attached Wiki hints are separate.
TAKING_HEART = [
    ("「女士」", "哎呀，最后还是把家里的仓鼠找回来了啊。"),
    ("「女士」", "啃啃木桩，咬咬米袋，"),
    ("「女士」", "给蒙德添了那么多麻烦…"),
    ("温迪", "你说的不是仓鼠，是老鼠——"),
    ("「女士」", "现在没你说话的份，无礼的吟游诗人。"),
    ("「女士」", "呵，放弃统御蒙德的神，"),
    ("「女士」", "就只剩这点力量…"),
    ("温迪", "哦？你嘲笑我的资本，"),
    ("温迪", "就是从主人那里借来的力量吗？"),
    ("「女士」", "油嘴滑舌。"),
    ("「女士」", "这就是——「神之心」？"),
    ("「女士」", "哼，远远比不上我珍藏的华丽棋具啊。"),
    ("温迪", "那大概是因为你的审美…真的很烂吧？"),
    ("旅行者", "温迪——！"),
    ("「女士」", "…算了，反正「神之心」已经到手了。"),
    ("「女士」", "走吧，趁骑士团还没赶来。"),
    ("「女士」", "不要留下任何把柄。"),
]


def load_payload():
    return json.loads(PAGE.read_text(encoding="utf-8"))


def heart_dialogues(record):
    lines = record.to_dict()["对话"]
    starts = [i for i, line in enumerate(lines) if line["内容"] == TAKING_HEART[0][1]]
    assert len(starts) == 1, "The cutscene's first utterance must survive as its own entry"
    first = starts[0]
    return lines[first:first + 17]


def test_original_page_preserves_all_17_lines_and_normal_dialogue_contract():
    provenance = json.loads((FIXTURES / "provenance.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(PAGE.read_bytes()).hexdigest() == provenance["file_sha256"]
    parser = WikiTextParser()
    record = parser.parse_archon_quest_page(load_payload())
    lines = heart_dialogues(record)
    assert [(x["说话者"], x["内容"]) for x in lines] == TAKING_HEART
    assert all(set(x) == {"说话者", "内容", "类型", "所属任务流程"} for x in lines)
    assert all(x["所属任务流程"] == "将天空之琴交给芭芭拉" for x in lines)
    assert [x["类型"] for x in lines] == ["character"] * 13 + ["traveler"] + ["character"] * 3
    normal = record.to_dict()["对话"]
    assert normal[0] == {
        "说话者": "琴", "内容": "这位就是教会方面负责回收天空之琴的专员，祈礼牧师芭芭拉。",
        "类型": "character", "所属任务流程": "在教堂找到琴与温迪",
    }
    assert any(x["说话者"] == "温迪" and x["内容"] == "她是「女士」——愚人众十一执行官的第八席，代号「女士」。" for x in normal)
    recovery = parser.recover_page(load_payload())
    units = [u for u in recovery["units"] if (u["speaker"], u["text"]) in TAKING_HEART]
    assert [(u["speaker"], u["text"]) for u in units] == TAKING_HEART
    assert [u["source"]["start"] for u in units] == sorted(u["source"]["start"] for u in units)
    text = parser.extract_page_metadata(load_payload())[2]
    assert all(replay_unit(text, u) == u["text"] for u in units)
    assert any(u["type"] == "annotation" and u["text"] == "哑巴开口" for u in recovery["units"])
    assert any(u["type"] == "annotation" and u["text"] == "派蒙表情包之一出处" for u in recovery["units"])
    assert not any("哑巴开口" in row["内容"] or "派蒙表情包之一出处" in row["内容"] for row in normal)


@pytest.mark.parametrize("br", ["<br>", "<br/>", "<br />", "<BR>", '<br class="line">'])
def test_real_page_with_only_html_breaks_keeps_all_speakers_separate(br):
    parser = WikiTextParser()
    title, page_id, text = parser.extract_page_metadata(load_payload())
    # Same real text, only remove redundant physical newlines following <br>.
    payload = build_page_payload(title, text.replace("<br>\n", br), page_id=page_id)
    lines = heart_dialogues(parser.parse_archon_quest_page(payload))
    assert [(x["说话者"], x["内容"]) for x in lines] == TAKING_HEART
    recovery = parser.recover_page(payload)
    modified = parser.extract_page_metadata(payload)[2]
    assert all(replay_unit(modified, u) == u["text"] for u in recovery["units"])


def test_unmarked_break_fragment_is_preserved_without_inheriting_speaker():
    text = "==任务剧情==\n===场景===\n{{折叠|标题=过场|内容=温迪：甲。<br>没有说话者的续行。<br>派蒙：乙。}}"
    result = WikiTextParser().recover_page(build_page_payload("测试", text))
    assert [(u["speaker"], u["text"], u["type"]) for u in result["units"]] == [
        ("温迪", "甲。", "dialogue"), (None, "没有说话者的续行。", "narration"), ("派蒙", "乙。", "dialogue"),
    ]
    issue = next(i for i in result["issues"] if i["rule"] == "unattributed_break_fragment")
    assert issue["raw"] == "没有说话者的续行。"


def test_inline_break_with_explicit_template_speaker_stays_one_utterance():
    text = "==任务剧情==\n===场景===\n{{人物对话|角色=温迪|内容=甲。<br>乙。}}"
    result = WikiTextParser().recover_page(build_page_payload("测试", text))
    assert [(u["speaker"], u["text"]) for u in result["units"]] == [("温迪", "甲。\n乙。")]


@pytest.mark.parametrize("synopsis", ["{{任务描述|任务概述。}}", "> 任务概述。"])
def test_task_description_does_not_become_a_dialogue_step(synopsis):
    text = f"==任务剧情==\n{synopsis}\n===场景===\n*温迪：正文。"
    parser = WikiTextParser()
    payload = build_page_payload("测试", text)
    record = parser.parse_event_quest_page(payload)
    assert [step.title for step in record.dialogue] == ["场景"]
    assert any(u["type"] == "description" and u["text"] == "任务概述。" for u in parser.recover_page(payload)["units"])


def test_nested_positional_folds_keep_entities_repeats_and_order():
    text = """==任务剧情==
===场景===
*派蒙：开始。
{{折叠|过场|温迪：甲&amp;乙。<br>{{折叠框|内层|「女士」：重复。<br>「女士」：重复。}}<br>温迪：结束。}}
*派蒙：之后。
"""
    record = WikiTextParser().parse_archon_quest_page(build_page_payload("测试", text))
    assert [(x.speaker, x.text) for x in record.dialogues] == [
        ("派蒙", "开始。"), ("温迪", "甲&乙。"), ("「女士」", "重复。"),
        ("「女士」", "重复。"), ("温迪", "结束。"), ("派蒙", "之后。"),
    ]


def test_non_story_fold_is_retained_as_description_and_diagnosed():
    text = "{{折叠|标题=资料|内容=来源：任务攻略<br>图片说明}}\n==任务剧情==\n===场景===\n*温迪：正文。"
    parser = WikiTextParser()
    payload = build_page_payload("测试", text)
    assert [(x.speaker, x.text) for x in parser.parse_archon_quest_page(payload).dialogues] == [("温迪", "正文。")]
    recovery = parser.recover_page(payload)
    assert any(u["type"] == "description" and "来源：任务攻略" in u["text"] for u in recovery["units"])
    assert any(i["rule"] == "fold_outside_story" for i in recovery["issues"])


@pytest.mark.parametrize("method", ["parse_archon_quest_page", "parse_character_quest_page", "parse_event_quest_page"])
def test_fold_before_first_scene_survives_business_projection(method):
    text = "==任务剧情==\n{{折叠|标题=过场|内容=温迪：前导。}}\n===之后===\n*派蒙：后续。"
    record = getattr(WikiTextParser(), method)(build_page_payload("测试", text))
    if method == "parse_event_quest_page":
        pairs = [(entry.speaker, entry.content) for step in record.dialogue for entry in step.dialogue]
    else:
        pairs = [(x.speaker, x.text) for x in record.dialogues]
    assert pairs == [("温迪", "前导。"), ("派蒙", "后续。")]


def test_unknown_nested_template_has_source_diagnostic_instead_of_silent_loss():
    text = "==任务剧情==\n===场景===\n{{折叠|标题=过场|内容=温迪：{{未知台词|甲}}}}"
    result = WikiTextParser().recover_page(build_page_payload("测试", text))
    assert any(i["rule"] == "unknown_template" and "未知台词" in i["raw"] for i in result["issues"])


@pytest.mark.parametrize("wrapper", ["span", "b", "font"])
def test_complete_dialogue_inside_inline_html_keeps_speaker_boundaries(wrapper):
    text = f"==任务剧情==\n===场景===\n{{{{折叠|标题=过场|内容=<{wrapper}>温迪：甲。<br>派蒙：乙。</{wrapper}>}}}}"
    payload = build_page_payload("测试", text)
    parser = WikiTextParser()
    assert [(x.speaker, x.text) for x in parser.parse_archon_quest_page(payload).dialogues] == [("温迪", "甲。"), ("派蒙", "乙。")]
    assert all(replay_unit(text, u) == u["text"] for u in parser.recover_page(payload)["units"])


@pytest.mark.parametrize("separator", ["<br>", "\n"])
def test_inline_content_with_colon_is_not_reinterpreted_as_a_speaker(separator):
    text = f"==任务剧情==\n===场景===\n{{{{折叠|标题=过场|内容=温迪：<span>提示：甲。{separator}乙。</span>}}}}"
    record = WikiTextParser().parse_archon_quest_page(build_page_payload("测试", text))
    assert [(x.speaker, x.text) for x in record.dialogues] == [("温迪", "提示：甲。\n乙。")]


@pytest.mark.parametrize("separator", ["<br>", "<br />", "\n", "\r\n"])
def test_wrapped_speaker_after_bare_line_keeps_the_logical_boundary(separator):
    text = f"==任务剧情==\n===场景===\n{{{{折叠|标题=过场|内容=*温迪：甲。{separator}<span>派蒙：乙。</span>}}}}"
    record = WikiTextParser().parse_archon_quest_page(build_page_payload("测试", text))
    assert [(x.speaker, x.text) for x in record.dialogues] == [("温迪", "甲。"), ("派蒙", "乙。")]


def test_task_description_unknown_arguments_remain_diagnosed():
    text = "==任务剧情==\n{{任务描述|概述。|未支持内容。}}\n===场景===\n*温迪：正文。"
    result = WikiTextParser().recover_page(build_page_payload("测试", text))
    assert any(i["rule"] == "unsupported_display_argument" and i["raw"] == "未支持内容。" for i in result["issues"])


def test_real_normal_page_keeps_synopsis_inside_named_flow_as_narration():
    fixture = next(FIXTURES.glob("鸟瞰风物__*.json"))
    provenance = json.loads((FIXTURES / "provenance.json").read_text(encoding="utf-8"))["normal_page"]
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == provenance["file_sha256"]
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    lines = WikiTextParser().parse_archon_quest_page(payload).to_dict()["对话"]
    assert len(lines) == 16
    synopsis = "从坠星山谷启程，你和派蒙走走看看，一路前行。"
    assert [(row["所属任务流程"], row["类型"]) for row in lines if row["内容"] == synopsis] == [
        ("继续前进", "narration"), ("游过星落湖", "narration"),
    ]


def test_description_colon_in_named_flow_is_not_a_speaker_marker():
    text = "==任务剧情==\n===前往蒙德===\n{{任务描述|前往风神护佑之地：蒙德城。}}\n*派蒙：前进。"
    record = WikiTextParser().parse_archon_quest_page(build_page_payload("测试", text))
    assert [(x.speaker, x.text, x.dialogue_type) for x in record.dialogues] == [
        ("", "前往风神护佑之地：蒙德城。", "narration"), ("派蒙", "前进。", "character"),
    ]
