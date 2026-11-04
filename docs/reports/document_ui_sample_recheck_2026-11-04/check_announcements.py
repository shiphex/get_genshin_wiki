"""Independent semantic checks of six manually reviewed announcement rows.

No production parsing code or tests supply the expected narration classification.
The nearby source context identifies published notices on announcement boards.
"""
import json
from pathlib import Path
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
OUT = ROOT / '.uv-cache/independent-sample-audit-2026-11-04'
CASES = [('1d60ad4965', [142, 143, 144, 145]), ('9f8aeeb802', [252, 253])]


def run():
    checks = []
    for suffix, numbers in CASES:
        path = next((ROOT / 'data/pages').glob('*__' + suffix + '.json'))
        page = next(iter(json.loads(path.read_bytes())['query']['pages'].values()))
        lines = page['revisions'][0]['slots']['main']['*'].splitlines()
        parsed_path = ROOT / 'data/parsed/character-quests' / path.name
        rows = json.loads(parsed_path.read_bytes())['对话']
        for number in numbers:
            source = lines[number - 1]
            # These exact six source lines use no inline display templates.
            expected = source.strip().removeprefix('|内容=').removeprefix('*').rstrip('}').strip()
            assert expected.startswith(('幕府通告：', '市民通告：'))
            suffix_text = expected.split('：', 1)[1]
            matches = [(i, row) for i, row in enumerate(rows) if row['内容'] in {expected, suffix_text}]
            passed = len(matches) == 1 and matches[0][1]['内容'] == expected and matches[0][1]['类型'] == 'narration' and matches[0][1]['说话者'] == ''
            retained = len(matches) == 1 and (matches[0][1]['内容'] == expected or matches[0][1]['说话者'] + '：' + matches[0][1]['内容'] == expected)
            checks.append({'title': page['title'], 'raw_line': number, 'raw': source,
                           'parsed_file': parsed_path.relative_to(ROOT).as_posix(),
                           'expected_content': expected, 'expected_type': 'narration', 'expected_speaker': '',
                           'actual_matches': [{'json_pointer': '/对话/' + str(i), 'row': row} for i, row in matches],
                           'source_text_retained': retained, 'pass': passed})
    result = {'reviewed_document_rows': len(checks), 'failed_document_rows': sum(not c['pass'] for c in checks),
              'all_source_text_retained': all(c['source_text_retained'] for c in checks),
              'checks': checks, 'verdict': 'PASS_SIX_ANNOUNCEMENT_CHECKS_ONLY' if all(c['pass'] for c in checks) else 'REJECT'}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'announcements.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'checks'}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    sys.exit(0 if run()['verdict'] == 'PASS_SIX_ANNOUNCEMENT_CHECKS_ONLY' else 1)
