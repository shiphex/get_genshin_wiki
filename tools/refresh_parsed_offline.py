"""Stage, verify and optionally replace parsed data without network access.

Raw caches and historical experiments are read-only. A non-version business
change is an error, not a migration to apply silently. --apply is required.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore
from get_genshin_wiki.versions import extract_version
from tools.recover_snapshot import offline_guard, run_recovery, snapshot_manifest, write_json

RAW_DIRS = ('pages', 'category_members', 'categories')
RECOVERY_NAME = 'full-offline-20261104'
RECOVERY_REL = 'recovery/' + RECOVERY_NAME
AGGREGATES = {'archon_quests.json': 'archon-quests', 'character_quests.json': 'character-quests'}
REPORT_REL = 'reports/entity-versions-latest.json'
METHODS = {
    'characters': 'parse_character_page', 'weapons': 'parse_weapon_page',
    'artifacts': 'parse_artifact_set_page', 'monsters': 'parse_monster_page',
    'books': 'parse_book_page', 'foods': 'parse_food_page', 'wildlife': 'parse_wildlife_page',
    'quest-items': 'parse_quest_item_page', 'items': 'parse_item_page',
    'materials': 'parse_material_page', 'namecards': 'parse_namecard_page',
    'secret-items': 'parse_secret_item_page', 'chronicles': 'parse_chronicle_page',
    'north-library': 'parse_north_library_page', 'archon-quests': 'parse_archon_quest_page',
    'character-quests': 'parse_character_quest_page', 'event-quests': 'parse_event_quest_page',
}


def read_json(path):
    return json.loads(path.read_bytes())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def capture_state(data_root: Path) -> dict:
    """Hash every protected input/output, including file names and absent paths."""
    result = {}
    for relative in (*RAW_DIRS, 'parsed', *AGGREGATES, RECOVERY_REL, REPORT_REL):
        path = data_root / relative
        if path.is_symlink() or (path.is_dir() and any(p.is_symlink() for p in path.rglob('*'))):
            raise ValueError(f'symlink in protected target: {path}')
        result[relative] = (snapshot_manifest(path) if path.is_dir() else
                            {'sha256': digest(path)} if path.is_file() else None)
    return result


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, value)


def _check_delta(old, new, relative):
    if old.get('所属版本') and old['所属版本'] != new.get('所属版本'):
        return {'file': relative, 'fields': ['所属版本'], 'reason': 'existing version conflict',
                'before': old['所属版本'], 'after': new.get('所属版本')}
    fields = sorted(k for k in old.keys() | new.keys()
                    if k != '所属版本' and (k not in old or k not in new or old[k] != new[k]))
    if fields:
        return {'file': relative, 'fields': fields, 'reason': 'non-version business change'}
    return None


def stage_business(data_root, frozen_root, output_root, report, *, baseline_business_root=None):
    """Reparse the existing official inventory, preserving its storage adapters."""
    from get_genshin_wiki.cli import _maybe_load_event_payload

    parser, store = WikiTextParser(), JsonFileStore(frozen_root)
    aggregates = {name: read_json(data_root / name) for name in AGGREGATES if (data_root / name).exists()}
    arc_index = aggregates.get('archon_quests.json', {}).get('index')
    if arc_index is None:
        arc_index = parser.parse_archon_quest_list_page(store.read('pages', '魔神任务')) if store.exists('pages', '魔神任务') else []
    arc_context = parser.build_archon_series_context(arc_index)
    char_context = parser.build_character_quest_series_context(
        parser.parse_character_quest_list_page(store.read('pages', '传说任务'))
    ) if store.exists('pages', '传说任务') else {}
    replacements, by_identity, evidence = {}, {}, []
    differences, coverage, accepted, accepted_details = [], {}, [], []
    for family, method in METHODS.items():
        paths = sorted((data_root / 'parsed' / family).glob('*.json'))
        counts = Counter()
        for path in paths:
            relative = path.relative_to(data_root).as_posix()
            raw_path = frozen_root / 'pages' / path.name
            if not raw_path.is_file():
                differences.append(dict(file=relative, fields=[], reason='missing source payload'))
                continue
            payload, old = read_json(raw_path), read_json(path)
            title, page_id, text = parser.extract_page_metadata(payload)
            if store.build_filename(title) != path.name:
                differences.append(dict(file=relative, fields=[], reason='source identity / filename mismatch'))
                continue
            resolution = extract_version(title, text)
            counts[resolution.status] += 1
            evidence.append(dict(family=family, source_title=title, page_id=page_id,
                                 raw_file='pages/' + path.name, wikitext_sha256=hashlib.sha256(text.encode()).hexdigest(),
                                 **asdict(resolution)))
            kwargs = {}
            if family == 'characters' and store.exists('pages', title + '语音'):
                voice = store.read('pages', title + '语音')
                if _has_text(voice):
                    kwargs['voice_payload'] = voice
            elif family == 'archon-quests':
                kwargs['series_context'] = arc_context
            elif family == 'character-quests':
                kwargs['series_context'] = char_context
            elif family == 'event-quests':
                kwargs['event_payload'] = _maybe_load_event_payload(store, parser, 'pages', payload)
            record = getattr(parser, method)(payload, **kwargs)
            if family == 'north-library':
                # These fields were supplied by category discovery, not parsing.
                # They are existing cached context; do not probe the live Wiki.
                record.library_category = old.get('library_category', '')
                record.category_candidates = old.get('category_candidates', [])
            new = record.to_storage_dict() if family == 'characters' else record.to_dict()
            if new.get('所属版本') != resolution.value:
                raise ValueError(f'version adapter mismatch: {relative}')
            difference = _check_delta(old, new, relative)
            if difference:
                baseline_path = baseline_business_root / relative if baseline_business_root else None
                baseline = read_json(baseline_path) if baseline_path and baseline_path.is_file() else None
                if (difference['reason'] == 'non-version business change' and baseline is not None
                        and {k: v for k, v in baseline.items() if k != '所属版本'}
                        == {k: v for k, v in new.items() if k != '所属版本'}):
                    accepted.append(difference)
                    accepted_details.append(dict(**difference,
                        before={k: old.get(k) for k in difference['fields']},
                        after={k: new.get(k) for k in difference['fields']},
                        baseline_sha256=digest(baseline_path)))
                else:
                    differences.append(difference)
            key = (family, title)
            if key in by_identity:
                raise ValueError(f'duplicate full source identity: {key}')
            by_identity[key] = new
            destination = output_root / relative
            _write(destination, new)
            if old != new:
                replacements[relative] = destination
        coverage[family] = dict(total=len(paths), **dict(counts))
        print(f'Business {family}: {len(paths)}', flush=True)
    report.update(coverage=coverage, differences=differences, entity_count=len(evidence),
                  changed_business_records=len(replacements), aggregate_records_checked=0,
                  accepted_baseline_changes=accepted)
    for name, aggregate in aggregates.items():
        family = AGGREGATES[name]
        result = dict(aggregate)
        quests = []
        seen = set()
        for old in aggregate['quests']:
            title = old.get('source_title') if family == 'character-quests' else old.get('source_title') or old['任务标题']['中文']
            key = (family, title)
            if not title or key in seen or key not in by_identity:
                raise ValueError(f'aggregate source identity missing/duplicate: {name}: {title}')
            seen.add(key)
            new = by_identity[key]
            difference = _check_delta(old, new, name + ':' + title)
            if difference:
                differences.append(difference)
            quests.append(new)
        expected_keys = {key for key in by_identity if key[0] == family}
        if seen != expected_keys:
            raise ValueError(f'aggregate inventory differs from single-page records: {name}')
        result['quests'] = quests
        report['aggregate_records_checked'] += len(quests)
        destination = output_root / name
        _write(destination, result)
        if aggregate != result:
            replacements[name] = destination
    with (output_root.parent / 'version_evidence.jsonl').open('w', encoding='utf-8') as handle:
        for row in evidence:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    _write(output_root.parent / 'unresolved_versions.json', [row for row in evidence if row['status'] != 'resolved'])
    _write(output_root.parent / 'accepted_existing_differences.json', accepted_details)
    if differences:
        reasons = ', '.join(sorted({d['reason'] for d in differences}))
        raise ValueError(f'blocked before replacement: {reasons} ({len(differences)} records)')
    return replacements


def _has_text(payload):
    pages = payload.get('query', {}).get('pages', {})
    return any(r.get('slots', {}).get('main', {}).get('*', '').strip()
               for p in pages.values() for r in p.get('revisions', []))


def _verify_manifest(root):
    saved = read_json(root / 'output_manifest.json')
    actual = snapshot_manifest(root)
    files = [f for f in actual['files'] if f['path'] != 'output_manifest.json']
    if saved['files'] != files:
        raise ValueError('recovery output manifest does not match generated files')


def _check_recovery_baseline(baseline, generated):
    if not baseline.exists():
        return None
    old_files = {p.relative_to(baseline).as_posix() for p in baseline.rglob('*') if p.is_file()}
    new_files = {p.relative_to(generated).as_posix() for p in generated.rglob('*') if p.is_file()}
    if old_files != new_files:
        raise ValueError('recovery baseline file inventory changed')
    for relative in sorted(new_files - {'output_manifest.json'}):
        old_path, new_path = baseline / relative, generated / relative
        if digest(old_path) == digest(new_path):
            continue
        if relative.startswith('parsed/'):
            difference = _check_delta(read_json(old_path), read_json(new_path), relative)
            if difference:
                raise ValueError(f'recovery non-version difference: {difference}')
        elif relative == 'character_quests.json':
            old, new = read_json(old_path), read_json(new_path)
            if {k: v for k, v in old.items() if k != 'quests'} != {k: v for k, v in new.items() if k != 'quests'}:
                raise ValueError('recovery aggregate structure changed')
            if len(old['quests']) != len(new['quests']) or any(_check_delta(a, b, relative) for a, b in zip(old['quests'], new['quests'])):
                raise ValueError('recovery aggregate non-version change')
        else:
            raise ValueError(f'recovery source/text/branch/diagnostic change: {relative}')
    return True


def _validate_targets(data_root, replacements):
    targets = []
    for relative, stage in replacements.items():
        path = Path(relative)
        allowed = (relative in {*AGGREGATES, RECOVERY_REL, REPORT_REL} or
                   len(path.parts) == 3 and path.parts[0] == 'parsed' and path.parts[1] in METHODS and path.suffix == '.json')
        target = (data_root / path).resolve()
        if not allowed or path.is_absolute() or '..' in path.parts or not target.is_relative_to(data_root.resolve()):
            raise ValueError(f'unsupported replacement target: {relative}')
        if (not stage.exists() or stage.is_symlink() or stage.resolve().is_relative_to(data_root.resolve())
                or data_root.resolve().is_relative_to(stage.resolve())
                or stage.is_dir() and any(p.is_symlink() for p in stage.rglob('*'))):
            raise ValueError(f'invalid staging target: {relative}')
        targets.append((relative, stage, target))
    return targets


def apply_outputs(data_root, replacements, expected_state, run_root, *, verify=None):
    """Back up verified targets, replace in place, and restore on any exception."""
    targets = _validate_targets(data_root, replacements)
    expected_outputs = {relative: snapshot_manifest(stage) if stage.is_dir() else digest(stage)
                        for relative, stage, target in targets}
    expected_old = {'parsed/' + row['path']: row['sha256']
                    for row in (expected_state.get('parsed') or {}).get('files', [])}
    for relative in (*AGGREGATES, REPORT_REL):
        expected_old[relative] = (expected_state.get(relative) or {}).get('sha256')
    expected_old[RECOVERY_REL] = expected_state.get(RECOVERY_REL)
    if capture_state(data_root) != expected_state:
        raise ValueError('protected inputs or outputs changed before replacement')
    run_root.mkdir(parents=True, exist_ok=True)
    backup = run_root / 'backup.zip'
    with zipfile.ZipFile(backup, 'x', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for relative, stage, target in targets:
            paths = sorted(p for p in target.rglob('*') if p.is_file()) if target.is_dir() else [target] if target.is_file() else []
            for path in paths:
                archive.write(path, path.relative_to(data_root).as_posix())
    with zipfile.ZipFile(backup) as archive:
        if archive.testzip() is not None:
            raise ValueError('backup failed CRC verification')
    _write(run_root / 'before_state.json', expected_state)
    # Recheck after the backup too: compressing a large recovery tree takes time.
    if capture_state(data_root) != expected_state:
        raise ValueError('protected inputs or outputs changed while backing up')
    journal, operations = [], []
    try:
        for relative, stage, target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            saved = run_root / 'previous' / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            existed = target.exists()
            if existed:
                target.replace(saved)
            operations.append((relative, target, saved, existed))
            actual_old = snapshot_manifest(saved) if saved.is_dir() else digest(saved) if existed else None
            if actual_old != expected_old.get(relative):
                raise ValueError(f'target changed during replacement: {relative}')
            journal.append(dict(target=relative, old_saved=existed, replaced=False))
            _write(run_root / 'replacement_journal.json', journal)
            stage.replace(target)
            journal[-1]['replaced'] = True
            _write(run_root / 'replacement_journal.json', journal)
        for relative, stage, target in targets:
            actual = snapshot_manifest(target) if target.is_dir() else digest(target)
            if actual != expected_outputs[relative]:
                raise ValueError(f'applied output failed verification: {relative}')
        if verify is not None:
            verify()
    except BaseException:
        for relative, target, saved, existed in reversed(operations):
            if target.exists():
                failed = run_root / 'failed' / relative
                failed.parent.mkdir(parents=True, exist_ok=True)
                target.replace(failed)
            if existed:
                saved.replace(target)
        _write(run_root / 'rollback.json', {'restored': capture_state(data_root) == expected_state})
        raise
    return backup


def run_refresh(data_root: Path, *, apply=False, work_root: Path | None = None,
                baseline_business_root: Path | None = None):
    data_root = Path(data_root).resolve()
    if not (data_root / 'pages').is_dir() or not (data_root / 'parsed').is_dir():
        raise ValueError('data root must contain pages and parsed directories')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_root = Path(work_root).resolve() if work_root else PROJECT_ROOT / '.uv-cache/entity-versions' / stamp
    if run_root == data_root or run_root.is_relative_to(data_root) or data_root.is_relative_to(run_root):
        raise ValueError('work root and data root must be disjoint')
    run_root.mkdir(parents=True, exist_ok=False)
    report = dict(status='staging', applied=False, offline=True, run_root=str(run_root),
                  data_root=str(data_root), generated_at=datetime.now(timezone.utc).isoformat())
    report_path = run_root / 'report.json'
    try:
        with offline_guard():
            before = capture_state(data_root)
            frozen = run_root / 'input'
            frozen.mkdir()
            for name in RAW_DIRS:
                if (data_root / name).exists():
                    shutil.copytree(data_root / name, frozen / name)
            input_manifest = snapshot_manifest(frozen)
            for name in RAW_DIRS:
                if before[name] != (snapshot_manifest(frozen / name) if (frozen / name).exists() else None):
                    raise ValueError('source changed during snapshot copy')
            _write(run_root / 'input_manifest.json', input_manifest)
            if baseline_business_root is not None:
                baseline_business_root = Path(baseline_business_root).resolve()
                metadata_path = baseline_business_root / 'baseline_manifest.json'
                metadata = read_json(metadata_path)
                if metadata.get('input_fingerprint_sha256') != input_manifest['fingerprint_sha256']:
                    raise ValueError('parser baseline input fingerprint does not match frozen input')
                actual = [f for f in snapshot_manifest(baseline_business_root)['files'] if f['path'] != 'baseline_manifest.json']
                if actual != metadata.get('files') or not metadata.get('parser_source_sha256'):
                    raise ValueError('parser baseline files/provenance do not match manifest')
                report['parser_baseline'] = dict(root=str(baseline_business_root),
                                                manifest_sha256=digest(metadata_path),
                                                parser_source_sha256=metadata['parser_source_sha256'])
            business = run_root / 'business'
            business.mkdir()
            replacements = stage_business(data_root, frozen, business, report,
                                          baseline_business_root=baseline_business_root)
            recovery, repeat = run_root / 'recovery', run_root / 'recovery-repeat'
            recovered = run_recovery(input_root=frozen, output_root=recovery, offline=True,
                                     manifest_path=run_root / 'input_manifest.json')
            run_recovery(input_root=frozen, output_root=repeat, offline=True,
                         manifest_path=run_root / 'input_manifest.json')
            _verify_manifest(recovery)
            _verify_manifest(repeat)
            if snapshot_manifest(recovery) != snapshot_manifest(repeat):
                raise ValueError('recovery repeat is not byte-identical')
            baseline_text = _check_recovery_baseline(data_root / RECOVERY_REL, recovery)
            report['recovery'] = dict(page_count=recovered['page_count'], unit_count=recovered['unit_count'],
                                      source_replay=recovered['source_replay'], branch_checks=recovered['branch_checks'],
                                      repeat_identical=True, baseline_text_unchanged=baseline_text,
                                      target=RECOVERY_REL, status=recovered['status'])
            if capture_state(data_root) != before:
                raise ValueError('protected inputs or outputs changed during staging')
            if snapshot_manifest(frozen) != input_manifest:
                raise ValueError('frozen source changed during staging')
            report.update(status='validated', raw_hashes_unchanged=True,
                          raw_file_count=input_manifest['file_count'], backup=None)
            if apply:
                report.update(applied=True, backup=str(run_root / 'backup.zip'))
                staged_report = run_root / 'official_report.json'
                _write(staged_report, report)
                replacements[RECOVERY_REL] = recovery
                replacements[REPORT_REL] = staged_report
                def final_verify():
                    after = capture_state(data_root)
                    if any(before[name] != after[name] for name in RAW_DIRS):
                        raise ValueError('raw sources changed after apply')
                    _verify_manifest(data_root / RECOVERY_REL)
                    _write(report_path, report)
                apply_outputs(data_root, replacements, before, run_root, verify=final_verify)
            else:
                _write(report_path, report)
            return report
    except BaseException as exc:
        report.update(status='failed', applied=False, error=f'{type(exc).__name__}: {exc}')
        _write(report_path, report)
        raise


def main(argv=None):
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument('--data-root', type=Path, default=PROJECT_ROOT / 'data')
    command.add_argument('--work-root', type=Path, help='New staging directory outside data root')
    command.add_argument('--apply', action='store_true', help='Back up and replace verified outputs')
    command.add_argument('--baseline-business-root', type=Path,
                         help='Explicitly accept only differences reproduced by a hashed prior parser baseline')
    args = command.parse_args(argv)
    try:
        report = run_refresh(args.data_root, apply=args.apply, work_root=args.work_root,
                             baseline_business_root=args.baseline_business_root)
    except (ValueError, RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
