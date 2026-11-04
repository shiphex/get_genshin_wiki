"""Offline, read-only audit of frozen inputs and current entity projections.

Run from any directory:
  .venv/Scripts/python.exe doc/reports/non_story_sample_audit_2026-10-31/audit.py
Only this report directory is written. Findings are observations, not fix tests.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
import platform
import importlib.metadata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore

OUT = Path(__file__).resolve().parent
SAMPLES = {
    'characters': ['七七', '钟离', '芙宁娜', '旅行者', '玛薇卡', '丝柯克'],
    'weapons': ['天空之刃', '铁蜂刺', '「渔获」', '「究极霸王超级魔剑」', '原木刀', '冷刃'],
    'materials': ['史莱姆凝液', '璀璨原钻碎屑', '慕风蘑菇', '「自由」的教导', '北陆单手剑原胚', '清心'],
    'artifacts': ['角斗士的终幕礼', '昔日宗室之仪', '祭火之人'],
    'monsters': ['丘丘人', '遗迹守卫', '若陀龙王'],
    'foods': ['甜甜花酿鸡', '仙跳墙', '蒙德土豆饼'],
    'items': ['浓缩树脂', '「四方八方之网」', '参量质变仪'],
    'wildlife': ['生物志：甜甜花鳉', '生物志：雪狐', 'Widget:CardCanvas'],
    'secret-items': ['塞西莉亚苗圃', '仲夏庭园', '太山府'],
    'namecards': ['七七·冷藏', '成就·七圣'],
}
METHODS = {
    'weapons': 'parse_weapon_page', 'materials': 'parse_material_page',
    'artifacts': 'parse_artifact_set_page', 'monsters': 'parse_monster_page',
    'foods': 'parse_food_page', 'items': 'parse_item_page',
    'wildlife': 'parse_wildlife_page', 'secret-items': 'parse_secret_item_page',
    'namecards': 'parse_namecard_page',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def differences(a, b, path=''):
    if type(a) is not type(b):
        return [path]
    if isinstance(a, dict):
        return [p for k in sorted(a.keys() | b.keys()) for p in (
            differences(a[k], b[k], f'{path}/{k}') if k in a and k in b else [f'{path}/{k}'])]
    if isinstance(a, list):
        return [] if a == b else [path]
    return [] if a == b else [path]


def main():
    parser = WikiTextParser()
    store = JsonFileStore(ROOT / 'data')
    loaded = {}
    observed_files = {}
    manifest = []
    archive_path = ROOT.parent / 'genshin_wiki_data_20260605.zip'
    archive = zipfile.ZipFile(archive_path) if archive_path.exists() else None
    archive_members = set(archive.namelist()) if archive else set()
    # This ZIP has legacy-encoded Chinese names. Stable SHA1 filename suffixes
    # identify members without guessing a character encoding.
    archive_index = {}
    for member in archive_members:
        suffix = re.search(r'__([0-9a-f]{10})\.json$', member)
        if suffix:
            family = 'pages' if member.startswith('pages/') else '/'.join(member.split('/')[:2])
            key = family, suffix.group(1)
            assert key not in archive_index, key
            archive_index[key] = member

    def read(path):
        raw = path.read_bytes()
        observed_files[path] = digest(raw)
        return json.loads(raw)

    def load(ns, title):
        key = ns, title
        if key in loaded:
            return loaded[key]
        filename = store.build_filename(title)
        raw_path = ROOT / 'data/pages' / filename
        saved_path = ROOT / 'data/parsed' / ns / filename
        payload = read(raw_path)
        actual_title, page_id, w = parser.extract_page_metadata(payload)
        assert actual_title == title
        page = next(iter(payload['query']['pages'].values()))
        saved = read(saved_path)
        voice_path = ROOT / 'data/pages' / store.build_filename(title + '语音')
        voice = None
        if ns == 'characters' and voice_path.exists():
            voice = read(voice_path)
        if ns == 'characters':
            record = parser.parse_character_page(payload, voice_payload=voice)
            current = record.to_storage_dict()
        else:
            record = getattr(parser, METHODS[ns])(payload)
            current = record.to_dict()
        suffix = filename.rsplit('__', 1)[1].removesuffix('.json')
        member = archive_index.get(('pages', suffix))
        saved_member = archive_index.get(('parsed/' + ns, suffix))
        archive_equal = (digest(archive.read(member)) == observed_files[raw_path]
                         if archive and member else None)
        saved_archive_equal = (digest(archive.read(saved_member)) == observed_files[saved_path]
                               if archive and saved_member else None)
        row = {
            'namespace': ns, 'title': title, 'page_id': page_id, 'source_ns': page.get('ns'),
            'raw_file': raw_path.relative_to(ROOT).as_posix(),
            'raw_sha256': observed_files[raw_path], 'raw_equals_0605_zip': archive_equal,
            'saved_file': saved_path.relative_to(ROOT).as_posix(),
            'saved_sha256': observed_files[saved_path],
            'saved_equals_0605_zip': saved_archive_equal,
            'saved_equals_current': saved == current,
            'changed_paths': differences(saved, current),
            'voice_file': voice_path.relative_to(ROOT).as_posix() if voice else None,
        }
        manifest.append(row)
        dump(OUT / 'current' / ns / filename, current)
        loaded[key] = {'manifest': row, 'w': w, 'saved': saved, 'current': current,
                       'templates': parser.parse_templates(w), 'record': record}
        return loaded[key]

    for ns, titles in SAMPLES.items():
        for title in titles:
            load(ns, title)

    findings = []

    def evidence(ns, title, needle, field_path, *, value=None):
        obj = load(ns, title)
        offset = obj['w'].find(needle)
        assert offset >= 0, (title, needle)
        def at(data):
            for key in field_path:
                data = data[key]
            return data
        return {
            'namespace': ns, 'title': title, 'raw_file': obj['manifest']['raw_file'],
            'raw_line': obj['w'].count('\n', 0, offset) + 1,
            'wikitext_start': offset, 'wikitext_end': offset + len(needle),
            'raw_exact': needle, 'output_path': '/'.join(field_path),
            'saved': at(obj['saved']), 'current': at(obj['current']),
            **({'expected_content': value} if value is not None else {}),
        }

    # Independent literal expectations from actual raw pages.
    char_fields = []
    notes = []
    for title in SAMPLES['characters']:
        obj = loaded['characters', title]
        for params in obj['templates'].get('角色/信息', []):
            for key in ('归属', '职业', '衣装名称', '昵称/外号'):
                raw = params.get(key, '')
                if raw and not obj['current']['角色'][key]:
                    char_fields.append(evidence('characters', title, raw, ['角色', key]))
        for params in obj['templates'].get('角色/故事', []):
            raw = params.get('冒险笔记', '')
            if raw and not obj['current']['冒险笔记']:
                notes.append(evidence('characters', title, raw, ['冒险笔记']))
    assert len({r['title'] for r in char_fields}) == 5
    assert {r['title'] for r in notes} == {'七七', '钟离'}
    findings.append({'id': 'F1', 'kind': 'field_omission', 'label': '角色信息子模板未合并', 'evidence': char_fields})
    findings.append({'id': 'F2', 'kind': 'field_omission', 'label': '空冒险笔记1覆盖非空冒险笔记', 'evidence': notes})

    color_cases = [
        evidence('items', '参量质变仪', '{{颜色|蓝|元素攻击}}', ['用途'], value='元素攻击'),
        evidence('items', '浓缩树脂', '备注：只能代替原本需要', ['用途'], value='持有上限为5个'),
    ]
    assert all(x['expected_content'] not in x['current'] for x in color_cases)
    findings.append({'id': 'F3', 'kind': 'visible_template_content_loss', 'label': '道具用途中的颜色模板被删除', 'evidence': color_cases})

    comment = evidence('weapons', '「究极霸王超级魔剑」', '<!--单手剑、双手剑、长柄武器、法器、弓 -->', ['类型'])
    intro_comment = evidence('weapons', '「究极霸王超级魔剑」', '<!--对武器的简要介绍，可在“角色”面板->“武器”标签查看 -->', ['介绍'])
    assert '<!--' in comment['current'] and '<!--' in intro_comment['current']
    findings.append({'id': 'F4', 'kind': 'editorial_noise', 'label': '武器类型与介绍混入编辑注释', 'evidence': [comment, intro_comment]})

    artifact_cases = [
        evidence('artifacts', '昔日宗室之仪', '合成台任意三件五星圣遗物合成一件。', ['获取方式'], value='合成台'),
        evidence('artifacts', '昔日宗室之仪', '世界任务：靖世九柱', ['获取方式'], value='靖世九柱'),
        evidence('artifacts', '祭火之人', '[[爆炎树]]、[[无相之火]]、[[古岩龙蜥]]掉落', ['获取方式']),
    ]
    assert all(x['expected_content'] not in x['current'] for x in artifact_cases[:2])
    assert '[[' in artifact_cases[2]['current']
    findings.append({'id': 'F5', 'kind': 'partial_source_and_markup_noise', 'label': '圣遗物获取方式过早返回并残留链接标记', 'evidence': artifact_cases})

    # Query expressions cannot be treated as resolved facts. Cross-check one
    # missing relationship against a separate, frozen character source page.
    support_title = '甘雨'
    support_path = ROOT / 'data/pages' / store.build_filename(support_title)
    support_payload = read(support_path)
    _, _, support_w = parser.extract_page_metadata(support_payload)
    support_templates = parser.parse_templates(support_w)
    assert any(x.get('突破特产材料') == '清心' for x in support_templates.get('角色/突破简', []))
    material_cases = []
    for title in ('慕风蘑菇', '清心', '「自由」的教导', '北陆单手剑原胚'):
        obj = loaded['materials', title]
        raw_usage = parser._extract_param_from_wikitext(obj['w'], ('用处',))
        row = evidence('materials', title, raw_usage, ['用途'])
        assert '#ask' not in row['saved'] and '#ask' in row['current']
        material_cases.append(row)
    assert '甘雨' not in loaded['materials', '清心']['current']['用途']
    findings.append({'id': 'F6', 'kind': 'unresolved_dependency_and_query_noise', 'label': '材料关系未展开；现存结果丢关系，重跑结果泄露查询源码',
                     'evidence': material_cases,
                     'support': {'title': support_title, 'raw_file': support_path.relative_to(ROOT).as_posix(),
                                 'raw_sha256': observed_files[support_path],
                                 'raw_exact': '突破特产材料=清心',
                                 'actual_parameter': next(x['突破特产材料'] for x in support_templates['角色/突破简'])}})

    widget = loaded['wildlife', 'Widget:CardCanvas']
    assert widget['current']['名称'] == '松鼠'
    assert widget['manifest']['source_ns'] != 0
    findings.append({'id': 'F7', 'kind': 'non_entity_page', 'label': '技术页面示例进入实体目录', 'evidence': [
        evidence('wildlife', 'Widget:CardCanvas', '|名称=松鼠', ['名称'])]})

    # Isolated hypothesis checks. Only copied dictionaries/helper inputs change;
    # no source file or production parser is edited.
    qiqi = loaded['characters', '七七']
    info = qiqi['templates']['角色/信息'][0]
    assert parser._extract_text_field(info, ('职业',)) == '不卜庐采药人'
    without_empty_alias = {name: [dict(params) for params in entries]
                           for name, entries in qiqi['templates'].items()}
    for params in without_empty_alias['角色/故事']:
        params.pop('冒险笔记1', None)
    recovered_notes = parser._extract_adventure_notes(without_empty_alias)
    assert len(recovered_notes) == 1
    assert recovered_notes[0].title == '不死之身的居家旅行实用宝典'
    assert '七七随身携带的物品' in recovered_notes[0].content
    assert parser._normalize_plain_text('{{颜色|蓝|元素攻击}}') == ''
    assert parser._clean_field_value('{{颜色|蓝|元素攻击}}') == '元素攻击'
    noble = dict(loaded['artifacts', '昔日宗室之仪']['templates']['圣遗物套装'][0])
    noble.pop('获取途径')
    expanded_obtain = parser._parse_artifact_obtaining_method(noble)
    assert '合成台' in expanded_obtain and '靖世九柱' in expanded_obtain
    root_cause_probes = {
        'F1_info_subtemplate_contains_extractable_profession': True,
        'F2_removing_empty_numbered_alias_restores_note': True,
        'F3_normalize_plain_loses_color_clean_field_preserves_it': True,
        'F5_removing_short_source_exposes_other_methods': True,
    }

    # Intentional limited schemas, reported separately from implementation bugs.
    coverage = []
    for ns, title, template, keys in [
        ('weapons', '天空之刃', '武器图鉴', ['稀有度', '初始攻击力', '90突破前攻击力', '技能名称', '技能介绍']),
        ('artifacts', '角斗士的终幕礼', '圣遗物套装', ['两件套效果', '四件套效果']),
        ('foods', '甜甜花酿鸡', '食物图鉴新', ['效果说明', '完美效果说明', '失败效果说明']),
        ('monsters', '遗迹守卫', '怪物信息栏', ['物抗', '火抗']),
    ]:
        obj = loaded[ns, title]
        raw = obj['templates'][template][0]
        coverage.append({'namespace': ns, 'title': title, 'raw_fields': {k: raw[k] for k in keys},
                         'persisted_keys': list(obj['current']), 'classification': 'schema_scope_not_parser_regression'})

    # Census of projections only: these are mechanical signals, not semantic
    # error rates. No all-library completeness claim is made.
    census = {}
    for ns in SAMPLES:
        files = sorted((ROOT / 'data/parsed' / ns).glob('*.json'))
        signals = Counter()
        non_entities = []
        for f in files:
            j = read(f)
            serialized = json.dumps(j, ensure_ascii=False)
            if '<!--' in serialized:
                signals['contains_html_comment'] += 1
            if '[[' in serialized or '{{' in serialized:
                signals['contains_wiki_markup'] += 1
            if ns == 'characters':
                for field in ('归属', '职业', '昵称/外号'):
                    if not j['角色'].get(field):
                        signals['empty_' + field] += 1
            if ns == 'wildlife':
                rawfile = ROOT / 'data/pages' / f.name
                if rawfile.exists():
                    raw = read(rawfile)
                    page = next(iter(raw.get('query', {}).get('pages', {}).values()), {})
                    title = page.get('title', '')
                    if page.get('ns', 0) != 0 or title == '数据组指南':
                        non_entities.append({'file': f.relative_to(ROOT).as_posix(), 'source_title': title,
                                             'source_ns': page.get('ns'), 'output_name': j.get('名称')})
        census[ns] = {'files': len(files), 'signals': dict(signals), 'non_entity_candidates': non_entities}

    # Positive controls: concrete supported fields that survive correctly.
    controls = [
        ('weapons', '铁蜂刺', ['锻造材料'], '北陆单手剑原胚*1、水晶块*50、白铁块*50'),
        ('weapons', '「渔获」', ['精炼材料'], '赤穗酒枡'),
        ('materials', '璀璨原钻碎屑', ['用途'], '旅行者（20级突破）'),
        ('wildlife', '生物志：甜甜花鳉', ['钓鱼信息', '钓鱼鱼饵'], '果酿饵'),
        ('wildlife', '生物志：雪狐', ['能否捕捉'], '能'),
        ('monsters', '丘丘人', ['drop_materials'], ['破损的面具', '污秽的面具', '不祥的面具']),
        ('namecards', '成就·七圣', ['获取方式'], '达成七圣召唤下所有成就时获取。'),
    ]
    for ns, title, path, expected in controls:
        value = loaded[ns, title]['current']
        for key in path:
            value = value[key]
        assert value == expected, (title, path, value)

    for path, original in observed_files.items():
        assert digest(path.read_bytes()) == original, f'Input changed: {path}'
    if archive:
        archive.close()
    summary = {
        'snapshot': 'genshin_wiki_data_20260605.zip', 'sample_design': 'purposive_structural_variants_not_random',
        'sample_count': len(manifest), 'namespaces': {k: len(v) for k, v in SAMPLES.items()},
        'raw_archive_matches': sum(r['raw_equals_0605_zip'] is True for r in manifest),
        'saved_archive_matches': sum(r['saved_equals_0605_zip'] is True for r in manifest),
        'python': platform.python_version(),
        'mwparserfromhell': importlib.metadata.version('mwparserfromhell'),
        'saved_matches_current': sum(r['saved_equals_current'] for r in manifest),
        'changed_samples': [{'namespace': r['namespace'], 'title': r['title'], 'changed_paths': r['changed_paths']} for r in manifest if not r['saved_equals_current']],
        'finding_ids': [r['id'] for r in findings], 'positive_controls_passed': len(controls),
        'checked_input_files_unchanged': len(observed_files),
        'source_hashes': {f: digest((ROOT/f).read_bytes()) for f in ['get_genshin_wiki/parser.py', 'get_genshin_wiki/models.py', 'get_genshin_wiki/recovery/display.py']},
    }
    dump(OUT / 'manifest.json', manifest)
    dump(OUT / 'findings.json', findings)
    dump(OUT / 'schema_scope.json', coverage)
    dump(OUT / 'census.json', census)
    dump(OUT / 'root_cause_probes.json', root_cause_probes)
    dump(OUT / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('CENSUS', json.dumps(census, ensure_ascii=False))


if __name__ == '__main__':
    main()
