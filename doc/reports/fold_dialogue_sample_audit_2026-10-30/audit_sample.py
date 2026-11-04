"""Read-only, offline, twelve-page audit. Never writes input or production JSON.

The lexical inventory below does not import the production extractor's rules.
Coverage is evidence of source accounting, not a semantic completeness score.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch
from contextlib import ExitStack
import zipfile

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
sys.path.insert(0, str(ROOT))
import mwparserfromhell as mw
from mwparserfromhell.nodes import Text, Template, Tag, Heading, Wikilink, Comment
from get_genshin_wiki.parser import WikiTextParser

SAMPLES = {
    'archon-quests': ['尾声的尾声', '黑蛇骑士的荣光', '定罪公文', '深渊法师'],
    'character-quests': ['占星术与五十年之约', '是荒泷生命摇滚虹色大巡回', '知己知彼定良策', '跨越时间的托付'],
    'event-quests': ['荷叶与森林的答案', '开火！玩具战争', '飞漆溅彩', '荣誉骑士的调饮心得'],
}
OUT = ROOT / '.uv-cache/independent-sample-audit'
HAN = re.compile(r'[\u3400-\u9fff]')


def payload_text(payload):
    page = next(iter(payload['query']['pages'].values()))
    revision = page.get('revisions', [{}])[0]
    return page['title'], revision.get('slots', {}).get('main', {}).get('*', revision.get('*', ''))


def inventory(text):
    leaves, folds = [], []

    def walk(raw, base, story=False, context=(), role='body'):
        cursor = base
        active, level = story, None
        for node in mw.parse(raw).nodes:
            value = str(node)
            if isinstance(node, Heading):
                title = str(node.title).strip()
                if level is not None and node.level <= level:
                    active, level = story, None
                # Deliberately broader than the production heading allowlist.
                # Review whether each such heading really denotes story text.
                if re.search(r'剧情|对话|任务过程|任务内容', title):
                    active, level = True, node.level
            elif isinstance(node, Text):
                if active and HAN.search(value):
                    leaves.append({'start': cursor, 'end': cursor + len(value), 'raw': value,
                                   'context': list(context), 'role': role})
            elif isinstance(node, Template):
                name = str(node.name).strip()
                params = []
                pos = cursor + 2 + len(str(node.name))
                for param in node.params:
                    start = pos + 1 + (len(str(param.name)) + 1 if param.showkey else 0)
                    params.append((str(param.name).strip(), str(param.value), start))
                    pos += 1 + len(str(param))
                if name in {'折叠', '折叠框'}:
                    selected = next((p for key in ('内容', '2') for p in params if p[0] == key), None)
                    folds.append({'start': cursor, 'end': cursor + len(value), 'in_story': active,
                                  'raw': value, 'has_content': selected is not None})
                    if selected:
                        walk(selected[1], selected[2], active, context + (name,), role)
                elif name == '剧情':
                    for key, val, start in params:
                        if re.fullmatch(r'内容\d+(?:\.\d+)*', key):
                            walk(val, start, True, context + (name + '/' + key,), role)
                elif name in {'任务', '任务信息'}:
                    for key, val, start in params:
                        if key in {'剧情', '任务剧情', '对话', '任务对话'}:
                            walk(val, start, True, context + (name + '/' + key,), role)
                elif active:
                    chosen = {'颜色': ('描述', '内容', '2', '3'), '注音': ('1',),
                              '黑幕': ('1',), '任务描述': ('1', '描述')}.get(name)
                    selected = next((p for key in chosen or () for p in params if p[0] == key), None)
                    if selected:
                        child_role = 'editorial' if name == '黑幕' else 'synopsis' if name == '任务描述' else role
                        walk(selected[1], selected[2], True, context + (name,), child_role)
                    elif name in {'剧情选项', '选项'}:
                        for key, val, start in params:
                            if re.fullmatch(r'(选项|剧情|选择)\d+', key):
                                walk(val, start, True, context + (name + '/' + key,), role)
                    elif '人物对话' in name:
                        for key, val, start in params:
                            if key in {'角色', '内容', '1', '2', '3'}:
                                walk(val, start, True, context + (name + '/' + key,), role)
                    else:
                        for key, val, start in params:
                            walk(val, start, True, context + ('unclassified:' + name + '/' + key,), 'uncertain')
            elif isinstance(node, Tag):
                name = str(node.tag).lower()
                if not node.self_closing and name not in {'ref', 'references', 'style', 'script', 'noinclude'}:
                    contents = str(node.contents)
                    # Locate the opening tag exactly; wiki list/bold markup is separate.
                    if node.wiki_markup:
                        opening = node.wiki_markup + ''.join(str(a) for a in node.attributes) + (node.padding or '') + (node.wiki_style_separator or '')
                    else:
                        opening = ('</' if node.invalid else '<') + str(node.tag) + ''.join(str(a) for a in node.attributes) + node.padding + '>'
                    assert value[len(opening):len(opening) + len(contents)] == contents
                    walk(contents, cursor + len(opening), active, context + ('tag:' + name,), role)
            elif isinstance(node, Wikilink):
                title = str(node.title)
                if not re.match(r'^(文件|File|Image|分类|Category):', title, re.I):
                    label = str(node.text) if node.text is not None else title
                    start = cursor + (3 + len(title) if node.text is not None else 2)
                    walk(label, start, active, context + ('link',), role)
            elif isinstance(node, Comment):
                pass
            cursor += len(value)

    walk(text, 0)
    return leaves, folds


def forbidden(*args, **kwargs):
    raise RuntimeError('network forbidden in sample audit')


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    archive = ROOT.parent / 'genshin_wiki_data_20260605.zip'
    report = []
    with ExitStack() as stack:
        for target in ('socket.socket.connect', 'socket.create_connection', 'socket.getaddrinfo', 'requests.sessions.Session.request'):
            stack.enter_context(patch(target, forbidden))
        zip_file = stack.enter_context(zipfile.ZipFile(archive))
        for family, titles in SAMPLES.items():
            for title in titles:
                raw_path = next((ROOT / 'data/pages').glob(title + '__*.json'))
                saved_path = ROOT / 'data/parsed' / family / raw_path.name
                raw_bytes, saved_bytes = raw_path.read_bytes(), saved_path.read_bytes()
                # Match the ASCII hash suffix, independent of ZIP legacy filename encoding.
                suffix = '__' + raw_path.name.rsplit('__', 1)[1]
                zip_names = [n for n in zip_file.namelist() if n.startswith('pages/') and n.endswith(suffix)]
                assert len(zip_names) == 1
                zip_matches = zip_file.read(zip_names[0]) == raw_bytes
                payload, saved = json.loads(raw_bytes), json.loads(saved_bytes)
                _, text = payload_text(payload)
                parser = WikiTextParser()
                recovery = parser.recover_page(payload, raw_file='pages/' + raw_path.name)
                leaves, folds = inventory(text)
                covered = set()
                for unit in recovery['units']:
                    for span in unit.get('text_spans', [unit['source']]) + ([unit['speaker_source']] if unit.get('speaker_source') else []):
                        covered.update(range(span['start'], span['end']))
                gaps = []
                for leaf in leaves:
                    missing = [i for i in range(leaf['start'], leaf['end']) if HAN.match(text[i]) and i not in covered]
                    if missing:
                        gaps.append({**leaf, 'unexported_chinese': ''.join(text[i] for i in missing),
                                     'diagnostics': sorted({issue['rule'] for issue in recovery['issues'] if issue['source']['start'] <= missing[0] < issue['source']['end']})})
                evidence = {'family': family, 'title': title, 'raw_file': str(raw_path.relative_to(ROOT)),
                            'saved_file': str(saved_path.relative_to(ROOT)),
                            'raw_sha256': hashlib.sha256(raw_bytes).hexdigest(),
                            'saved_sha256': hashlib.sha256(saved_bytes).hexdigest(),
                            'matches_original_zip': zip_matches, 'source_text': text,
                            'folds': folds, 'units': recovery['units'], 'scenes': recovery['scenes'],
                            'issues': recovery['issues'], 'independent_lexical_gaps': gaps,
                            'saved_record': saved}
                evidence_path = OUT / (family + '--' + raw_path.name)
                evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
                method = {'archon-quests': 'parse_archon_quest_page',
                          'character-quests': 'parse_character_quest_page',
                          'event-quests': 'parse_event_quest_page'}[family]
                fresh = getattr(parser, method)(payload).to_dict()
                dialogue_key = '剧情对话' if family == 'event-quests' else '对话'
                row = {'family': family, 'title': title, 'matches_original_zip': zip_matches,
                       'raw_sha256': evidence['raw_sha256'], 'saved_sha256': evidence['saved_sha256'],
                       'saved_dialogue_matches_current_parser': saved[dialogue_key] == fresh[dialogue_key],
                       'folds': len(folds), 'units': len(recovery['units']),
                       'issues': dict(Counter(i['rule'] for i in recovery['issues'])),
                       'lexical_gaps': len(gaps), 'evidence': evidence_path.name}
                report.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    (OUT / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    run()
