"""Frozen V2.3.0 regressions: ruby fallback and ASCII speaker separators."""
import hashlib
import json
import re
from pathlib import Path

import pytest

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.recovery.display import display_text, replay_unit
from tests.helpers import build_page_payload

FIXTURES = Path(__file__).parent / "fixtures/parser_v231"
APEP = [
    ("阿佩普", "「龙王」自世界之外取得漆黑之力，带领我们反抗外来者定义的秩序。"),
    ("阿佩普", "嗯，后来「阿赫玛尔」在「娜布·玛莉卡塔」的帮助下获得了这种力量。"),
]
FINALE = [
    ("派蒙", "芙卡洛斯摧毁了水神的神座，归还了力量，你变成了完全状态的元素龙王…"),
    ("丝柯克", "你的身上，现在带着「第三降临者的遗骨」吧？"),
    ("丝柯克", "嗯…用你们常用的说法，好像应该叫…「神之心」？"),
    ("那维莱特", "你所说的「第三降临者」，指的是谁？又是在什么时候死去的？"),
    ("丝柯克", "师父之前没有和我提过，可能对我来说是无足轻重的信息。"),
]


@pytest.mark.parametrize("suffix,method,expected,flow", [
    ("b8c0d1a9aa", "parse_character_quest_page", APEP, "与阿佩普交谈"),
    ("2832f60895", "parse_archon_quest_page", FINALE, "◆与那维莱特对话"),
])
def test_frozen_speeches_keep_identity_flow_and_source_order(suffix, method, expected, flow):
    path = next(FIXTURES.glob("*" + suffix + ".json"))
    provenance = json.loads((FIXTURES / "provenance.json").read_bytes())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == provenance["files"][path.name]
    raw = json.loads(path.read_bytes())
    parser = WikiTextParser()
    rows = getattr(parser, method)(raw).to_dict()["对话"]
    recovery = parser.recover_page(raw, raw_file="pages/" + path.name)
    text = parser.extract_page_metadata(raw)[2]
    positions = []
    for speaker, content in expected:
        found = [(i, row) for i, row in enumerate(rows) if row["内容"] == content]
        assert len(found) == 1
        index, row = found[0]
        positions.append(index)
        assert row == {"说话者": speaker, "内容": content, "类型": "character", "所属任务流程": flow}
        unit = next(u for u in recovery["units"] if u["text"] == content)
        assert unit["type"] == "dialogue" and unit["speaker"] == speaker
        assert replay_unit(text, unit) == content
        # Independent raw neighbours catch dropped/reordered surrounding speech.
        source_index = text.count("\n", 0, unit["source"]["start"])
        for delta in (-1, 1):
            neighbour = text.splitlines()[source_index + delta]
            if neighbour.startswith("*") and ("：" in neighbour or ":" in neighbour):
                _, body = re.split("[：:]", neighbour, maxsplit=1)
                assert rows[index + delta]["内容"] == display_text(body)
    assert positions == sorted(positions)
    assert all(replay_unit(text, u) == u["text"] for u in recovery["units"])


@pytest.mark.parametrize("method", [
    "parse_archon_quest_page", "parse_character_quest_page", "parse_event_quest_page",
])
@pytest.mark.parametrize("colon", [":", "："])
@pytest.mark.parametrize("wrapper", ["", "span"])
def test_separators_keep_speech_boundaries_without_reclassifying_documents(method, colon, wrapper):
    speech = f"派蒙{colon}甲:乙。<br>旅行者{colon}继续。"
    if wrapper:
        speech = f"<{wrapper}>{speech}</{wrapper}>"
    text = (
        "==任务剧情==\n===场景===\n"
        f"*{speech}\n"
        f"*旁白{colon}风吹过。\n"
        f"*阅读{colon}「提示:普通文本。」\n"
        f"{{{{折叠|标题=调查日志|内容=编号{colon}甲。<br>备注{colon}乙。}}}}\n"
        f"{{{{任务描述|地点{colon}蒙德。}}}}\n"
        f"{{{{剧情选项|选项1=回答{colon}好的|剧情1=*丝柯克{colon}知道了。}}}}\n"
        f"*「附言{colon}明天返航。」\n"
        f"*那维莱特{colon}<span>提示:正文。</span>"
    )
    parser = WikiTextParser()
    raw = build_page_payload("测试", text)
    result = getattr(parser, method)(raw).to_dict()
    rows = [r for s in result["剧情对话"] for r in s["对话"]] if method == "parse_event_quest_page" else result["对话"]
    if method == "parse_event_quest_page":
        assert [(r["说话者"], r["内容"]) for r in rows if r["类型"] == "角色/NPC"] == [
            ("派蒙", "甲:乙。"), ("丝柯克", "知道了。"), ("那维莱特", "提示:正文。"),
        ]
        assert any(r["类型"] == "选项" and r["选项"] == [f"回答{colon}好的"] for r in rows)
    else:
        assert [(r["说话者"], r["内容"]) for r in rows if r["类型"] == "character"] == [
            ("派蒙", "甲:乙。"), ("丝柯克", "知道了。"), ("那维莱特", "提示:正文。"),
        ]
        assert any(r["类型"] == "option" and r["内容"] == f"回答{colon}好的" for r in rows)
    narration = [r for r in rows if r["类型"] in {"narration", "旁白"}]
    assert all(not r.get("说话者") for r in narration)
    assert [r["内容"] for r in narration] == [
        "风吹过。", f"阅读{colon}「提示:普通文本。」", f"编号{colon}甲。\n备注{colon}乙。",
        f"地点{colon}蒙德。", f"「附言{colon}明天返航。」",
    ]
    units = parser.recover_page(raw)["units"]
    assert any(u["type"] == "dialogue" and u["speaker"] == "旅行者" and u["text"] == "继续。" for u in units)
    assert all(replay_unit(text, u) == u["text"] for u in units)


def test_unknown_markup_still_has_a_diagnostic():
    raw = build_page_payload("测试", "==任务剧情==\n===场景===\n*派蒙：{{未支持模板|正文}}")
    assert any(i["rule"] == "unknown_template" for i in WikiTextParser().recover_page(raw)["issues"])


@pytest.mark.parametrize("line", [
    "*正文里的比例为3:2。", "<span>正文里的比例为3:2。</span>",
    "*时间:10:30", "*提示:请继续前进。", "*http://example.com",
])
def test_plain_ascii_colon_text_is_not_a_speaker(line):
    raw = build_page_payload("测试", f"==任务剧情==\n===场景===\n{line}")
    rows = WikiTextParser().parse_archon_quest_page(raw).dialogues
    assert len(rows) == 1 and not rows[0].speaker and rows[0].dialogue_type == "narration"
    assert rows[0].text == display_text(line.lstrip("*"))


def test_frozen_template_fragments_remain_unresolved_narration():
    path = next(FIXTURES.glob("*cd50ea0579.json"))
    provenance = json.loads((FIXTURES / "provenance.json").read_bytes())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == provenance["files"][path.name]
    rows = WikiTextParser().parse_character_quest_page(json.loads(path.read_bytes())).dialogues
    fragments = [r for r in rows if r.text.startswith((
        "|选项2=想起了「终末番伏击任务」", "|选项3=想起了「巡礼修行」"))]
    assert len(fragments) == 2
    assert all(not r.speaker and r.dialogue_type == "narration" for r in fragments)


@pytest.mark.parametrize("speaker", ["？？？", "???", "会说话的魔法灯（？）"])
def test_explicit_unknown_speaker_and_name_qualifiers_are_preserved(speaker):
    raw = build_page_payload("测试", f"==任务剧情==\n===场景===\n*{speaker}:原句。")
    rows = WikiTextParser().parse_archon_quest_page(raw).dialogues
    assert [(r.speaker, r.text, r.dialogue_type) for r in rows] == [(speaker, "原句。", "character")]
