"""Semantic recheck against raw lines, not production-derived expectations.

Keep the October audit and evidence snapshots unchanged. Its old lookup uses
colon suffixes as row identity; corrected narration includes the full label.
This verifier therefore checks full original rows and explicit type/speaker.
"""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

import mwparserfromhell as mw

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.recovery.display import replay_unit


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def run():
    main = module('independent_main', 'doc/reports/fold_dialogue_sample_recheck_2026-10-31/check_main_samples.py')
    other = module('independent_other', 'doc/reports/fold_dialogue_sample_recheck_2026-10-31/check_other_samples.py')
    controls = [main.sequence_check('archon-quests', '1b5fe85fa5'),
                main.sequence_check('character-quests', '0ff3aa7fb4')]
    assert all(c['dialogue_sequence_equal'] and c['option_sequence_equal'] for c in controls)
    event_controls = [other.audit(*case) for case in other.CASES[:2]]
    assert all(c['colon_row_sequence_equal'] and c['grouped_option_order_equal'] for c in event_controls)
    parser = WikiTextParser()
    evidence = []
    for family, suffix, line_numbers in [
        ('character-quests', '6a586c4ae4', [67, 69, 71, 300, 307, 316]),
        ('archon-quests', '9cc68e31c8', [824, 826, 828, 830, 832, 834]),
    ]:
        path = next((ROOT / 'data/pages').glob('*__' + suffix + '.json'))
        payload = json.loads(path.read_bytes())
        page = next(iter(payload['query']['pages'].values()))
        text = page['revisions'][0]['slots']['main']['*']
        lines = text.splitlines()
        saved = json.loads((ROOT / 'data/parsed' / family / path.name).read_bytes())
        result = parser.recover_page(payload, raw_file='pages/' + path.name)
        # Only the five notes individually inspected in the source audit are
        # detached here; do not infer that every blackout is editorial.
        known_notes = ['———雅珂达', '———杜林', '———派蒙', '——坎托尔', '旁边有他们的对话']
        for line_number in line_numbers:
            raw = lines[line_number - 1]
            expected = raw.strip().removeprefix('*')
            for note in known_notes:
                expected = expected.replace('{{黑幕|' + note + '}}', '')
            expected = expected.replace('<br>', '').strip()
            found = [r for r in saved['对话'] if r['内容'] == expected]
            assert len(found) == 1, (page['title'], line_number, found)
            row = found[0]
            assert row['类型'] == 'narration' and row['说话者'] == '', (line_number, row)
            units = [u for u in result['units'] if u['text'] == expected]
            assert len(units) == 1 and units[0]['type'] == 'narration' and units[0]['speaker'] is None
            unit = units[0]
            assert replay_unit(text, unit) == expected
            assert text[unit['source']['start']:unit['source']['end']].strip() in raw
            evidence.append({'title': page['title'], 'raw_line': line_number, 'raw': raw,
                             'actual': row, 'source': unit['source'], 'branch_path': unit['branch_path'],
                             'text_spans': unit['text_spans'], 'excluded_spans': unit.get('excluded_spans', [])})
        if suffix == '9cc68e31c8':
            annotations = [u['text'] for u in result['units'] if u['type'] == 'annotation']
            assert all(annotations.count(note) == 1 for note in known_notes)
            assert not any(note in r['内容'] for r in saved['对话'] for note in known_notes)
        else:
            # Reconcile the complete colon-shaped source inventory while
            # excluding only manually confirmed document rows from speakers.
            visible = re.sub(r'<!--[\s\S]*?-->', lambda m: '\n' * m.group().count('\n'), text)
            first = text[:text.index('==任务剧情==')].count('\n') + 1
            expected_dialogues = []
            for ln, line in enumerate(visible.splitlines(), 1):
                if ln < first or ln in line_numbers:
                    continue
                for segment in re.split(r'<br\s*/?>', line):
                    segment = re.sub(r'^\|(?:剧情\d+|内容)=', '', segment).strip().removeprefix('*')
                    match = re.match(r'([^：\n{}|]+)：(.*)', segment)
                    if match:
                        speaker, content = match.groups()
                        if ln in (120, 125):
                            assert '{{黑幕|反覆播送}}' in content
                            content = content.replace('{{黑幕|反覆播送}}', '')
                        expected_dialogues.append((speaker, content.rstrip('}').strip()))
            actual_dialogues = [(r['说话者'], r['内容']) for r in saved['对话'] if r['说话者']]
            assert actual_dialogues == expected_dialogues
            expected_options = [str(t.get('选项' + str(i)).value).strip()
                                for t in mw.parse(text).filter_templates(recursive=True) if str(t.name).strip() == '剧情选项'
                                for i in range(1, 20) if t.has('选项' + str(i))]
            assert [r['内容'] for r in saved['对话'] if r['类型'] == 'option'] == expected_options
            controls.append({'title': page['title'], 'expected_dialogues': len(expected_dialogues),
                             'expected_options': len(expected_options), 'dialogue_sequence_equal': True,
                             'option_sequence_equal': True})
    persisted = [json.loads(line) for line in (ROOT / 'data/reports/fold-dialogue-0605-annotations.jsonl').read_text(encoding='utf-8').splitlines()]
    assert all(any(n['source']['page_title'] == '月亮回家的夜晚' and n['text'] == value for n in persisted) for value in known_notes)
    # Additional real pages not used to design the initial fix: malformed
    # speaker-name quotes must not change their saved dialogue classification.
    reparse_report = json.loads((OUT / 'reparse_verification.json').read_bytes())
    for change in reparse_report['changes']:
        for item in change['rows']:
            before, after = item['before'], item['after']
            assert before['类型'] == 'character'
            assert after['类型'] == 'narration' and after['说话者'] == ''
            assert after['内容'] == before['说话者'] + '：' + before['内容']
            assert before['所属任务流程'] == after['所属任务流程']
    holdouts = []
    with zipfile.ZipFile(ROOT / reparse_report['backup']) as baseline:
        for title in ['孤独的远征者', '托克的璃月见闻录', '曾经的真相', '步入阳光之下']:
            suffix = hashlib.sha1(title.encode()).hexdigest()[:10]
            path = next((ROOT / 'data/parsed/character-quests').glob('*__' + suffix + '.json'))
            actual = json.loads(path.read_bytes())
            assert actual == json.loads(baseline.read(path.relative_to(ROOT).as_posix())), title
            raw = json.loads((ROOT / 'data/pages' / path.name).read_bytes())
            result = parser.recover_page(raw)
            ambiguous = [u for u in result['units'] if u['type'] == 'dialogue' and u['speaker'] in {'「公子', '「罗兰', '「巫婆', '「仆人'}]
            assert ambiguous and all(u['speaker_status'] == 'unresolved' for u in ambiguous)
            assert any(i['rule'] == 'unbalanced_speaker_quote' for i in result['issues'])
            holdouts.append({'title': title, 'business_record_unchanged': True, 'ambiguous_speeches': len(ambiguous)})
    for family, aggregate in [('archon-quests', 'archon_quests.json'), ('character-quests', 'character_quests.json')]:
        for record in json.loads((ROOT / 'data' / aggregate).read_bytes())['quests']:
            title = record['任务标题']['中文'] if family == 'archon-quests' else record['source_title']
            suffix = hashlib.sha1(title.encode()).hexdigest()[:10]
            path = next((ROOT / 'data/parsed' / family).glob('*__' + suffix + '.json'))
            assert json.loads(path.read_bytes()) == record
    report = {'verdict': 'PASS_REVIEWED_DOCUMENT_AND_CONTROL_CHECKS_ONLY',
              'original_report_rows_fixed': 11, 'additional_paper_row_fixed': 1,
              'full_source_rows': evidence, 'sequences': controls,
              'event_controls': [{k:v for k,v in r.items() if k in ('source_title', 'raw_colon_rows', 'raw_option_labels', 'colon_row_sequence_equal', 'grouped_option_order_equal')} for r in event_controls],
              'malformed_quote_holdouts': holdouts,
              'prayer_annotations_persisted': 5, 'aggregate_consistency': True}
    report['all_changed_rows_retain_full_original_label_and_body'] = reparse_report['changed_rows']
    (OUT / 'semantic_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:([{a:b for a,b in s.items() if a != 'raw_dialogue_line_numbers'} for s in v] if k == 'sequences' else v)
                      for k,v in report.items() if k != 'full_source_rows'}, ensure_ascii=False))
    return report


if __name__ == '__main__':
    run()
