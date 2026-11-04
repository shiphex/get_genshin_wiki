"""Independent, read-only inspection of exactly three selected snapshots.

Expected text comes from raw Wikitext, not the recovery extractor, tests or
reports. A small line scanner covers the syntax manually read in these pages.
mwparserfromhell is used only to inspect direct option parameters and nesting;
no production get_genshin_wiki code is imported. Colon-row equality proves
text/order preservation, not semantic correctness of a proposed speaker.
Semantic document checks below deliberately expose that distinction.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

import mwparserfromhell as mw


ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
CASES = (
    ("e051c16291", "event-quests", {144: "柯莱", 245: "妮露"}),
    ("2516d6c0fe", "event-quests", {}),
    ("6a586c4ae4", "character-quests", {120: "反覆播送", 125: "反覆播送"}),
)


def flattened_rows(parsed, family):
    if family == "character-quests":
        return [(f"/对话/{i}", row) for i, row in enumerate(parsed["对话"])]
    return [(f"/剧情对话/{si}/对话/{ri}", row)
            for si, scene in enumerate(parsed["剧情对话"])
            for ri, row in enumerate(scene["对话"])]


def line_display(raw):
    return re.sub(r"<br\s*/?>", "\n", raw).strip()


def audit(suffix, family, confirmed_notes):
    raw_path = next((ROOT / "data/pages").glob(f"*{suffix}.json"))
    parsed_path = ROOT / "data/parsed" / family / raw_path.name
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    page = next(iter(payload["query"]["pages"].values()))
    text = page["revisions"][0]["slots"]["main"]["*"]
    raw_lines = text.splitlines()
    visible = re.sub(r"<!--[\s\S]*?-->",
                     lambda m: "\n" * m.group().count("\n"), text)
    start_line = text[:text.index("==任务剧情==")].count("\n") + 1
    expected_colon_rows = []
    for ln, line in enumerate(visible.splitlines(), 1):
        if ln < start_line:
            continue
        for segment in re.split(r"<br\s*/?>", line):
            segment = re.sub(r"^\|(?:剧情\d+|内容)=", "", segment)
            segment = segment.strip().removeprefix("*")
            match = re.match(r"([^：\n{}|]+)：(.*)", segment)
            if match:
                speaker, content = match.groups()
                if ln in confirmed_notes:
                    marker = "{{黑幕|" + confirmed_notes[ln] + "}}"
                    assert marker in content, (suffix, ln, marker)
                    content = content.replace(marker, "")
                expected_colon_rows.append((ln, speaker, content.rstrip("}").strip()))

    # Direct sibling option labels are read from raw template syntax. Template
    # preorder gives the legacy grouped-label order even with nested choices.
    expected_groups = []
    for template in mw.parse(visible).filter_templates(recursive=True):
        if str(template.name).strip() == "剧情选项":
            expected_groups.append([
                str(template.get("选项" + str(i)).value).strip()
                for i in range(1, 20) if template.has("选项" + str(i))])
    parsed_text = parsed_path.read_text(encoding="utf-8")
    parsed = json.loads(parsed_text)
    located = flattened_rows(parsed, family)
    actual_colon_rows = [(row["说话者"], row["内容"])
                         for _, row in located if row.get("说话者")]
    expected_pairs = [(speaker, content) for _, speaker, content in expected_colon_rows]
    expected_options = [label for group in expected_groups for label in group]
    if family == "event-quests":
        actual_groups = [row["选项"] for _, row in located if row["类型"] == "选项"]
        options_equal = expected_groups == actual_groups
        actual_options = [label for group in actual_groups for label in group]
    else:
        actual_options = [row["内容"] for _, row in located if row["类型"] == "option"]
        options_equal = expected_options == actual_options
    result = {
        "source_title": page["title"], "scope": "Only this selected page and parsed counterpart",
        "raw_file": str(raw_path.relative_to(ROOT)),
        "parsed_file": str(parsed_path.relative_to(ROOT)),
        "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "parsed_sha256": hashlib.sha256(parsed_path.read_bytes()).hexdigest(),
        "raw_colon_rows": len(expected_pairs), "actual_speaker_rows": len(actual_colon_rows),
        "colon_row_sequence_equal": expected_pairs == actual_colon_rows,
        "raw_option_labels": len(expected_options), "actual_option_labels": len(actual_options),
        "raw_option_groups": len(expected_groups), "grouped_option_order_equal": options_equal,
        "missing_colon_rows": list((Counter(expected_pairs) - Counter(actual_colon_rows)).items()),
        "extra_colon_rows": list((Counter(actual_colon_rows) - Counter(expected_pairs)).items()),
        "manually_confirmed_inline_notes": [
            {"raw_line": ln, "note": note, "raw": raw_lines[ln - 1]}
            for ln, note in confirmed_notes.items()],
        "semantic_document_checks": [], "other_source_boundaries": [],
    }
    if suffix == "6a586c4ae4":
        # These are source UI/document rows, not evidence of a speaking person.
        for ln, content in [(69, "「…宣传支出十万摩拉、雇佣支出二十万摩拉、原料支出…」"),
                            (71, "「…快递员…将于…上午进城，途经…」"),
                            (300, "桌上散落着一些信件…"),
                            (307, "把爱洛芙也叫上吧！」"),
                            (316, "桌上散落着一些笔记…")]:
            matches = [(pointer, row) for pointer, row in located if row.get("内容") == content]
            assert len(matches) == 1, (ln, matches)
            pointer, actual = matches[0]
            needle = '"内容": ' + json.dumps(actual["内容"], ensure_ascii=False)
            # Serialized rows put speaker immediately before content. This
            # zero-based content index is the one-based speaker line number.
            speaker_line = next(i for i, line in enumerate(parsed_text.splitlines())
                                if needle in line)
            result["semantic_document_checks"].append({
                "raw_line": ln, "raw": raw_lines[ln - 1], "json_pointer": pointer,
                "json_speaker_line": speaker_line,
                "expected_type": "narration", "expected_speaker": "",
                "expected_content": raw_lines[ln - 1].strip(), "actual": actual,
                "passes": actual["类型"] == "narration" and actual["说话者"] == "",
                "scope_note": "fold body" if ln >= 296 else "outside fold",
            })
        pv_lines = [181, 182, 183, 185, 186, 188, 189, 190, 191, 193, 194,
                    198, 199, 200, 202, 203, 204, 205, 206, 207, 208, 209,
                    210, 212, 213]
        expected_pv = [line_display(raw_lines[ln - 1]) for ln in pv_lines]
        actual_pv = [row["内容"] for _, row in located if row["类型"] == "narration"
                     and row["所属任务流程"] == "离开厄舍的工厂"
                     and row["内容"] in expected_pv]
        result["unattributed_pv_fragments"] = {
            "raw_count": len(expected_pv), "sequence_equal": expected_pv == actual_pv}
        for pointer, row in located:
            if row.get("说话者") == "（派蒙":
                result["other_source_boundaries"].append({
                    "raw_line": 196, "raw": raw_lines[195], "json_pointer": pointer,
                    "actual": row, "note": "Parenthesis included in speaker; source boundary issue"})
    if suffix == "2516d6c0fe":
        for pointer, row in located:
            if row.get("说话者") == "=谢妮":
                result["other_source_boundaries"].append({
                    "raw_line": 136, "raw": raw_lines[135], "json_pointer": pointer,
                    "actual": row, "note": "Raw source itself has leading =; not claimed as a new regression"})
    return result


if __name__ == "__main__":
    evidence = [audit(*case) for case in CASES]
    output = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    if len(sys.argv) == 2:
        target = Path(sys.argv[1]).resolve()
        allowed = Path(__file__).resolve().parent
        if target.parent != allowed:
            raise ValueError("Evidence output must stay beside this audit script")
        target.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
