"""Offline refresh must validate before replacing any official artifact."""
import json
import socket
from pathlib import Path
from unittest.mock import patch
import zipfile

import pytest

from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore
from tests.helpers import build_page_payload


def prepare(root):
    store = JsonFileStore(root)
    payload = build_page_payload('书籍甲', '{{书籍|实装版本=1.0、1.2|卷1名=第一卷|卷1内容=原文}}')
    store.write('pages', '书籍甲', payload)
    old = WikiTextParser().parse_book_page(payload).to_dict()
    old.pop('所属版本')
    path = store.write('parsed/books', '书籍甲', old)
    store.write('category_members', '书籍', ['书籍甲'])
    return path


def test_dry_run_is_offline_and_leaves_official_files_unchanged(tmp_path):
    from tools.refresh_parsed_offline import run_refresh
    data = tmp_path / 'data'
    path = prepare(data)
    before = {p.relative_to(data).as_posix(): p.read_bytes() for p in data.rglob('*') if p.is_file()}
    with patch('get_genshin_wiki.client.MediaWikiClient.__init__', side_effect=AssertionError('client initialized')):
        report = run_refresh(data, work_root=tmp_path / 'staging')
    assert report['status'] == 'validated'
    assert report['applied'] is False
    assert report['raw_hashes_unchanged'] is True
    assert report['recovery']['repeat_identical'] is True
    assert before == {p.relative_to(data).as_posix(): p.read_bytes() for p in data.rglob('*') if p.is_file()}
    staged = Path(report['run_root']) / 'business' / path.relative_to(data)
    record = json.loads(staged.read_bytes())
    assert record['所属版本'] == '1.0、1.2'
    assert record['volumes'][0]['content'] == '原文'
    assert '所属版本' not in record['volumes'][0]


def test_apply_backs_up_and_replaces_same_paths_and_is_idempotent(tmp_path):
    from tools.refresh_parsed_offline import run_refresh
    data = tmp_path / 'data'
    path = prepare(data)
    before = path.read_bytes()
    raw = next((data / 'pages').glob('*')).read_bytes()
    report = run_refresh(data, apply=True, work_root=tmp_path / 'first')
    assert report['applied'] is True
    assert json.loads(path.read_bytes())['所属版本'] == '1.0、1.2'
    assert next((data / 'pages').glob('*')).read_bytes() == raw
    assert (data / 'recovery/full-offline-20261104/output_manifest.json').is_file()
    with zipfile.ZipFile(report['backup']) as backup:
        assert backup.read(path.relative_to(data).as_posix()) == before
    second = run_refresh(data, apply=True, work_root=tmp_path / 'second')
    assert second['changed_business_records'] == 0
    assert second['recovery']['baseline_text_unchanged'] is True


def test_non_version_difference_blocks_apply(tmp_path):
    from tools.refresh_parsed_offline import run_refresh
    data = tmp_path / 'data'
    path = prepare(data)
    old = json.loads(path.read_bytes());old['genre'] = '未经解析的旧值'
    path.write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
    before = path.read_bytes()
    with pytest.raises(ValueError, match='non-version'):
        run_refresh(data, apply=True, work_root=tmp_path / 'run')
    assert path.read_bytes() == before
    assert not (data / 'recovery').exists()
    report = json.loads((tmp_path / 'run/report.json').read_bytes())
    assert report['status'] == 'failed'
    assert report['differences'][0]['fields'] == ['genre']


def test_existing_version_conflict_blocks_apply(tmp_path):
    from tools.refresh_parsed_offline import run_refresh
    data = tmp_path / 'data';path = prepare(data)
    d = json.loads(path.read_bytes());d['所属版本'] = '5.8'
    path.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ValueError, match='existing version'):
        run_refresh(data, apply=True, work_root=tmp_path / 'run')
    assert json.loads(path.read_bytes())['所属版本'] == '5.8'


def test_missing_raw_source_blocks_apply(tmp_path):
    from tools.refresh_parsed_offline import run_refresh
    data = tmp_path / 'data';path = prepare(data)
    next((data / 'pages').glob('*')).unlink()
    with pytest.raises(ValueError, match='source'):
        run_refresh(data, apply=True, work_root=tmp_path / 'run')
    assert '所属版本' not in json.loads(path.read_bytes())


def test_network_calls_are_forbidden_inside_refresh(tmp_path, monkeypatch):
    from tools import refresh_parsed_offline as refresh
    data = tmp_path / 'data';path = prepare(data);before = path.read_bytes()
    def network_attempt(*args, **kwargs):
        socket.create_connection(('example.com', 443))
    monkeypatch.setattr(refresh, 'stage_business', network_attempt)
    with pytest.raises(RuntimeError, match='network access forbidden'):
        refresh.run_refresh(data, apply=True, work_root=tmp_path / 'run')
    assert path.read_bytes() == before


def test_concurrent_change_rejects_replacement(tmp_path):
    from tools.refresh_parsed_offline import capture_state, apply_outputs
    data = tmp_path / 'data';path = prepare(data)
    expected = capture_state(data)
    stage = tmp_path / 'new.json';stage.write_text('{}', encoding='utf-8')
    path.write_text('{"concurrent":true}', encoding='utf-8')
    with pytest.raises(ValueError, match='changed'):
        apply_outputs(data, {path.relative_to(data).as_posix(): stage}, expected, tmp_path / 'run')
    assert json.loads(path.read_bytes()) == {'concurrent': True}


def test_failed_replacement_rolls_back_files_and_recovery(tmp_path, monkeypatch):
    from tools.refresh_parsed_offline import capture_state, apply_outputs
    data = tmp_path / 'data';path = prepare(data);before = path.read_bytes()
    recovery = data / 'recovery/full-offline-20261104'
    recovery.mkdir(parents=True);(recovery / 'old.txt').write_text('old', encoding='utf-8')
    new_file = tmp_path / 'new.json';new_file.write_text('{"new":true}', encoding='utf-8')
    new_dir = tmp_path / 'new-recovery';new_dir.mkdir();(new_dir / 'new.txt').write_text('new', encoding='utf-8')
    expected = capture_state(data)
    original = Path.replace
    def fail_once(self, target):
        if self == new_dir:
            raise OSError('injected replacement failure')
        return original(self, target)
    monkeypatch.setattr(Path, 'replace', fail_once)
    with pytest.raises(OSError, match='injected'):
        apply_outputs(data, {path.relative_to(data).as_posix(): new_file,
                            'recovery/full-offline-20261104': new_dir}, expected, tmp_path / 'run')
    assert path.read_bytes() == before
    assert (recovery / 'old.txt').read_text(encoding='utf-8') == 'old'
    assert capture_state(data) == expected


def test_task_aggregates_match_full_source_identity_even_with_shared_display_name(tmp_path):
    from tools.refresh_parsed_offline import run_refresh
    data = tmp_path / 'data';prepare(data)
    store = JsonFileStore(data);records = []
    for number, title in enumerate(['甲/同名任务', '乙/同名任务'], 10):
        payload = build_page_payload(title, '{{任务|任务名称=同名任务|所属版本=2.1}}', page_id=number)
        store.write('pages', title, payload)
        d = WikiTextParser().parse_character_quest_page(payload).to_dict()
        store.write('parsed/character-quests', title, d);records.append(d)
    aggregate = {'quests': records, 'quest_count': 2, 'index': [{'original': '保留'}]}
    (data / 'character_quests.json').write_text(json.dumps(aggregate, ensure_ascii=False), encoding='utf-8')
    report = run_refresh(data, apply=True, work_root=tmp_path / 'run')
    result = json.loads((data / 'character_quests.json').read_bytes())
    assert result == aggregate
    assert result['quests'][0]['page_id'] != result['quests'][1]['page_id']
    assert report['aggregate_records_checked'] == 2


def test_replacement_rejects_paths_outside_allowed_targets(tmp_path):
    from tools.refresh_parsed_offline import capture_state, apply_outputs
    data = tmp_path / 'data';prepare(data)
    stage = tmp_path / 'new.json';stage.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='target'):
        apply_outputs(data, {'pages/forbidden.json': stage}, capture_state(data), tmp_path / 'run')


def test_post_replace_corruption_is_detected_and_rolled_back(tmp_path, monkeypatch):
    from tools.refresh_parsed_offline import capture_state, apply_outputs
    data = tmp_path / 'data';path = prepare(data);before = path.read_bytes()
    staged = tmp_path / 'new.json';staged.write_text('{"new":true}', encoding='utf-8')
    expected = capture_state(data)
    original = Path.replace
    def corrupt(self, target):
        result = original(self, target)
        if self == staged:
            Path(target).write_text('{"corrupted":true}', encoding='utf-8')
        return result
    monkeypatch.setattr(Path, 'replace', corrupt)
    with pytest.raises(ValueError, match='verification'):
        apply_outputs(data, {path.relative_to(data).as_posix(): staged}, expected, tmp_path / 'run')
    assert path.read_bytes() == before


def test_raw_source_cannot_be_used_as_movable_staging_file(tmp_path):
    from tools.refresh_parsed_offline import capture_state, apply_outputs
    data = tmp_path / 'data';path = prepare(data)
    source = next((data / 'pages').glob('*'));before = source.read_bytes()
    with pytest.raises(ValueError, match='staging'):
        apply_outputs(data, {path.relative_to(data).as_posix(): source}, capture_state(data), tmp_path / 'run')
    assert source.read_bytes() == before


def test_final_manifest_check_failure_is_inside_rollback_transaction(tmp_path, monkeypatch):
    from tools import refresh_parsed_offline as refresh
    data = tmp_path / 'data';path = prepare(data);before = path.read_bytes()
    verify = refresh._verify_manifest
    def fail_official(root):
        if root == data / refresh.RECOVERY_REL:
            raise ValueError('injected final manifest failure')
        return verify(root)
    monkeypatch.setattr(refresh, '_verify_manifest', fail_official)
    with pytest.raises(ValueError, match='final manifest'):
        refresh.run_refresh(data, apply=True, work_root=tmp_path / 'run')
    assert path.read_bytes() == before
    assert not (data / refresh.RECOVERY_REL).exists()
    assert not (data / refresh.REPORT_REL).exists()
    assert json.loads((tmp_path / 'run/rollback.json').read_bytes())['restored'] is True


def test_mid_batch_concurrent_update_is_preserved_and_blocks_apply(tmp_path, monkeypatch):
    from tools import refresh_parsed_offline as refresh
    data = tmp_path / 'data';first = prepare(data);before = first.read_bytes()
    second = first.with_name('second.json');second.write_text('{"old":2}', encoding='utf-8')
    a = tmp_path / 'a.json';a.write_text('{"new":1}', encoding='utf-8')
    b = tmp_path / 'b.json';b.write_text('{"new":2}', encoding='utf-8')
    state = refresh.capture_state(data)
    write = refresh._write
    injected = False
    def intervene(path, value):
        nonlocal injected
        if path.name == 'replacement_journal.json' and not injected:
            second.write_text('{"concurrent":true}', encoding='utf-8');injected = True
        return write(path, value)
    monkeypatch.setattr(refresh, '_write', intervene)
    with pytest.raises(ValueError, match='changed'):
        refresh.apply_outputs(data, {first.relative_to(data).as_posix(): a,
                                     second.relative_to(data).as_posix(): b}, state, tmp_path / 'run')
    assert first.read_bytes() == before
    assert json.loads(second.read_bytes()) == {'concurrent': True}


def prepare_baseline(data, path, baseline):
    from tools.refresh_parsed_offline import capture_state
    from tools.recover_snapshot import snapshot_manifest, write_json
    baseline.mkdir()
    payload = json.loads(next((data / 'pages').glob('*')).read_bytes())
    expected = WikiTextParser().parse_book_page(payload).to_dict()
    relative = path.relative_to(data)
    dest = baseline / relative;dest.parent.mkdir(parents=True)
    write_json(dest, expected)
    frozen = baseline.parent / (baseline.name + '-raw');frozen.mkdir()
    import shutil
    for name in ('pages', 'category_members', 'categories'):
        if (data / name).exists():shutil.copytree(data / name, frozen / name)
    write_json(baseline / 'baseline_manifest.json', {
        'input_fingerprint_sha256': snapshot_manifest(frozen)['fingerprint_sha256'],
        'parser_source_sha256': 'fixture-baseline',
        'files': snapshot_manifest(baseline)['files'],
    })
    return dest


def test_explicit_frozen_parser_baseline_allows_only_proven_existing_differences(tmp_path):
    from tools.refresh_parsed_offline import run_refresh
    data = tmp_path / 'data';path = prepare(data)
    old = json.loads(path.read_bytes());old['genre'] = '旧解析值'
    path.write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
    baseline = tmp_path / 'baseline';prepare_baseline(data, path, baseline)
    report = run_refresh(data, apply=True, work_root=tmp_path / 'run', baseline_business_root=baseline)
    assert json.loads(path.read_bytes())['genre'] == ''
    assert report['accepted_baseline_changes'][0]['fields'] == ['genre']
    changes = json.loads((tmp_path / 'run/accepted_existing_differences.json').read_bytes())
    assert changes[0]['before']['genre'] == '旧解析值'
    assert changes[0]['after']['genre'] == ''


def test_baseline_does_not_allow_new_regression_or_changed_input(tmp_path):
    from tools.refresh_parsed_offline import run_refresh
    from tools.recover_snapshot import snapshot_manifest, write_json
    data = tmp_path / 'data';path = prepare(data)
    old = json.loads(path.read_bytes());old['genre'] = '旧解析值'
    path.write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
    baseline = tmp_path / 'baseline';dest = prepare_baseline(data, path, baseline)
    expected = json.loads(dest.read_bytes());expected['genre'] = '另一种解析值';write_json(dest, expected)
    meta_path = baseline / 'baseline_manifest.json';meta = json.loads(meta_path.read_bytes())
    meta['files'] = [f for f in snapshot_manifest(baseline)['files'] if f['path'] != 'baseline_manifest.json'];write_json(meta_path, meta)
    with pytest.raises(ValueError, match='non-version'):
        run_refresh(data, apply=True, work_root=tmp_path / 'run', baseline_business_root=baseline)
    meta['input_fingerprint_sha256'] = 'different-input';write_json(meta_path, meta)
    with pytest.raises(ValueError, match='baseline.*input'):
        run_refresh(data, apply=True, work_root=tmp_path / 'other', baseline_business_root=baseline)
    assert json.loads(path.read_bytes())['genre'] == '旧解析值'
