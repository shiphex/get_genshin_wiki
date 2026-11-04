"""Recheck the known audit findings against saved JSON, without rewriting it.

Uses the original independent scanner's raw expectations, with the one confirmed
inline 砂糖 hint removed from speech. The original audit scripts remain unchanged.
Writes verification artifacts only; no raw or parsed inputs are modified.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
AUDIT = ROOT / "doc/reports/fold_dialogue_sample_audit_2026-10-30"


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, AUDIT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    findings = load_module("check_findings").run()
    assert findings["verdict"] == "PASS_KNOWN_CHECKS_ONLY", findings["checks"]
    scanner = load_module("reviewer_check_events")
    event_checks = []
    for suffix in scanner.SAMPLES:
        path = next((ROOT / "data/pages").glob(f"*__{suffix}.json"))
        title, raw_dialogue, raw_options, notes = scanner.raw_expectation(json.loads(path.read_bytes()))
        expected = [(speaker, content) for _, speaker, content in raw_dialogue]
        for note in notes:
            # Exact, independently confirmed editorial hint from the original
            # audit. Do not classify arbitrary hidden text as a note here.
            assert title == "开火！玩具战争" and note["annotations"] == ["砂糖"] and note["speaker"] == "派蒙"
            index = next(i for i, row in enumerate(raw_dialogue) if row[0] == note["raw_line"])
            speaker, content = expected[index]
            assert content.endswith("砂糖")
            expected[index] = (speaker, content[:-len("砂糖")])
        parsed = json.loads((ROOT / "data/parsed/event-quests" / path.name).read_bytes())
        actual, options = [], []
        for scene in parsed["剧情对话"]:
            for row in scene["对话"]:
                if row["类型"] == "选项":
                    options.extend(row["选项"])
                elif row["类型"] != "旁白":
                    actual.append((row["说话者"], row["内容"]))
        assert actual == expected, title
        assert options == [text for _, text in raw_options], title
        event_checks.append({"title": title, "dialogues": len(actual), "options": len(options),
                             "exact_sequence_equal": True, "separated_confirmed_hints": len(notes)})

    audit_rows = json.loads((ROOT / ".uv-cache/independent-sample-audit/summary.json").read_bytes())
    assert len(audit_rows) == 12
    assert all(row["matches_original_zip"] and row["saved_dialogue_matches_current_parser"] for row in audit_rows)
    annotations = [json.loads(line) for line in (ROOT / "data/reports/fold-dialogue-0605-annotations.jsonl").read_text(encoding="utf-8").splitlines()]
    for title, value in [("尾声的尾声", "哑巴开口"), ("尾声的尾声", "派蒙表情包之一出处"), ("开火！玩具战争", "砂糖")]:
        assert any(note["source"]["page_title"] == title and note["text"] == value for note in annotations)

    # Independently scan the exact 17-line original cutscene; only its confirmed
    # editor hint is detached, and no production extraction helper is used.
    page_path = next((ROOT / "data/pages").glob("*__e4ed1de066.json"))
    page = next(iter(json.loads(page_path.read_bytes())["query"]["pages"].values()))
    text = page["revisions"][0]["slots"]["main"]["*"]
    start = text.index("{{折叠|标题=过场动画（夺心）|内容=")
    body_start = text.index("\n", start) + 1
    body_end = text.index("|折叠=是}}", body_start)
    original = [line for line in text[body_start:body_end].splitlines() if line.strip()]
    pairs = [tuple(line.replace("<br>", "").replace("{{黑幕|哑巴开口}}", "").split("：", 1)) for line in original]
    assert len(pairs) == 17
    record = json.loads((ROOT / "data/parsed/archon-quests" / page_path.name).read_bytes())
    first = next(i for i, row in enumerate(record["对话"]) if row["内容"] == pairs[0][1])
    cutscene = record["对话"][first:first + 17]
    assert [(row["说话者"], row["内容"]) for row in cutscene] == pairs
    aggregate = json.loads((ROOT / "data/archon_quests.json").read_bytes())
    assert next(row for row in aggregate["quests"] if row["任务标题"]["中文"] == page["title"]) == record
    comparison = [{"原始Wikitext": raw, "JSON": row} for raw, row in zip(original, cutscene, strict=True)]
    (ROOT / "data/reports/taking-heart-17-lines.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"known_checks": findings["checks"], "event_sequences": event_checks,
              "original_sample_count": 12, "original_samples_zip_and_saved_fresh": True,
              "taking_heart_exact_lines": 17, "persisted_annotation_count": len(annotations),
              "verdict": "PASS_KNOWN_CHECKS_ONLY"}
    output = ROOT / "data/reports/fold-dialogue-audit-fix-verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
