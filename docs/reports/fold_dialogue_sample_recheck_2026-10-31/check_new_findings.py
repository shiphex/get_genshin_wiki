"""Recheck written-document classification on two new real samples.

Exit 1 means at least one reviewed document row is still a character utterance.
Counts of colon-shaped source rows are reported separately from semantic checks.
"""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
OUT = ROOT / '.uv-cache/independent-sample-audit-2026-10-31'


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def run():
    main = module('recheck_main_samples', 'check_main_samples.py')
    other = module('recheck_other_samples', 'check_other_samples.py')
    rows = [other.audit(*case) for case in other.CASES]
    document_checks = [check for row in rows for check in row['semantic_document_checks']]
    prayer = main.prayer_document_check()
    failed = [check for check in document_checks if not check['passes']]
    result = {'other_samples': rows, 'prayer_document': prayer,
              'failed_written_document_rows': len(failed) + sum(row['类型'] != 'narration' or bool(row['说话者']) for row in prayer['actual']),
              'verdict': 'PASS_REVIEWED_DOCUMENT_CHECKS_ONLY' if not failed and prayer['document_rows_not_character_speech'] else 'REJECT'}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'new_findings.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'verdict': result['verdict'], 'failed_written_document_rows': result['failed_written_document_rows'],
                      'other_sample_sequences': [{'title': row['source_title'], 'colon_row_sequence_equal': row['colon_row_sequence_equal'],
                                                  'option_order_equal': row['grouped_option_order_equal'],
                                                  'raw_colon_rows': row['raw_colon_rows'], 'raw_option_labels': row['raw_option_labels']}
                                                 for row in rows]}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    sys.exit(0 if run()['verdict'] == 'PASS_REVIEWED_DOCUMENT_CHECKS_ONLY' else 1)
