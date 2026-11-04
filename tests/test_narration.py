"""Non-speaker story text retains its content, identity and uncertainty."""
import pytest

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.recovery.display import replay_unit
from tests.helpers import build_page_payload
from tests.test_document_dialogue import payload


@pytest.mark.parametrize('suffix,numbers', [('1d60ad4965', [142, 143, 144, 145]), ('9f8aeeb802', [252, 253])])
def test_real_announcements_are_documents_with_shared_identity(suffix, numbers):
    parser = WikiTextParser()
    raw = payload(suffix)
    text = parser.extract_page_metadata(raw)[2]
    expected = [text.splitlines()[n - 1].strip().removeprefix('|内容=').removeprefix('*').removesuffix('}}') for n in numbers]
    result = parser.recover_page(raw)
    docs = [u for u in result['units'] if u['text'] in expected]
    assert [u['text'] for u in docs] == expected
    assert all(u['type'] == 'narration' and u['speaker'] is None and u['speaker_status'] == 'not_applicable' for u in docs)
    assert all(u['narration_kind'] == 'document' for u in docs)
    assert len({u['document_id'] for u in docs}) == 1
    assert all(replay_unit(text, u) == u['text'] for u in result['units'])
    rows = parser.parse_character_quest_page(raw).to_dict()['对话']
    for value in expected:
        row = next(r for r in rows if r['内容'] == value)
        assert row['说话者'] == '' and row['类型'] == 'narration'
        assert set(row) == {'说话者', '内容', '类型', '所属任务流程'}
    if suffix == '1d60ad4965':
        for name in ['小百合', '真理']:
            assert any(u['type'] == 'dialogue' and u['speaker'] == name for u in result['units'])


@pytest.mark.parametrize('method', ['parse_archon_quest_page', 'parse_character_quest_page', 'parse_event_quest_page'])
def test_narration_subtypes_and_legacy_compatibility(method):
    text = ('==任务剧情==\n===调查现场===\n'
            '*旁白：门缓缓打开。\n'
            '*阅读：桌上散落着一些信件…\n'
            '*查看「祈月笺」：「愿旅途顺利。」{{黑幕|署名}}\n'
            '{{折叠|标题=额外对话（公告板）|内容=\n'
            '*市民通告：保持警惕。\n*市民通告：欢迎来访。\n'
            '*派蒙：公告写了什么？\n}}\n'
            '无法确定性质的原文。\n::编者补充。')
    parser = WikiTextParser()
    raw = build_page_payload('测试', text)
    result = parser.recover_page(raw)
    units = {u['text']: u for u in result['units']}
    for value, subtype in [('门缓缓打开。', 'narrative'), ('阅读：桌上散落着一些信件…', 'interface'),
                           ('查看「祈月笺」：「愿旅途顺利。」', 'document'), ('市民通告：保持警惕。', 'document'),
                           ('无法确定性质的原文。', 'unknown'), ('编者补充。', 'unknown')]:
        unit = units[value]
        assert unit['narration_kind'] == subtype
        assert unit['speaker'] is None and unit['speaker_status'] == 'not_applicable'
    assert units['无法确定性质的原文。']['source_kind'] == 'unknown'
    assert units['编者补充。']['source_kind'] == 'wiki_editorial'
    assert any(i['rule'] == 'unclassified_narration' for i in result['issues'])
    assert units['公告写了什么？']['speaker'] == '派蒙'
    assert 'narration_kind' not in units['公告写了什么？']
    assert [u['text'] for u in result['units'] if u['type'] == 'annotation'] == ['署名']
    record = getattr(parser, method)(raw).to_dict()
    rows = [r for s in record['剧情对话'] for r in s['对话']] if method == 'parse_event_quest_page' else record['对话']
    expected = '旁白' if method == 'parse_event_quest_page' else 'narration'
    assert next(r for r in rows if r['内容'] == '市民通告：保持警惕。')['类型'] == expected
    assert all('narration_kind' not in r and 'document_id' not in r for r in rows)
    assert all(replay_unit(text, u) == u['text'] for u in result['units'])


def test_document_groups_do_not_cross_speech_choices_or_folds():
    text = ('==任务剧情==\n===场景===\n'
            '{{折叠|标题=日记|内容=第一段。\n第二段。}}\n'
            '*桌上的便条：甲。\n*桌上的便条：乙。\n*派蒙：继续。\n*桌上的便条：丙。\n'
            '{{剧情选项|选项1=左|剧情1=*桌上的便条：左。|选项2=右|剧情2=*桌上的便条：右。}}\n'
            '{{折叠|标题=日记|内容=第三段。}}')
    result = WikiTextParser().recover_page(build_page_payload('测试', text))
    docs = {u['text']: u for u in result['units'] if u['type'] == 'narration'}
    assert all(u['narration_kind'] == 'document' for u in docs.values())
    assert docs['第一段。']['document_id'] == docs['第二段。']['document_id']
    assert docs['桌上的便条：甲。']['document_id'] == docs['桌上的便条：乙。']['document_id']
    keys = ['第一段。', '桌上的便条：甲。', '桌上的便条：丙。', '桌上的便条：左。', '桌上的便条：右。', '第三段。']
    assert len({docs[k]['document_id'] for k in keys}) == len(keys)


def test_announcement_context_does_not_grant_identity_or_capture_live_speech():
    text = ('==任务剧情==\n===场景===\n{{折叠|标题=额外对话（公告板前）|内容=\n'
            '*派蒙：我读了市民通告。\n*公告员：下一位。\n*市民通告：请注意。\n}}\n'
            '*旁白：风停了。\n*记录员：我来记录。')
    units = WikiTextParser().recover_page(build_page_payload('测试', text))['units']
    assert [(u['speaker'], u['text']) for u in units if u['type'] == 'dialogue'] == [
        ('派蒙', '我读了市民通告。'), ('公告员', '下一位。'), ('记录员', '我来记录。')]
    assert next(u for u in units if u['text'] == '风停了。')['speaker'] is None


def test_nested_document_containers_keep_document_evidence():
    text = ('==任务剧情==\n===场景===\n{{折叠|标题=日记|内容=第一页。\n'
            '{{折叠|标题=第二页|内容=第二页正文。}}\n末段。}}')
    result = WikiTextParser().recover_page(build_page_payload('测试', text))
    assert [u['text'] for u in result['units']] == ['第一页。', '第二页正文。', '末段。']
    assert all(u['narration_kind'] == 'document' for u in result['units'])


@pytest.mark.parametrize('row', ['*旁白：风停了。{{黑幕|编者补充}}', '{{折叠|标题=日记|内容=风停了。{{黑幕|编者补充}}}}'])
def test_narration_editorial_notes_stay_separate(row):
    text = '==任务剧情==\n===场景===\n' + row
    parser = WikiTextParser()
    result = parser.recover_page(build_page_payload('测试', text))
    assert [u['text'] for u in result['units'] if u['type'] == 'narration'] == ['风停了。']
    assert [u['text'] for u in result['units'] if u['type'] == 'annotation'] == ['编者补充']
    assert all(replay_unit(text, u) == u['text'] for u in result['units'])


@pytest.mark.parametrize('body,subtype', [('你翻开了这张纸，准备阅读。', 'interface'), ('「愿旅途顺利。」', 'document'), ('内容性质不明。', 'unknown')])
def test_named_reading_action_needs_body_evidence(body, subtype):
    raw = build_page_payload('测试', '==任务剧情==\n===场景===\n*查看「祈月笺」：' + body)
    unit = WikiTextParser().recover_page(raw)['units'][0]
    assert unit['narration_kind'] == subtype


def test_document_key_with_wholly_hidden_body_stays_ambiguous():
    raw = build_page_payload('测试', '==任务剧情==\n===场景===\n{{折叠|标题=日记|内容=*正文：{{黑幕|隐藏正文}}}}')
    result = WikiTextParser().recover_page(raw)
    assert [u['text'] for u in result['units'] if u['type'] == 'narration'] == ['正文：隐藏正文']
    assert not any(u['type'] == 'annotation' for u in result['units'])
    assert any(i['rule'] == 'ambiguous_blackout_content' for i in result['issues'])


def test_option_label_annotation_can_validate_its_actual_label_source():
    from get_genshin_wiki.recovery.source import SourcePage
    from tools.recover_snapshot import validate_unit
    raw = build_page_payload('测试', '==任务剧情==\n===场景===\n{{剧情选项|选项1=阅读{{黑幕|编者补充}}|剧情1=*派蒙：继续。}}')
    source = SourcePage.from_payload(raw, 'pages/test.json')
    result = WikiTextParser().recover_page(raw, raw_file=source.raw_file)
    assert any(u['type'] == 'annotation' for u in result['units'])
    for unit in result['units']:
        validate_unit(unit, {source.raw_file: source})


def test_explicit_narrator_in_dialogue_template_has_no_character_identity():
    text = '==任务剧情==\n===场景===\n{{人物对话|角色=旁白|内容=风停了。}}'
    raw = build_page_payload('测试', text)
    unit = WikiTextParser().recover_page(raw)['units'][0]
    assert unit['type'] == 'narration' and unit['speaker'] is None
    assert unit['narration_kind'] == 'narrative'
    span = unit['narration_label_source']
    assert text[span['start']:span['end']] == '旁白'
