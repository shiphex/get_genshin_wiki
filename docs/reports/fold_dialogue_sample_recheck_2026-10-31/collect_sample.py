"""Collect six new, fixed audit samples without changing production data."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
OUT = ROOT / '.uv-cache/independent-sample-audit-2026-10-31'
SAMPLES = {
    'archon-quests': ['众望所归', '月亮回家的夜晚'],
    'character-quests': ['西风吹拂的日常', '所织与所斩'],
    'event-quests': ['图书管理员的悠长假期', '重炮在聆听'],
}


def run():
    previous = ROOT / 'docs/reports/fold_dialogue_sample_audit_2026-10-30/audit_sample.py'
    spec = importlib.util.spec_from_file_location('original_sample_collector', previous)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SAMPLES, module.OUT = SAMPLES, OUT
    before = {}
    for family, titles in SAMPLES.items():
        for title in titles:
            raw = next((ROOT / 'data/pages').glob(title + '__*.json'))
            saved = ROOT / 'data/parsed' / family / raw.name
            for path in (raw, saved):
                before[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    with contextlib.redirect_stdout(io.StringIO()):
        module.run()
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest for name, digest in before.items())
    rows = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
    result = {'sample_count': len(rows), 'original_zip_matches': sum(r['matches_original_zip'] for r in rows),
              'saved_dialogue_matches_current_parser': sum(r['saved_dialogue_matches_current_parser'] for r in rows),
              'input_and_business_files_unchanged': True, 'samples': rows,
              'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                  'get_genshin_wiki/recovery/extract.py', 'get_genshin_wiki/recovery/display.py',
                  'get_genshin_wiki/recovery/legacy.py')}}
    (OUT / 'collection.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in {'samples', 'code_sha256'}}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    run()
