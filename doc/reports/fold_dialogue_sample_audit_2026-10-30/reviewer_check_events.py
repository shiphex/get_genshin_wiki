"""Read-only, independent audit of four selected event-quest snapshots.

This deliberately does not import the production parser, fixtures, or reports.
Rules are limited to syntax manually confirmed in these four raw Wikitext pages:
physical lines / br, *Speaker:Speech, |content= prefixes, and option/response
parameters. Comments are excluded. A black-curtain template is rendered only
for content/order comparison and separately reported as editorial contamination.
This is not a general Wikitext parser or a full-corpus validation.
"""
from collections import Counter
import json
from pathlib import Path
import re


ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
SAMPLES = ("ef7a3ea1cd", "eee6ab4b6c", "cab7307ef4", "59a46a986a")


def raw_expectation(payload):
    page = next(iter(payload["query"]["pages"].values()))
    text = page["revisions"][0]["slots"]["main"]["*"]
    # Retain newline positions so reported Wikitext line numbers remain exact.
    visible = re.sub(r"<!--[\s\S]*?-->",
                     lambda match: "\n" * match.group().count("\n"), text)
    start_line = text[:text.index("==任务剧情==")].count("\n") + 1
    dialogues, options, editorial = [], [], []
    for line_number, line in enumerate(visible.splitlines(), 1):
        if line_number < start_line:
            continue
        for option in re.findall(r"\|选项\d+=([^|\n}]+)", line):
            options.append((line_number, option))
        for segment in re.split(r"<br\s*/?>", line):
            segment = re.sub(r"^\|(?:剧情\d+|内容)=", "", segment)
            segment = segment.strip().removeprefix("*")
            match = re.match(r"([^：\n{}|]+)：(.*)", segment)
            if match is None:
                continue
            speaker, content = match.groups()
            annotations = re.findall(r"\{\{黑幕\|([^}]+)\}\}", content)
            if annotations:
                editorial.append({"raw_line": line_number, "speaker": speaker,
                                  "annotations": annotations, "raw": segment})
            content = re.sub(r"\{\{黑幕\|([^}]+)\}\}", r"\1", content)
            dialogues.append((line_number, speaker, content.rstrip("}").strip()))
    return page["title"], dialogues, options, editorial


def audit(suffix):
    raw_path = next((ROOT / "data/pages").glob(f"*{suffix}*.json"))
    parsed_path = ROOT / "data/parsed/event-quests" / raw_path.name
    title, dialogue_sources, option_sources, editorial = raw_expectation(
        json.loads(raw_path.read_text(encoding="utf-8")))
    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    actual_dialogues, actual_options, narrations = [], [], []
    for scene in parsed["剧情对话"]:
        for index, row in enumerate(scene["对话"]):
            if row["类型"] == "选项":
                actual_options.extend(row["选项"])
            elif row["类型"] == "旁白":
                narrations.append(row["内容"])
            else:
                actual_dialogues.append((row["说话者"], row["内容"]))
            for annotation in editorial:
                if row.get("说话者") == annotation["speaker"] and any(
                    value in row.get("内容", "") for value in annotation["annotations"]
                ):
                    annotation["actual_json"] = {
                        "scene": scene["任务流程"], "index": index, "entry": row}
    expected_dialogues = [(speaker, content) for _, speaker, content in dialogue_sources]
    expected_options = [text for _, text in option_sources]
    missing_dialogues = Counter(expected_dialogues) - Counter(actual_dialogues)
    missing_options = Counter(expected_options) - Counter(actual_options)
    return {
        "title": title,
        "expected_dialogues": len(expected_dialogues),
        "actual_dialogues": len(actual_dialogues),
        "expected_options": len(expected_options),
        "actual_options": len(actual_options),
        "dialogue_sequence_equal_with_black_curtain_rendered": expected_dialogues == actual_dialogues,
        "actual_dialogues_equal_expected_prefix": actual_dialogues == expected_dialogues[:len(actual_dialogues)],
        "option_sequence_equal": expected_options == actual_options,
        "missing_dialogue_count": sum(missing_dialogues.values()),
        "missing_option_count": sum(missing_options.values()),
        "extra_dialogues": list((Counter(actual_dialogues) - Counter(expected_dialogues)).items()),
        "extra_options": list((Counter(actual_options) - Counter(expected_options)).items()),
        "missing_dialogues_with_raw_lines": [entry for entry in dialogue_sources if (entry[1], entry[2]) in missing_dialogues],
        "missing_options_with_raw_lines": [entry for entry in option_sources if entry[1] in missing_options],
        "editorial_annotations": editorial,
        "actual_narrations": narrations,
    }


if __name__ == "__main__":
    print(json.dumps([audit(suffix) for suffix in SAMPLES], ensure_ascii=False, indent=2))
