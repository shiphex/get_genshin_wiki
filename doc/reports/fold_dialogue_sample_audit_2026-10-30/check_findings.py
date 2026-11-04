"""Reproduce four known failures on the fixed sample; exit 1 means rejection.

This checks desired behavior, not whether the previous broken output persists.
No tests or production parsing code supply the expected event dialogue sequence.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
sys.path.insert(0, str(ROOT))
from get_genshin_wiki.parser import WikiTextParser


def load(family, suffix):
    raw_path = next((ROOT / 'data/pages').glob('*__' + suffix + '.json'))
    saved_path = ROOT / 'data/parsed' / family / raw_path.name
    payload = json.loads(raw_path.read_text(encoding='utf-8'))
    page = next(iter(payload['query']['pages'].values()))
    text = page['revisions'][0]['slots']['main']['*']
    return payload, text, json.loads(saved_path.read_text(encoding='utf-8'))


def run():
    event_script = Path(__file__).with_name('reviewer_check_events.py')
    if not event_script.exists():
        event_script = ROOT / '.uv-cache/independent-sample-audit/reviewer_check_events.py'
    spec = importlib.util.spec_from_file_location('independent_event_audit', event_script)
    events = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(events)
    event_results = [events.audit(suffix) for suffix in events.SAMPLES]
    checks = []
    target = event_results[0]
    checks.append({'id': 'F1', 'requirement': 'Visible follow-up dialogue and options reach business JSON',
                   'pass': target['missing_dialogue_count'] == 0 and target['missing_option_count'] == 0
                           and not target['extra_dialogues'] and not target['extra_options']
                           and target['dialogue_sequence_equal_with_black_curtain_rendered'] and target['option_sequence_equal'],
                   'missing_dialogues': target['missing_dialogue_count'], 'missing_options': target['missing_option_count']})
    _, _, end = load('archon-quests', 'e4ed1de066')
    unwanted = [r for r in end['对话'] if '派蒙表情包之一出处' in r['内容'] or '哑巴开口' in r['内容']]
    event_unwanted = [a for r in event_results for a in r['editorial_annotations'] if a.get('actual_json')]
    checks.append({'id': 'F2', 'requirement': 'Known editorial hints do not become spoken dialogue',
                   'pass': not unwanted and not event_unwanted, 'archon_actual': unwanted, 'event_actual': event_unwanted})
    _, _, rock = load('character-quests', '7085f7cb33')
    document_labels = {'十一号盗宝鼬', '十二号盗宝鼬', '八号陆鳗鳗', '三号将军蟹', '五号妖狸', '九号陆鳗鳗'}
    wrong = [r for r in rock['对话'] if r['说话者'] in document_labels and r['类型'] in {'character', 'traveler'}]
    checks.append({'id': 'F3', 'requirement': 'Document entries are not classified as speakers',
                   'pass': not wrong, 'misclassified_document_rows': wrong})
    payload, text, snake = load('archon-quests', 'd6ba260bf8')
    narrative = '你们本以为一切已经结束，却再次有光在你们身后亮起，那是哈夫丹的灵魂在散发出最后的光芒。他向戴因说道：'
    start = text.index(narrative)
    recovered = WikiTextParser().recover_page(payload)
    retained = any(narrative in u['text'] for u in recovered['units'])
    diagnosed = any(i['source']['start'] <= start and i['source']['end'] >= start + len(narrative)
                    for i in recovered['issues'])
    saved_retained = any(narrative in r['内容'] for r in snake['对话'])
    checks.append({'id': 'F4', 'requirement': 'Colon-ended narration is retained or explicitly diagnosed',
                   'pass': (retained and saved_retained) or diagnosed,
                   'raw_line': text[:start].count('\n') + 1, 'raw': narrative,
                   'recovery_retained': retained, 'business_json_retained': saved_retained, 'diagnosed': diagnosed})
    return {'sample_size': 12, 'event_sequence_audit': event_results, 'checks': checks,
            'verdict': 'PASS_KNOWN_CHECKS_ONLY' if all(c['pass'] for c in checks) else 'REJECT'}


if __name__ == '__main__':
    result = run()
    output = ROOT / '.uv-cache/independent-sample-audit'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'findings.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for check in result['checks']:
        print(('PASS' if check['pass'] else 'FAIL') + ' ' + check['id'] + ': ' + check['requirement'])
    print(result['verdict'])
    sys.exit(0 if all(c['pass'] for c in result['checks']) else 1)
