"""Written text must not acquire a character identity from its colon label."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.recovery.display import replay_unit
from tests.helpers import build_page_payload

FIXTURES = Path(__file__).parent / 'fixtures/documents'
DOCUMENTS = [
    ('6a586c4ae4', '书柜上的纸张：(看起来像是以前的设计手稿，没有什么特别的地方。）'),
    ('6a586c4ae4', '本子上的备忘录：「…宣传支出十万摩拉、雇佣支出二十万摩拉、原料支出…」'),
    ('6a586c4ae4', '桌上的笔记：「…快递员…将于…上午进城，途经…」'),
    ('6a586c4ae4', '阅读：桌上散落着一些信件…'),
    ('6a586c4ae4', '「附言：把爱洛芙也叫上吧！」'),
    ('6a586c4ae4', '阅读：桌上散落着一些笔记…'),
    ('9cc68e31c8', '查看「祈月笺」：「希望月下世界的人们都能寻到自己的归宿，希望将来能和朋友们再次相见。」'),
    ('9cc68e31c8', '查看「祈月笺」：「希望老板能给我加工资…」'),
    ('9cc68e31c8', '查看「祈月笺」：「想要更快融入人类社会。」'),
    ('9cc68e31c8', '查看「祈月笺」：「希望长翎鹮不要再咬我了。」'),
    ('9cc68e31c8', '查看「祈月笺」：「希望和旅行者的旅途顺利，也希望哥伦比娅的旅途顺利。」'),
    ('9cc68e31c8', '查看「祈月笺」：「希望莉莉希小姐能注意到我…」'),
]


def payload(suffix):
    path = next(FIXTURES.glob('*__' + suffix + '.json'))
    provenance = json.loads((FIXTURES / 'provenance.json').read_text(encoding='utf-8'))
    expected = next(x['sha256'] for x in provenance if x['file'] == path.name)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    return json.loads(path.read_bytes())


@pytest.mark.parametrize('suffix,expected', DOCUMENTS)
def test_real_written_row_keeps_label_and_text_without_inventing_a_speaker(suffix, expected):
    parser = WikiTextParser()
    raw = payload(suffix)
    method = parser.parse_character_quest_page if suffix == '6a586c4ae4' else parser.parse_archon_quest_page
    record = method(raw)
    rows = [r for r in record.dialogues if r.text == expected]
    assert len(rows) == 1
    assert rows[0].dialogue_type == 'narration' and rows[0].speaker == ''
    result = parser.recover_page(raw)
    unit = next(u for u in result['units'] if u['text'] == expected)
    assert unit['type'] == 'narration' and unit['speaker'] is None
    assert unit['speaker_status'] == 'not_applicable'
    assert replay_unit(parser.extract_page_metadata(raw)[2], unit) == expected
    if expected.startswith('「附言'):
        assert unit['branch_path'][-1]['label'] == '娜维娅寄来的信'
    if suffix == '9cc68e31c8':
        assert unit['branch_path'][-1]['label'] == '额外对话（查看「祈月笺」）'


def test_real_prayer_authorship_stays_separate_and_adjacent_character_still_speaks():
    parser = WikiTextParser()
    raw = payload('9cc68e31c8')
    result = parser.recover_page(raw)
    notes = [u['text'] for u in result['units'] if u['type'] == 'annotation']
    for note in ['———雅珂达', '———杜林', '———派蒙', '——坎托尔', '旁边有他们的对话']:
        assert notes.count(note) == 1
    record = parser.parse_archon_quest_page(raw)
    assert any(r.speaker == '菈乌玛' and r.text == '希望大家的愿望，都得以实现…' and r.dialogue_type == 'character' for r in record.dialogues)
    assert [r.text for r in record.dialogues if r.dialogue_type == 'option' and r.task_flow == '祈愿之笺'][-7:] == [
        '继续查看', '继续查看', '继续查看', '继续查看', '继续查看', '离开', '要来点祈月糖吗？']
    text = parser.extract_page_metadata(raw)[2]
    assert all(replay_unit(text, u) == u['text'] for u in result['units'])


@pytest.mark.parametrize('method', ['parse_archon_quest_page', 'parse_character_quest_page', 'parse_event_quest_page'])
def test_mixed_fold_keeps_document_choice_and_live_speech_in_all_adapters(method):
    text = ('==任务剧情==\n===场景===\n{{折叠|标题=额外对话|内容=\n'
            '*查看「航海日志」：今日起航。{{黑幕|署名}}<br>*「女士」：我们走。\n'
            '{{剧情选项|选项1=打开下一页|剧情1=「附言：明天返航。」\n*记录员：这是一段发言。}}\n'
            '}}\n*派蒙：看完了。')
    parser = WikiTextParser()
    raw = build_page_payload('无关的新页面', text)
    record = getattr(parser, method)(raw)
    if method == 'parse_event_quest_page':
        rows = [r for s in record.dialogue for r in s.dialogue]
        actual = [(r.speaker, r.content) for r in rows if r.type != '选项']
        assert [r.options for r in rows if r.type == '选项'] == [['打开下一页']]
        assert rows[0].type == '旁白'
    else:
        rows = record.dialogues
        actual = [(r.speaker, r.text) for r in rows if r.dialogue_type != 'option']
        assert [r.text for r in rows if r.dialogue_type == 'option'] == ['打开下一页']
        assert rows[0].dialogue_type == 'narration'
    assert actual == [('', '查看「航海日志」：今日起航。'), ('「女士」', '我们走。'),
                      ('', '「附言：明天返航。」'), ('记录员', '这是一段发言。'), ('派蒙', '看完了。')]
    result = parser.recover_page(raw)
    assert [u['text'] for u in result['units'] if u['type'] == 'annotation'] == ['署名']
    assert all(replay_unit(text, u) == u['text'] for u in result['units'])


@pytest.mark.parametrize('label', ['阅读', '查阅', '翻阅《旅途见闻》', '桌上的便条', '墙上的告示'])
def test_reading_actions_and_located_documents_are_narration(label):
    raw = build_page_payload('测试', f'==任务剧情==\n===场景===\n*{label}：记录内容。\n*派蒙：继续。')
    rows = WikiTextParser().parse_archon_quest_page(raw).dialogues
    assert [(r.speaker, r.text) for r in rows] == [('', f'{label}：记录内容。'), ('派蒙', '继续。')]
    assert rows[0].dialogue_type == 'narration'


@pytest.mark.parametrize('speaker', ['「女士」', '「公子」', '阅读者', '记录员', '信使', '会说话的魔法灯（？）'])
def test_character_names_are_not_reclassified_by_document_word_substrings(speaker):
    raw = build_page_payload('测试', f'==任务剧情==\n===场景===\n*{speaker}：我要读这封信。')
    rows = WikiTextParser().parse_archon_quest_page(raw).dialogues
    assert len(rows) == 1 and rows[0].dialogue_type == 'character'
    assert rows[0].speaker == speaker and rows[0].text == '我要读这封信。'


@pytest.mark.parametrize('label', ['阅读', '桌上的便条'])
def test_document_with_wholly_hidden_body_keeps_text_instead_of_detaching_it(label):
    text = f'==任务剧情==\n===场景===\n*{label}：{{{{黑幕|隐藏正文}}}}'
    parser = WikiTextParser()
    raw = build_page_payload('测试', text)
    rows = parser.parse_archon_quest_page(raw).dialogues
    assert [(r.speaker, r.text, r.dialogue_type) for r in rows] == [('', f'{label}：隐藏正文', 'narration')]
    result = parser.recover_page(raw)
    assert not any(u['type'] == 'annotation' for u in result['units'])
    assert any(i['rule'] == 'ambiguous_blackout_content' for i in result['issues'])
    assert all(replay_unit(text, u) == u['text'] for u in result['units'])


@pytest.mark.parametrize('speaker,content', [('「公子', '解散！'), ('「罗兰', '但你比我更清楚。'), ('「巫婆', '不要寻找我的下落。'), ('「仆人', '你确定要留下来吗？'), ('「公子', '这里的「信件」很重要。')])
def test_incomplete_source_quotes_do_not_turn_live_speech_into_a_document(speaker, content):
    text = f'==任务剧情==\n===场景===\n*{speaker}：{content}'
    parser = WikiTextParser()
    raw = build_page_payload('测试', text)
    rows = parser.parse_archon_quest_page(raw).dialogues
    assert [(r.speaker, r.text, r.dialogue_type) for r in rows] == [(speaker, content, 'character')]
    result = parser.recover_page(raw)
    spoken = next(u for u in result['units'] if u['type'] == 'dialogue')
    assert spoken['speaker_status'] == 'unresolved'
    assert any(i['rule'] == 'unbalanced_speaker_quote' for i in result['issues'])
