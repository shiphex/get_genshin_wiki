"""Compatibility projections of source-aware text; JSONL remains authoritative."""
from __future__ import annotations

from ..models import ArchonQuestDialogue, EventQuestDialogueEntry, EventQuestStepRecord


def dialogue_scenes(result):
    scenes = [s for s in result["scenes"] if s["body_type"] == "dialogue"]
    return [s for s in scenes if not (s["chapter"] and s["title"] == s["chapter"] and any(t["chapter"] == s["chapter"] and t["title"] != s["chapter"] for t in scenes))]


def event_steps(result):
    steps = []
    for scene in dialogue_scenes(result):
        units = [u for u in result["units"] if u["scene_id"] == scene["scene_id"] and u["type"] in {"dialogue", "narration", "option"}]
        entries = []
        emitted_groups = set()
        for unit in units:
            if unit["type"] == "option":
                group = (unit["branch_path"] or [{}])[-1].get("group_id")
                if group:
                    if group in emitted_groups:
                        continue
                    emitted_groups.add(group)
                    labels = [u["text"] for u in units if u["type"] == "option" and u["branch_path"] and u["branch_path"][-1]["group_id"] == group]
                    entries.append(EventQuestDialogueEntry(type="选项", options=labels))
                elif entries and entries[-1].type == "选项":
                    entries[-1].options.append(unit["text"])
                else:
                    entries.append(EventQuestDialogueEntry(type="选项", options=[unit["text"]]))
            else:
                kind = "旁白" if unit["type"] == "narration" else "旅行者" if unit["speaker"] == "旅行者" else "角色/NPC"
                entries.append(EventQuestDialogueEntry(type=kind, speaker=unit["speaker"] or "" if kind != "旁白" else "", content=unit["text"]))
        steps.append(EventQuestStepRecord(title=scene["title"], dialogue=entries))
    return steps


def archon_dialogues(result):
    scenes = {s["scene_id"]: s for s in dialogue_scenes(result)}
    dialogues = []
    for unit in result["units"]:
        if unit["scene_id"] not in scenes or unit["type"] not in {"dialogue", "narration", "option"}:
            continue
        scene = scenes[unit["scene_id"]]
        flow = "" if scene["title"] in {"任务剧情", "剧情", "对话", "任务对话"} else scene["title"]
        kind = "option" if unit["type"] == "option" else "narration" if unit["type"] == "narration" else "traveler" if unit["speaker"] == "旅行者" else "character"
        dialogues.append(ArchonQuestDialogue(speaker=unit["speaker"] or "", text=unit["text"], dialogue_type=kind, task_flow=flow))
    return dialogues


def character_dialogues(result):
    dialogues = []
    for step in event_steps(result):
        for entry in step.dialogue:
            if entry.type == "选项":
                dialogues.extend(ArchonQuestDialogue(speaker="", text=text, dialogue_type="option", task_flow=step.title) for text in entry.options)
            else:
                kind = "narration" if entry.type == "旁白" else "traveler" if entry.type == "旅行者" else "character"
                dialogues.append(ArchonQuestDialogue(speaker=entry.speaker, text=entry.content, dialogue_type=kind, task_flow=step.title))
    return dialogues
