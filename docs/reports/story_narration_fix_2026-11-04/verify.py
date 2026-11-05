"""Sample semantic requirements plus generation and frozen-input checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from get_genshin_wiki.storage import JsonFileStore

OUT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def run():
    notices = module('notices', 'docs/reports/document_ui_sample_recheck_2026-11-04/check_announcements.py').run()
    assert notices['failed_document_rows'] == 0
    sample = module('sample', 'docs/reports/document_ui_sample_recheck_2026-11-04/verify_sample.py').run()
    assert sample['known_rows']['pass']
    assert all(x['speaker_and_content_sequence_equal'] and x['option_order_equal'] for x in sample['controls'])
    character = module('character', 'docs/reports/document_ui_sample_recheck_2026-11-04/review_character_samples.py')
    characters = [character.audit(*case) for case in character.CASES]
    assert all(c['normal_dialogue_sequence_equal'] and c['numbered_option_sequence_equal'] for c in characters)
    for c, (_, notices_at, narration_at) in zip(characters, character.CASES):
        raw = read(ROOT / c['raw_file'])
        page = next(iter(raw['query']['pages'].values()))
        lines = page['revisions'][0]['slots']['main']['*'].splitlines()
        expected = [(n, character.raw_narration(lines[n - 1])) for n in narration_at]
        expected += [(n, lines[n - 1].strip().removeprefix('|内容=').removeprefix('*').rstrip('}')) for n in notices_at]
        actual = [r['内容'] for r in read(ROOT / c['saved_file'])['对话'] if r['类型'] == 'narration']
        assert actual == [value for _, value in sorted(expected)]
        c['post_fix_narration_sequence_equal'] = True
        c['historical_metric_note'] = 'The old colon/all-narration metrics include notices as speakers; new checks expect notices as narration.'
    manifest = read(ROOT / '.uv-cache/0605-manifest.json')
    raw_count = 0
    for name, digest in manifest.items():
        if name.startswith(('pages/', 'categories/', 'category_members/')):
            assert hashlib.sha256((ROOT / 'data' / name).read_bytes()).hexdigest() == digest, name
            raw_count += 1
    aggregate_count = 0
    store = JsonFileStore(ROOT / 'data')
    for family, filename in [('archon-quests', 'archon_quests.json'), ('character-quests', 'character_quests.json')]:
        for quest in read(ROOT / 'data' / filename)['quests']:
            title = quest['任务标题']['中文'] if family == 'archon-quests' else quest['source_title']
            assert quest == read(ROOT / 'data/parsed' / family / store.build_filename(title))
            aggregate_count += 1
    result = dict(announcements=notices, known_rows_and_controls=sample, character_controls=characters,
                  raw_snapshot_hashes_verified=raw_count, aggregate_records_equal=aggregate_count,
                  verdict='PASS_REVIEWED_SAMPLES_ONLY')
    (OUT / 'semantic_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k in ('verdict', 'raw_snapshot_hashes_verified', 'aggregate_records_equal')}, ensure_ascii=False))


if __name__ == '__main__':
    run()
