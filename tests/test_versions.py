"""Entity release metadata must never leak from child records or examples."""
import json
from pathlib import Path

import pytest

from get_genshin_wiki.parser import WikiTextParser
from tests.helpers import build_page_payload


@pytest.mark.parametrize('method,template', [
    ('parse_character_page', '角色'), ('parse_weapon_page', '武器图鉴'),
    ('parse_artifact_set_page', '圣遗物套装'), ('parse_monster_page', '怪物信息栏'),
    ('parse_book_page', '书籍'), ('parse_food_page', '食物图鉴新'),
    ('parse_wildlife_page', '野生生物图鉴'), ('parse_quest_item_page', '任务道具'),
    ('parse_item_page', '消耗品图鉴'), ('parse_material_page', '素材图鉴'),
    ('parse_namecard_page', '名片'), ('parse_secret_item_page', '秘境副本'),
    ('parse_archon_quest_page', '任务'), ('parse_character_quest_page', '任务'),
    ('parse_event_quest_page', '任务'),
])
def test_entity_api_serializes_root_version(method, template):
    record = getattr(WikiTextParser(), method)(build_page_payload(
        '测试实体', '{{' + template + '|名称=测试实体|实装版本=月之一}}'))
    assert record.version == '月之一'
    assert record.to_dict()['所属版本'] == '月之一'
    if method == 'parse_character_page':
        stored = record.to_storage_dict()
        assert stored['所属版本'] == '月之一'
        assert '所属版本' not in stored['角色']


@pytest.mark.parametrize('method', ['parse_chronicle_page', 'parse_north_library_page'])
def test_reference_pages_have_empty_root_version(method):
    d = getattr(WikiTextParser(), method)(build_page_payload('索引', '==正文==\n内容')).to_dict()
    assert d['所属版本'] == ''


@pytest.mark.parametrize('raw,expected', [
    ('2.1', '2.1'), ('月之七', '月之七'), ('6.3', '6.3'),
    ('1.0、1.2、2.0、1.2', '1.0、1.2、2.0'),
    ('[[版本/2.1|2.1]]<!--3.0、3.1、3.2等等-->', '2.1'),
    ('<span>月之一</span>', '月之一'),
    ('{{颜色|红|5.8}}', '5.8'),
    ('{{{实装版本|}}}', ''), ('填写的内容4', ''), ('', ''),
])
def test_version_normalization(raw, expected):
    from get_genshin_wiki.versions import extract_version
    result = extract_version('实体', '{{武器图鉴|实装版本=' + raw + '}}')
    assert result.value == expected
    if expected:
        assert result.evidence


@pytest.mark.parametrize('text,expected,status', [
    ('{{武器图鉴|介绍={{图标|实装版本=5.8}}}}', '', 'missing'),
    ('{{圣遗物套装|生之花={{圣遗物部件|实装版本=5.8}}}}', '', 'missing'),
    ('{{食物图鉴新|食谱实装版本=5.8}}', '', 'missing'),
    ('{{武器图鉴|实装版本=2.1}}\n{{书籍|实装版本=5.8}}', '', 'conflict'),
    ('{{任务|所属版本=2.1|实装版本=5.8}}', '', 'conflict'),
    ('{{任务|所属版本=2.1|对白={{条件|版本=5.8}}}}', '2.1', 'resolved'),
    ('{{书籍|实装版本=1.0、1.2|卷={{书籍|实装版本=5.8}}}}', '1.0、1.2', 'resolved'),
    ('2026年11月4日更新，正文提及5.8版本。', '', 'missing'),
])
def test_subject_evidence_only(text, expected, status):
    from get_genshin_wiki.versions import extract_version
    result = extract_version('实体', text)
    assert (result.value, result.status) == (expected, status)


@pytest.mark.parametrize('title', ['模板:武器图鉴', 'Template:Weapon', '数据组指南', 'Widget:CardCanvas'])
def test_technical_pages_cannot_supply_versions(title):
    from get_genshin_wiki.versions import extract_version
    result = extract_version(title, '{{武器图鉴|实装版本=1.0}}')
    assert result.value == ''
    assert result.status == 'non_entity'


def test_book_and_artifact_children_stay_unchanged():
    p = WikiTextParser()
    book = p.parse_book_page(build_page_payload('书', '{{书籍|实装版本=1.0、1.2|卷数=1|名称1=一|内容1=正文}}')).to_dict()
    artifact = p.parse_artifact_set_page(build_page_payload('套装', '{{圣遗物套装|实装版本=1.0|生之花=花}}')).to_dict()
    assert book['所属版本'] == '1.0、1.2'
    assert artifact['所属版本'] == '1.0'
    assert all('所属版本' not in x for x in book['volumes'])
    assert '所属版本' not in artifact['生之花']


def test_real_malformed_material_has_traceable_version_fallback():
    from get_genshin_wiki.versions import extract_version
    payload = json.loads((Path(__file__).parent / 'fixtures/versions/material-query.json').read_text(encoding='utf-8'))
    title, _, text = WikiTextParser().extract_page_metadata(payload)
    result = extract_version(title, text)
    assert result.value == '月之一'
    assert result.status == 'resolved'
    evidence = result.evidence[0]
    assert evidence['method'] == 'raw_parameter'
    assert text[evidence['start']:evidence['end']].strip() == '月之一'
    assert WikiTextParser().parse_material_page(payload).to_dict()['所属版本'] == '月之一'


def test_layout_tags_allow_subject_but_not_nested_entities():
    from get_genshin_wiki.versions import extract_version
    text = '<div><onlyinclude>{{角色|实装版本=1.0|奖励={{书籍|实装版本=5.8}}}}</onlyinclude></div>{{角色}}'
    assert extract_version('角色', text).value == '1.0'
    assert extract_version('角色', '<pre>{{角色|实装版本=1.0}}</pre>').value == ''


def test_malformed_weapon_tail_and_comment_are_not_mistaken_for_missing_metadata():
    from get_genshin_wiki.versions import extract_version
    payload = json.loads((Path(__file__).parent / 'fixtures/versions/weapon-info.json').read_text(encoding='utf-8'))
    title, _, text = WikiTextParser().extract_page_metadata(payload)
    assert extract_version(title, text).value == '1.0'
    text = '{{素材图鉴|名称=甲}}\n|介绍=正文\n<!--\n|实装版本=5.8\n}}\n-->'
    assert extract_version('甲', text).value == ''


@pytest.mark.parametrize('tag', ['pre', 'nowiki', 'code', 'syntaxhighlight', 'noinclude'])
@pytest.mark.parametrize('own_version', ['', '|实装版本=1.0'])
def test_examples_after_closed_subject_cannot_supply_or_conflict_with_release(tag, own_version):
    from get_genshin_wiki.versions import extract_version
    text = '{{食物图鉴新' + own_version + '}}\n<' + tag + '>\n|实装版本=5.8\n}}\n</' + tag + '>'
    assert extract_version('实体', text).value == ('1.0' if own_version else '')


def test_plain_orphan_parameter_after_complete_subject_is_not_metadata():
    from get_genshin_wiki.versions import extract_version
    assert extract_version('实体', '{{素材图鉴}}\n|实装版本=5.8\n}}').value == ''
