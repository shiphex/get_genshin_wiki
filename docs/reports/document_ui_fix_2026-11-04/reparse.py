"""Reparse cached task records, preserving identity/context and backing up outputs.

Default writes audit artifacts only. --apply also updates task business records,
their two aggregates, and recovery annotations/issues. No crawler is used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from get_genshin_wiki.cli import _maybe_load_event_payload
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.recovery.display import replay_unit
from get_genshin_wiki.storage import JsonFileStore
from tools.recover_snapshot import offline_guard

OUT = Path(__file__).resolve().parent
FAMILIES = ('archon-quests', 'character-quests', 'event-quests')


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def rows(record, family):
    if family == 'event-quests':
        return [r for scene in record['剧情对话'] for r in scene['对话']]
    return record['对话']


def run(apply=False, baseline_backup=None):
    store, parser = JsonFileStore(ROOT / 'data'), WikiTextParser()
    raw_paths = [p for ns in ('pages', 'category_members', 'categories') for p in (ROOT / 'data' / ns).glob('*.json')]
    raw_hashes = {p: digest(p) for p in raw_paths}
    arc_path, char_path = ROOT / 'data/archon_quests.json', ROOT / 'data/character_quests.json'
    arc_summary, char_summary = read(arc_path), read(char_path)
    arc_context = parser.build_archon_series_context(arc_summary['index'])
    char_context = parser.build_character_quest_series_context(parser.parse_character_quest_list_page(store.read('pages', '传说任务')))
    files = {family: sorted((ROOT / 'data/parsed' / family).glob('*.json')) for family in FAMILIES}
    business_hashes = {p: digest(p) for group in files.values() for p in group}
    business_hashes.update({p: digest(p) for p in (arc_path, char_path)})
    baseline_records = {}
    if baseline_backup:
        baseline_backup = Path(baseline_backup).resolve()
        with zipfile.ZipFile(baseline_backup) as baseline:
            baseline_records = {p: json.loads(baseline.read(p.relative_to(ROOT).as_posix())) for group in files.values() for p in group}
    new_records, changes, units_by_page, metadata_differences = {}, [], {}, []
    counts, issues, notes, replays = {}, [], [], 0
    with offline_guard():
        for family, paths in files.items():
            for number, path in enumerate(paths, 1):
                payload = read(ROOT / 'data/pages' / path.name)
                title, _, text = parser.extract_page_metadata(payload)
                if family == 'archon-quests':
                    record = parser.parse_archon_quest_page(payload, series_context=arc_context).to_dict()
                elif family == 'character-quests':
                    record = parser.parse_character_quest_page(payload, series_context=char_context).to_dict()
                else:
                    event = _maybe_load_event_payload(store, parser, 'pages', payload)
                    record = parser.parse_event_quest_page(payload, event_payload=event).to_dict()
                old = baseline_records.get(path) or read(path)
                key = '剧情对话' if family == 'event-quests' else '对话'
                other_keys = [k for k in old.keys() | record.keys() if k != key and old.get(k) != record.get(k)]
                if other_keys:
                    assert set(other_keys) == {'相关角色'}, (title, other_keys)
                    metadata_differences.append({'family': family, 'title': title,
                                                 'before': old['相关角色'], 'after': record['相关角色']})
                before, after = rows(old, family), rows(record, family)
                assert len(before) == len(after), (title, 'row count changed')
                if old != record:
                    changed = [{'index': i, 'before': a, 'after': b} for i, (a,b) in enumerate(zip(before, after)) if a != b]
                    changes.append({'family': family, 'title': title, 'file': path.relative_to(ROOT).as_posix(), 'rows': changed})
                    write(OUT / 'current' / family / path.name, record)
                else:
                    staged = OUT / 'current' / family / path.name
                    if staged.exists():
                        staged.unlink()
                new_records[path] = record
                recovered = parser.recover_page(payload, raw_file='pages/' + path.name)
                units_by_page[title] = recovered['units']
                assert all(replay_unit(text, u) == u['text'] for u in recovered['units']), title
                replays += len(recovered['units'])
                issues.extend(recovered['issues'])
                notes.extend(u for u in recovered['units'] if u['type'] == 'annotation')
                if number % 100 == 0:
                    print(f'{family}: {number}/{len(paths)}', flush=True)
            counts[family] = len(paths)
            print(f'{family}: {len(paths)} complete', flush=True)
    # Render a compact independent-review inventory of every changed row.
    for change in changes:
        for row in change['rows']:
            content = row['after'].get('内容', '')
            matching = [u for u in units_by_page[change['title']] if u['text'] == content]
            row['classification_reasons'] = sorted({u.get('classification_reason', '') for u in matching})
    assert all(digest(p) == value for p, value in raw_hashes.items())
    assert all(digest(p) == value for p, value in business_hashes.items())
    backup = None
    if apply:
        backup = ROOT / '.uv-cache' / ('document-ui-before-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.zip')
        other_outputs = [ROOT / 'data/reports' / name for name in (
            'fold-dialogue-0605-annotations.jsonl', 'fold-dialogue-0605-issues.jsonl', 'fold-dialogue-0605-verification.json')]
        with zipfile.ZipFile(backup, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in list(business_hashes) + [p for p in other_outputs if p.exists()]:
                archive.write(path, path.relative_to(ROOT).as_posix())
        # All records have been checked before any business data is replaced.
        for path, record in new_records.items():
            if read(path) != record:
                write(path, record)
        for summary_path, summary in ((arc_path, arc_summary), (char_path, char_summary)):
            family = 'archon-quests' if summary_path == arc_path else 'character-quests'
            for i, old in enumerate(summary['quests']):
                title = old['任务标题']['中文'] if family == 'archon-quests' else old['source_title']
                path = ROOT / 'data/parsed' / family / store.build_filename(title)
                summary['quests'][i] = new_records[path]
            summary['generated_at'] = datetime.now(timezone.utc).isoformat()
            write(summary_path, summary)
        for filename, entries in [('fold-dialogue-0605-issues.jsonl', issues), ('fold-dialogue-0605-annotations.jsonl', notes)]:
            (ROOT / 'data/reports' / filename).write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in entries), encoding='utf-8')
        assert all(read(p) == record for p, record in new_records.items())
        assert all(digest(p) == value for p, value in raw_hashes.items())
    report = {'applied': apply, 'record_counts': counts, 'changed_pages': len(changes),
              'changed_rows': sum(len(c['rows']) for c in changes), 'replayed_units': replays,
              'annotation_count': len(notes), 'raw_files_hash_verified': len(raw_hashes),
              'backup': (baseline_backup or backup).relative_to(ROOT).as_posix() if (baseline_backup or backup) else None,
              'pre_apply_backup': backup.relative_to(ROOT).as_posix() if backup else None,
              'related_character_updates': metadata_differences,
              'issues_by_rule': dict(Counter(i['rule'] for i in issues)),
              'changes': changes}
    write(OUT / 'reparse_verification.json', report)
    if apply:
        write(ROOT / 'data/reports/fold-dialogue-0605-verification.json', {
            'record_counts': counts, 'unique_pages_checked': len({p.name for p in new_records}),
            'raw_files_hash_verified': len(raw_hashes), 'annotation_count': len(notes),
            'issues_by_rule': report['issues_by_rule'],
            'latest_fix_report': 'docs/reports/document_ui_fix_2026-11-04.md'})
    print(json.dumps({k:v for k,v in report.items() if k not in ('issues_by_rule', 'changes', 'related_character_updates')}, ensure_ascii=False), flush=True)
    return report


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--apply', action='store_true')
    cli.add_argument('--baseline-backup', type=Path)
    args = cli.parse_args()
    run(args.apply, args.baseline_backup)
