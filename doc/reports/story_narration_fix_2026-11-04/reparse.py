"""Backed-up task regeneration and a new, offline recovery export.

Keeps previous audit reports and recovery directories intact. --apply is
required for business updates; the default only stages differences/exports.
"""
from collections import Counter
from datetime import datetime, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.recovery.display import replay_unit
from tools.recover_snapshot import offline_guard, validate_unit

OUT = Path(__file__).resolve().parent


def run(apply=False):
    # Reuse the already audited backup, metadata, aggregate and replay checks.
    spec = importlib.util.spec_from_file_location('document_ui_reparse', ROOT / 'doc/reports/document_ui_fix_2026-11-04/reparse.py')
    reparse = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reparse)
    reparse.OUT = OUT
    report = reparse.run(apply)
    destination = ROOT / 'data/recovery' / ('story-narration-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    destination.mkdir(parents=True, exist_ok=False)
    parser = WikiTextParser()
    counts, source_counts, kinds = Counter(), Counter(), Counter()
    documents, unit_count = set(), 0
    from contextlib import ExitStack
    from get_genshin_wiki.recovery.source import SourcePage
    with offline_guard(), ExitStack() as stack:
        handles = {name: stack.enter_context((destination / (name + '.jsonl')).open('w', encoding='utf-8'))
                   for name in ('text_units', 'scenes', 'issues', 'sources')}
        paths = sorted({p.name for family in reparse.FAMILIES for p in (ROOT / 'data/parsed' / family).glob('*.json')})
        for name in paths:
            path = ROOT / 'data/pages' / name
            before = reparse.digest(path)
            payload = reparse.read(path)
            raw_file = 'pages/' + name
            result = parser.recover_page(payload, raw_file=raw_file)
            source = SourcePage.from_payload(payload, raw_file)
            for unit in result['units']:
                validate_unit(unit, {raw_file: source})
                assert replay_unit(source.text, unit) == unit['text']
                if unit['type'] == 'narration':
                    assert unit['speaker'] is None and unit['speaker_status'] == 'not_applicable'
                    counts[unit['narration_kind']] += 1
                    if unit['narration_kind'] == 'document':
                        documents.add(unit['document_id'])
                unit_count += 1
                kinds[unit['type']] += 1
                source_counts[unit['source_kind']] += 1
            for field, name_out in (('units', 'text_units'), ('scenes', 'scenes'), ('issues', 'issues')):
                for entry in result[field]:
                    handles[name_out].write(json.dumps(entry, ensure_ascii=False) + '\n')
            handles['sources'].write(json.dumps(result['source'], ensure_ascii=False) + '\n')
            assert reparse.digest(path) == before
    export = dict(pages=len(paths), units=unit_count, narration_kinds=dict(counts),
                  unit_types=dict(kinds), source_kinds=dict(source_counts), document_groups=len(documents),
                  output=destination.relative_to(ROOT).as_posix(),
                  limitation='Offline cached task pages only; unresolved dependencies remain diagnostics. No semantic completeness claim.')
    reparse.write(destination / 'export_verification.json', export)
    reparse.write(OUT / 'recovery_export.json', export)
    if apply:
        summary_path = ROOT / 'data/reports/fold-dialogue-0605-verification.json'
        summary = reparse.read(summary_path)
        summary.update(latest_fix_report='doc/reports/story_narration_fix_2026-11-04.md', recovery_export=export['output'])
        reparse.write(summary_path, summary)
    print(json.dumps(export, ensure_ascii=False), flush=True)
    return report, export


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--apply', action='store_true')
    run(cli.parse_args().apply)
