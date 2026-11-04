"""Independent audit of exactly two new character-quest sample pages.

Raw Wikitext supplies expected text/order. No production parser, tests, or
reports supply expectations. mwparserfromhell only reads direct numbered
option parameters. Semantic notice expectations are separately identified
from manually read plot context; matching colon rows alone is not a pass.
Parent-collected issues are consulted only for the unsupported source shape.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

import mwparserfromhell as mw


ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
AUDIT_DIR = ROOT / '.uv-cache/independent-sample-audit-2026-11-04'
CASES = (
    ("1d60ad4965", [142, 143, 144, 145], [81, 161, 179, 217]),
    ("9f8aeeb802", [252, 253], [27, 68, 79, 87, 90, 93, 98, 99, 101, 102, 104, 106, 110]),
)


def raw_narration(line):
    line = line.removeprefix("::")
    if line.startswith("{{任务描述|"):
        body = line[7:].split("|", 1)[0].removesuffix("}}")
    elif line.startswith("{{颜色|"):
        body = line.split("|", 2)[2].removesuffix("}}")
    else:
        assert line.startswith("<small>") and line.endswith("</small>"), line
        body = line[7:-8]
    return re.sub(r"<br\s*/?>", "\n", body).strip()


def audit(suffix, notice_lines, narration_lines):
    raw_path = next((ROOT / "data/pages").glob(f"*{suffix}.json"))
    saved_path = ROOT / "data/parsed/character-quests" / raw_path.name
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    page = next(iter(payload["query"]["pages"].values()))
    text = page["revisions"][0]["slots"]["main"]["*"]
    lines = text.splitlines()
    visible = re.sub(r"<!--[\s\S]*?-->", lambda m: "\n" * m.group().count("\n"), text)
    plot_start = text[:text.index("==任务剧情==")].count("\n") + 1
    expected_rows = []
    for ln, line in enumerate(visible.splitlines(), 1):
        if ln <= plot_start:
            continue
        for fragment in re.split(r"<br\s*/?>", line):
            fragment = re.sub(r"^\|(?:内容|剧情\d+)=", "", fragment)
            fragment = fragment.strip().removeprefix("*")
            match = re.match(r"([^：\n{}|]+)：(.*)", fragment)
            if match:
                expected_rows.append((ln, match[1], match[2].rstrip("}").strip()))
    groups, unsupported = [], []
    for template in mw.parse(visible).filter_templates(recursive=True):
        if str(template.name).strip() != "剧情选项":
            continue
        labels = [str(template.get("选项" + str(i)).value).strip()
                  for i in range(1, 20) if template.has("选项" + str(i))]
        if labels:
            groups.append(labels)
        else:
            unsupported.append({"raw": str(template),
                                "unnumbered_label": str(template.get("选项").value).strip()
                                if template.has("选项") else None})
    saved_text = saved_path.read_text(encoding="utf-8")
    saved_lines = saved_text.splitlines()
    saved = json.loads(saved_text)
    rows = saved["对话"]
    actual_pairs = [(r["说话者"], r["内容"]) for r in rows if r["说话者"]]
    expected_pairs = [(speaker, body) for _, speaker, body in expected_rows]
    expected_options = [label for group in groups for label in group]
    actual_options = [r["内容"] for r in rows if r["类型"] == "option"]
    expected_narrations = [raw_narration(lines[ln - 1]) for ln in narration_lines]
    actual_narrations = [r["内容"] for r in rows if r["类型"] == "narration"]
    notice_checks = []
    for ln, speaker, body in expected_rows:
        if ln not in notice_lines:
            continue
        matches = [(i, row) for i, row in enumerate(rows)
                   if (row["说话者"], row["内容"]) == (speaker, body)
                   or row["内容"] == speaker + "：" + body]
        assert len(matches) == 1, (ln, matches)
        index, actual = matches[0]
        needle = '"内容": ' + json.dumps(actual["内容"], ensure_ascii=False)
        content_line = next(i + 1 for i, line in enumerate(saved_lines) if needle in line)
        expected_content = speaker + "：" + body
        notice_checks.append({
            "raw_line": ln, "raw": lines[ln - 1], "json_pointer": f"/对话/{index}",
            "json_speaker_line": content_line - 1, "json_content_line": content_line,
            "expected": {"说话者": "", "内容": expected_content, "类型": "narration"},
            "actual": actual,
            "semantic_pass": actual["说话者"] == "" and actual["类型"] == "narration"
                             and actual["内容"] == expected_content,
            "text_retained_across_current_fields": actual["内容"] == expected_content
                or actual["说话者"] + "：" + actual["内容"] == expected_content,
        })
    forensic_path = AUDIT_DIR / ("character-quests--" + raw_path.name)
    forensic = json.loads(forensic_path.read_text(encoding="utf-8")) if forensic_path.exists() else {}
    for shape in unsupported:
        shape["raw_line"] = text[:text.index(shape["raw"])].count("\n") + 1
        shape["business_present"] = shape["unnumbered_label"] in actual_options
        shape["observed_diagnostics_from_forensic_capture"] = [
            {"rule": issue["rule"], "raw": issue.get("raw")}
            for issue in forensic.get("issues", []) if issue.get("raw") == shape["raw"]]
    # Exclude notice rows only after the syntactic preservation comparison.
    real_expected = [(s, b) for ln, s, b in expected_rows if ln not in notice_lines]
    notice_labels = {s for ln, s, _ in expected_rows if ln in notice_lines}
    real_actual = [(s, b) for s, b in actual_pairs if s not in notice_labels]
    context_lines = ([123, 124, 125, 139, 141, 147, 149, 150, 151, 152]
                     if suffix == "1d60ad4965" else [251, 252, 253, 254])
    return {
        "title": page["title"], "raw_file": str(raw_path.relative_to(ROOT)),
        "saved_file": str(saved_path.relative_to(ROOT)),
        "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "saved_sha256": hashlib.sha256(saved_path.read_bytes()).hexdigest(),
        "scope": "Full decoded Wikitext of this page and its saved character-quest dialogues",
        "raw_colon_rows": len(expected_pairs), "saved_named_rows": len(actual_pairs),
        "colon_sequence_equal": expected_pairs == actual_pairs,
        "missing_colon_rows": list((Counter(expected_pairs) - Counter(actual_pairs)).items()),
        "extra_colon_rows": list((Counter(actual_pairs) - Counter(expected_pairs)).items()),
        "normal_dialogue_rows_excluding_notices": len(real_expected),
        "normal_dialogue_sequence_equal": real_expected == real_actual,
        "numbered_option_labels": len(expected_options), "saved_option_labels": len(actual_options),
        "numbered_option_groups": len(groups), "numbered_option_sequence_equal": expected_options == actual_options,
        "expected_narration_count": len(expected_narrations),
        "narration_source_lines": narration_lines,
        "existing_narration_sequence_equal": expected_narrations == actual_narrations,
        "blackout_template_count": text.count("{{黑幕"),
        "notice_semantic_basis": (
            "Plot says the marriage announcement has been posted/published; the notice-board fold contains official notice text. "
            "An adjacent separate fold explicitly names people discussing the announcement."
            if suffix == "1d60ad4965" else
            "The fold is explicitly the Palais Mermonia notice board; both rows are formal public notices addressing citizens, not a person's speech."),
        "notice_context_raw_lines": [{"line": ln, "raw": lines[ln - 1]} for ln in context_lines],
        "notice_checks": notice_checks, "unsupported_source_shapes": unsupported,
        "limitations": ["Two selected pages only; no full-corpus validation",
                        "Neither page contains blackout templates or quoted role names",
                        "Text preservation and semantic classification are separate checks",
                        "Unsupported-shape diagnostics use parent forensic capture only; it does not supply expectations"],
    }


if __name__ == "__main__":
    result = [audit(*case) for case in CASES]
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if len(sys.argv) == 2:
        target = Path(sys.argv[1]).resolve()
        if target.parent != AUDIT_DIR:
            raise ValueError("Write audit evidence only beside this script")
        target.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
