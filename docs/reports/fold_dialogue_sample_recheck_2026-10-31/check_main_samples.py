"""Independent, limited source expectations for three newly selected pages.

Does not import the production parser, its display renderer, fixtures or reports.
The renderer implements only syntax manually inspected in these samples.
"""
from collections import Counter
import html
import json
from pathlib import Path
import re
import sys

import mwparserfromhell as mw
from mwparserfromhell.nodes import Text, HTMLEntity, Template, Tag, Wikilink, Comment

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
OUT = ROOT / '.uv-cache/independent-sample-audit-2026-10-31'


def visible(raw):
    result = []
    for node in mw.parse(raw).nodes:
        if isinstance(node, (Text, HTMLEntity)):
            result.append(html.unescape(str(node)))
        elif isinstance(node, Comment):
            continue
        elif isinstance(node, Template):
            name = str(node.name).strip()
            keys = {'颜色': ('描述', '内容', '2'), '注音': ('1',), '黑幕': ('1',)}.get(name)
            if keys is None:
                raise ValueError('Unreviewed inline template: ' + name)
            key = next((key for key in keys if node.has(key)), None)
            if key is None:
                raise ValueError('Unreviewed template arguments: ' + str(node))
            result.append(visible(str(node.get(key).value)))
        elif isinstance(node, Tag):
            if str(node.tag).lower() == 'br':
                result.append('\n')
            elif str(node.tag).lower() in {'span', 'font', 'b', 'i', 'strong', 'small'}:
                result.append(visible(str(node.contents)))
            else:
                raise ValueError('Unreviewed inline tag: ' + str(node.tag))
        elif isinstance(node, Wikilink):
            result.append(visible(str(node.text if node.text is not None else node.title)))
        else:
            raise ValueError('Unreviewed node: ' + type(node).__name__)
    return ''.join(result)


def load(family, suffix):
    path = next((ROOT / 'data/pages').glob('*__' + suffix + '.json'))
    payload = json.loads(path.read_bytes())
    page = next(iter(payload['query']['pages'].values()))
    text = page['revisions'][0]['slots']['main']['*']
    saved = json.loads((ROOT / 'data/parsed' / family / path.name).read_bytes())
    return page['title'], text, saved


def sequence_check(family, suffix):
    title, text, record = load(family, suffix)
    source = re.sub(r'<!--[\s\S]*?-->', lambda m: '\n' * m.group().count('\n'), text)
    start_line = text[:text.index('==任务剧情==')].count('\n') + 1
    expected, raw_lines = [], []
    for number, line in enumerate(source.splitlines(), 1):
        if number < start_line:
            continue
        line = re.sub(r'^\|(?:剧情\d+|内容)=', '', line).strip()
        match = re.match(r'^\*([^：{}<>|]+)：(.*)', line)
        if match:
            speaker, content = match.groups()
            expected.append((visible(speaker).strip(), visible(content).rstrip('}').strip()))
            raw_lines.append(number)
    options = []
    for template in mw.parse(source[source.index('==任务剧情=='):]).filter_templates():
        if str(template.name).strip() == '剧情选项':
            for param in template.params:
                if re.fullmatch(r'选项\d+', str(param.name).strip()):
                    options.append(visible(str(param.value)).strip())
    actual = [(r['说话者'], r['内容']) for r in record['对话'] if r['类型'] in {'character', 'traveler'}]
    actual_options = [r['内容'] for r in record['对话'] if r['类型'] == 'option']
    return {'title': title, 'expected_dialogues': len(expected), 'actual_dialogues': len(actual),
            'dialogue_sequence_equal': expected == actual,
            'expected_options': len(options), 'actual_options': len(actual_options),
            'option_sequence_equal': options == actual_options,
            'missing_dialogues': list((Counter(expected) - Counter(actual)).items()),
            'extra_dialogues': list((Counter(actual) - Counter(expected)).items()),
            'raw_dialogue_line_numbers': raw_lines}


def prayer_document_check():
    title, text, record = load('archon-quests', '9cc68e31c8')
    lines = text.splitlines()
    expected = []
    for line_number in (824, 826, 828, 830, 832, 834):
        line = lines[line_number - 1]
        assert line.startswith('*查看「祈月笺」：')
        raw = line.split('：', 1)[1]
        # These five author/context notes were inspected individually.
        raw = re.sub(r'\{\{黑幕\|[^{}]+\}\}', '', raw)
        expected.append({'raw_line': line_number, 'content': raw})
    actual = [r for r in record['对话'] if r['内容'] in {r['content'] for r in expected}]
    return {'title': title, 'scope': 'Wikitext lines 823-835 only; six written prayer notes',
            'expected': expected, 'actual': actual,
            'all_written_text_retained': all(any(r['内容'] == e['content'] for r in actual) for e in expected),
            'document_rows_not_character_speech': len(actual) == 6 and all(r['类型'] == 'narration' and not r['说话者'] for r in actual)}


def run():
    sequences = [sequence_check('archon-quests', '1b5fe85fa5'),
                 sequence_check('character-quests', '0ff3aa7fb4')]
    document = prayer_document_check()
    result = {'sequences': sequences, 'prayer_document': document,
              'verdict': 'PASS_REVIEWED_CHECKS_ONLY' if all(r['dialogue_sequence_equal'] and r['option_sequence_equal'] for r in sequences)
                         and document['document_rows_not_character_speech'] else 'REJECT'}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'main_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({**{k: v for k, v in result.items() if k not in {'prayer_document', 'sequences'}},
                      'sequences': [{k: v for k, v in r.items() if k != 'raw_dialogue_line_numbers'} for r in sequences],
                      'prayer_document_rows_not_character_speech': document['document_rows_not_character_speech']}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    sys.exit(0 if run()['verdict'] == 'PASS_REVIEWED_CHECKS_ONLY' else 1)
