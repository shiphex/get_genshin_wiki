"""Source-aware semantic extraction shared by recovery and legacy adapters."""
from __future__ import annotations

import re
from typing import Any, Callable

from mwparserfromhell.nodes import Heading, Tag, Template, Text

from .display import DISPLAY_TAGS, display_param, display_projection, display_text
from .source import SourcePage, nodes_with_spans, stable_id, tag_contents, template_params

Resolver = Callable[[str], list[dict[str, Any]]]
PLOT_HEADING = re.compile(r"^(?:任务剧情|剧情|对话|任务过程|任务内容)(?:$|[·：:])")
BUSINESS = {"任务", "任务信息", "角色资料", "角色/信息", "角色/故事", "角色展示", "武器", "武器属性", "武器故事", "圣遗物", "圣遗物属性", "书籍", "食物", "食物属性", "野生生物", "野生生物属性", "任务道具", "道具", "道具属性", "材料", "材料属性", "名片", "名片属性", "怪物", "怪物属性", "秘境", "秘境属性"}
BUSINESS.add("角色")
META = {"JS", "提示", "提示信息", "提示消息", "面包屑", "角色导航", "语音tab样式", "角色语音表头", "player", "图标", "原神WIKI导航", "!", "目录"}
VOICE = re.compile(r"角色/语音\d*$")
METADATA_FIELDS = {"任务名称", "名称", "名字", "任务地区", "地区", "国家", "任务类型", "类型", "任务条件", "条件", "任务流程", "系列任务", "相关活动", "活动", "时间", "活动时间", "所属版本", "版本", "实装版本", "前置任务", "后续任务", "并行任务", "出场人物", "相关角色", "奖励", "称号", "全名", "英文名称", "英文名", "稀有度", "所属", "种族", "元素", "武器", "武器类型", "性别", "命之座", "神之眼", "书籍名", "卷数", "体裁", "图鉴", "获取方式", "获取途径", "来源", "用途", "所需食材", "特殊料理", "特殊料理角色", "能否捕捉", "出现地点", "其他", "结尾", "冒险笔记名称"}
METADATA_FIELD_PATTERNS = re.compile(r"(?:卷\d+(?:名|获取地点)|章节(?:名称|奖励)\d+|开启需求\d+|段落名称\d+(?:\.\d+)*|.*(?:突破材料|技能材料|升级材料|基础攻击力|生命上限|攻击力|防御力|暴击率|暴击伤害|获取地点|获取方式))$")
REDIRECT = re.compile(r"^\s*#(?:重定向|redirect)\s*:?\s*\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", re.I)


class RecoveryExtractor:
    def __init__(self, parser, source: SourcePage, resolve_page: Resolver | None = None, visited=()):
        self.parser = parser
        self.page = source
        self.resolve_page = resolve_page
        self.visited = tuple(visited) + (source.identity,)
        self.units: list[dict] = []
        self.scenes: list[dict] = []
        self.issues: list[dict] = []
        self.dependencies: list[dict] = []
        self.regions: list[dict] = []
        self.character_owner = False

    def mark(self, start, end, disposition, reason):
        self.regions.append({"source": self.page.source(start, end), "disposition": disposition, "reason": reason})

    def issue(self, rule, start, end, status="unsupported", **extra):
        item = {"rule": rule, "status": status, "source": self.page.source(start, end),
                "raw": self.page.text[start:end], **extra}
        self.issues.append(item)
        self.mark(start, end, status, rule)

    def scene(self, title, start, end, *, chapter="", parent_id=None, body_type="dialogue", title_source=None):
        unknown = []
        cleaned = display_text(title, unknown=unknown)
        result = {"scene_id": stable_id("scene", self.page.identity, start, end), "title": cleaned,
                  "chapter": chapter, "parent_id": parent_id, "body_type": body_type, "source": self.page.source(start, end), "empty": True}
        self.scenes.append(result)
        if unknown:
            self.issue("unknown_scene_display", start, end)
        self.mark(start, end, "metadata", "scene_structure")
        title_source = title_source or self.page.source(start, end)
        result["title_source"] = title_source
        if title_source["start"] < title_source["end"]:
            left, right = title_source["start"], title_source["end"]
            _, _, unsupported = display_projection(self.page.text[left:right], left)
            for arg_start, arg_end, template_name, parameter in unsupported:
                self.issue("unsupported_display_argument", arg_start, arg_end, template=template_name, parameter=parameter)
        return result

    def run(self, *, transcluded=False):
        if self.page.missing:
            self.issue("missing_page", 0, len(self.page.text), "needs_source")
        elif not self.page.text:
            self.mark(0, 0, "metadata", "legitimate_empty_page")
        elif transcluded:
            self.transcluded_text()
        elif self.page.title.startswith(("模板:", "Template:")):
            self.issue("template_requires_consumer", 0, len(self.page.text))
        else:
            redirect = REDIRECT.match(self.page.text)
            if redirect:
                self.dependency(redirect.group(1).strip(), "redirect", 0, redirect.end())
                self.mark(0, redirect.end(), "metadata", "redirect_mapping")
            else:
                self.walk_root(self.page.text)
                if self.character_owner and not self.page.title.endswith("语音"):
                    self.dependency(self.page.title + "语音", "character_voice", 0, 0)
        merged = {}
        for unit in self.units:
            existing = merged.get(unit["unit_id"])
            if existing is None:
                merged[unit["unit_id"]] = unit
            else:
                for consumer in unit.get("consumed_by", []):
                    if consumer not in existing.setdefault("consumed_by", []):
                        existing["consumed_by"].append(consumer)
        self.units = list(merged.values())
        return {"source": self.page.source(), "units": self.units, "scenes": self.scenes,
                "issues": self.issues, "dependencies": self.dependencies, "regions": self.regions}

    def dependency(self, title, kind, start, end, *, scene=None, branch=None):
        record = {"consumer": self.page.source(start, end), "target_title": title, "kind": kind}
        candidates = self.resolve_page(title) if self.resolve_page else []
        if not candidates:
            record["status"] = "needs_source"
            self.issue("missing_dependency", start, end, "needs_source", target_title=title)
        elif len(candidates) != 1:
            record["status"] = "unresolved"
            self.issue("ambiguous_dependency", start, end, candidates=[c["raw_file"] for c in candidates])
        else:
            candidate = candidates[0]
            provider = SourcePage.from_payload(candidate["payload"], candidate["raw_file"])
            record["provider"] = provider.source()
            if provider.identity in self.visited:
                record["status"] = "unresolved"
                self.issue("redirect_cycle" if kind == "redirect" else "dependency_cycle", start, end)
            elif len(self.visited) >= 32:
                record["status"] = "unresolved"
                self.issue("dependency_depth_limit", start, end)
            elif provider.missing:
                record["status"] = "needs_source"
                self.issue("missing_dependency", start, end, "needs_source", target_title=title)
            else:
                worker = RecoveryExtractor(self.parser, provider, self.resolve_page, self.visited)
                consume_body = scene is not None and kind in {"template", "transclusion"}
                child = worker.run(transcluded=consume_body)
                record["status"] = "consumed" if child["units"] else "unresolved"
                record["unit_ids"] = [u["unit_id"] for u in child["units"]]
                for unit in child["units"]:
                    unit.setdefault("consumed_by", []).append({"page_id": self.page.page_id, "page_title": self.page.title,
                                                             "scene_id": scene["scene_id"] if scene else None, "branch_path": branch})
                self.units.extend(child["units"])
                self.scenes.extend(child["scenes"])
                self.issues.extend(child["issues"])
                self.dependencies.extend(child["dependencies"])
                self.regions.extend(child["regions"])
                if not child["units"]:
                    self.issue("dependency_has_no_supported_text", start, end)
        self.dependencies.append(record)

    def transcluded_text(self):
        """Render only an explicitly consumed, argument-free cached body."""
        scene = self.scene(self.page.title, 0, 0)
        onlyinclude = []

        def collect(raw, base):
            for node, start, _ in nodes_with_spans(raw, base):
                if isinstance(node, Tag):
                    name = str(node.tag).lower()
                    if name == "onlyinclude":
                        onlyinclude.append((node, start))
                    elif name not in {"noinclude", "style", "script"} and node.contents:
                        contents, content_start = tag_contents(node, start)
                        collect(contents, content_start)

        collect(self.page.text, 0)
        if onlyinclude:
            for node, start in onlyinclude:
                self.walk_container(node, start, scene, [], "dialogue")
        else:
            self.walk_prose(self.page.text, 0, scene, [], "dialogue")
        return {"source": self.page.source(), "units": self.units, "scenes": self.scenes,
                "issues": self.issues, "dependencies": self.dependencies, "regions": self.regions}

    def walk_root(self, raw):
        active_level = None
        chapter = ""
        current = None
        root_branch = []
        buffer_start = None
        buffer = ""

        def flush():
            nonlocal buffer, buffer_start, current
            if buffer.strip() and active_level is not None:
                if current is None:
                    current = self.scene(chapter, buffer_start, buffer_start, chapter=chapter)
                self.walk_prose(buffer, buffer_start, current, root_branch, "dialogue")
            buffer, buffer_start = "", None

        for node, start, end in nodes_with_spans(raw):
            if isinstance(node, Tag) and str(node.tag).lower() in {"noinclude", "style", "script"}:
                flush()
                self.mark(start, end, "non_story", "documentation_or_style")
            elif isinstance(node, Heading):
                flush()
                title = display_text(str(node.title))
                self.mark(start, end, "metadata", "heading")
                if active_level is not None and node.level <= active_level:
                    active_level, current = None, None
                if PLOT_HEADING.search(title):
                    active_level, chapter, current = node.level, title, None
                    root_branch = [{"kind": "condition", "group_id": stable_id("heading_branch", self.page.identity, start), "option_id": "heading", "label": title, "condition": title, "label_source": self.page.source(start, end)}] if "分支" in title else []
                elif active_level is not None:
                    current = self.scene(str(node.title), start, end, chapter=chapter)
            elif isinstance(node, Template) and (str(node.name).strip() in BUSINESS | {"剧情"} or VOICE.fullmatch(str(node.name).strip())):
                flush()
                self.business_template(node, start, end)
            elif active_level is not None:
                if buffer_start is None:
                    buffer_start = start
                buffer += str(node)
            elif isinstance(node, Template):
                self.template(node, start, end, None, [], "dialogue", outside=True)
            elif isinstance(node, Tag) and str(node.tag).lower() in {"div", "poem", "p", "center", "onlyinclude", "includeonly", "noinclude"}:
                contents, content_start = tag_contents(node, start)
                # Voice templates often live in display containers.
                for child, child_start, child_end in nodes_with_spans(contents, content_start):
                    if isinstance(child, Template):
                        self.template(child, child_start, child_end, None, [], "dialogue", outside=True)
                    elif isinstance(child, Tag):
                        self.walk_container(child, child_start, None, [], "dialogue", outside=True)
        flush()

    def business_template(self, template, start, end, *, branch=(), parent_scene=None):
        branch = None if branch is None else list(branch)
        name = str(template.name).strip()
        if name in {"角色", "角色资料", "角色/信息"}:
            self.character_owner = True
        params = list(template_params(template, start))
        by_name = {p[0]: p for p in params}
        if name == "剧情":
            for key, value, value_start, value_end in params:
                match = re.fullmatch(r"内容(\d+(?:\.\d+)*)", key)
                if match:
                    suffix = match.group(1)
                    title_param = by_name.get("段落名称" + suffix)
                    chapter_param = by_name.get("章节名称" + suffix.split(".")[0])
                    title = title_param[1] if title_param else ""
                    scene = self.scene(title, title_param[2] if title_param else value_start,
                                       title_param[3] if title_param else value_start,
                                       chapter=display_text(chapter_param[1]) if chapter_param else "",
                                       parent_id=parent_scene["scene_id"] if parent_scene else None)
                    self.walk_prose(value, value_start, scene, branch, "dialogue")
                elif re.fullmatch(r"章节简述\d+", key):
                    scene = self.scene(key, value_start, value_start, body_type="description")
                    self.walk_prose(value, value_start, scene, branch, "description")
                else:
                    self.business_metadata(key, value, value_start, value_end)
            return
        for key, value, value_start, value_end in params:
            text_type = None
            label = key
            label_source = None
            if VOICE.fullmatch(name):
                if key == "语音内容":
                    text_type = "voice"
                    label_param = by_name.get("语音类型")
                    label = label_param[1] if label_param else key
                    label_source = self.page.source(label_param[2], label_param[3]) if label_param else None
            elif name == "书籍":
                volume = re.fullmatch(r"卷(\d+)(内容|描述)", key)
                if volume:
                    text_type = "book" if volume.group(2) == "内容" else "description"
                    label_param = by_name.get("卷" + volume.group(1) + "名")
                    label = label_param[1] if label_param else key
                    label_source = self.page.source(label_param[2], label_param[3]) if label_param else None
            elif name == "角色/故事":
                if re.fullmatch(r"角色详细|角色故事\d+|冒险笔记内容|其他故事\d*", key):
                    text_type = "story"
            elif name == "角色展示" and key in {"壹·人物", "贰·故事"}:
                text_type = "story"
            elif key in {"任务剧情", "剧情", "对话", "任务对话"} and name in {"任务", "任务信息"}:
                text_type = "dialogue"
            elif key in {"任务描述", "介绍", "描述", "故事", "内容", "神之眼描述"} or re.fullmatch(r"(?:时之沙|死之羽|理之冠|生之花|空之杯)(?:描述|故事)", key):
                text_type = "story" if key.endswith("故事") else "description"
            if text_type:
                scene = self.scene(label, value_start, value_start, body_type=text_type, parent_id=parent_scene["scene_id"] if parent_scene else None, title_source=label_source)
                self.walk_prose(value, value_start, scene, branch, text_type)
            else:
                if VOICE.fullmatch(name) and (key == "语音类型" or key.startswith("语音文件") or key in {"语音内容日语", "语音内容英语", "语音内容韩语"}):
                    self.mark(value_start, value_end, "metadata", "voice_metadata_or_other_language")
                else:
                    self.business_metadata(key, value, value_start, value_end)

    def business_metadata(self, key, value, start, end):
        if not value.strip() or key in METADATA_FIELDS or METADATA_FIELD_PATTERNS.fullmatch(key):
            self.mark(start, end, "metadata", "known_business_metadata" if value.strip() else "legitimate_empty_field")
        else:
            self.issue("unsupported_business_field", start, end, parameter=key)

    def walk_container(self, node, start, scene, branch, kind, outside=False):
        contents, content_start = tag_contents(node, start)
        if outside:
            for child, child_start, child_end in nodes_with_spans(contents, content_start):
                if isinstance(child, Template):
                    self.template(child, child_start, child_end, scene, branch, kind, outside=True)
                elif isinstance(child, Tag):
                    self.walk_container(child, child_start, scene, branch, kind, outside=True)
        else:
            self.walk_prose(contents, content_start, scene, branch, kind)

    def walk_prose(self, raw, start, scene, branch, kind):
        buffer, buffer_start = "", None

        def flush():
            nonlocal buffer, buffer_start
            if buffer:
                self.lines(buffer, buffer_start, scene, branch, kind)
            buffer, buffer_start = "", None

        for node, node_start, node_end in nodes_with_spans(raw, start):
            if isinstance(node, Heading):
                flush()
                scene = self.scene(str(node.title), node_start, node_end, chapter=scene["chapter"] if scene else "", body_type=kind)
                continue
            name = str(node.name).strip() if isinstance(node, Template) else ""
            if isinstance(node, Tag) and str(node.tag).lower() in {"noinclude", "style", "script", "ref", "references"}:
                flush()
                self.mark(node_start, node_end, "non_story", "documentation_or_style")
                continue
            structural = isinstance(node, Template) and (name in {"剧情选项", "选项", "折叠", "折叠框", "剧情", "#tag:tabber"} or "人物对话" in name or name in BUSINESS or VOICE.fullmatch(name) or name.startswith(":") or name in META)
            if isinstance(node, Template) and not structural and self.resolve_page and name not in {"颜色", "注音", "黑幕", "任务描述", "切换板", "玩家名", "旅行者名字", "NICKNAME"}:
                structural = bool(self.resolve_page(name if name.startswith(("模板:", "Template:")) else "模板:" + name))
            container = isinstance(node, Tag) and (str(node.tag).lower() in {"tabber", "div", "poem", "p", "center", "blockquote", "includeonly", "onlyinclude"} or (str(node.tag).lower() in DISPLAY_TAGS and "\n" in str(node.contents)))
            if structural or container:
                flush()
                if structural:
                    self.template(node, node_start, node_end, scene, branch, kind)
                elif str(node.tag).lower() == "tabber":
                    content, content_start = tag_contents(node, node_start)
                    self.tabber(content, content_start, scene, branch, kind, node_start)
                else:
                    self.walk_container(node, node_start, scene, branch, kind)
            else:
                if buffer_start is None:
                    buffer_start = node_start
                buffer += str(node)
        flush()

    def lines(self, raw, start, scene, branch, kind):
        # Newlines inside inline display nodes remain part of that node.
        cursor, line_start, parts = start, start, []
        for node, node_start, node_end in nodes_with_spans(raw, start):
            if isinstance(node, Text):
                for segment in str(node).splitlines(keepends=True):
                    parts.append(segment)
                    cursor += len(segment)
                    if segment.endswith(("\n", "\r")):
                        self.emit("".join(parts), line_start, scene, branch, kind)
                        line_start, parts = cursor, []
            else:
                parts.append(str(node))
                cursor = node_end
        if parts:
            self.emit("".join(parts), line_start, scene, branch, kind)

    def emit(self, raw, start, scene, branch, kind, speaker_override=None, speaker_source=None, speaker_status="resolved"):
        wiki_annotation = raw.lstrip().startswith("::") or "{{黑幕" in raw
        prefix = re.match(r"[\s*:>#]*", raw).group()
        if kind in {"dialogue", "option"}:
            start += len(prefix)
            raw = raw[len(prefix):]
        whitespace = len(raw) - len(raw.lstrip())
        start += whitespace
        raw = raw.strip()
        if not raw:
            return
        speaker = speaker_override
        if kind == "dialogue" and "剧情选项-图标" in raw:
            kind, branch = "option", None
        if kind == "dialogue" and speaker_override is None:
            split = None
            for node, node_start, node_end in nodes_with_spans(raw, start):
                if isinstance(node, Text) and "：" in str(node):
                    split = node_start + str(node).index("：") - start
                    break
            if split is not None:
                unknown_speaker = []
                speaker = display_text(raw[:split], unknown=unknown_speaker)
                speaker_source = self.page.source(start, start + split)
                if unknown_speaker:
                    self.issue("unknown_speaker_display", start, start + split)
                    speaker = ""
                    speaker_status = "unresolved"
                raw, start = raw[split + 1:], start + split + 1
                whitespace = len(raw) - len(raw.lstrip())
                raw, start = raw.strip(), start + whitespace
                kind = "narration" if speaker == "旁白" else "dialogue"
                if speaker == "选项":
                    kind, speaker, branch = "option", None, None
            else:
                kind, speaker = "narration", None
        unknown = []
        rendered = display_text(raw, unknown=unknown)
        if unknown:
            self.issue("unknown_template", start, start + len(raw), templates=unknown)
            return
        if not rendered:
            return
        if re.fullmatch(r"[-_=★\s]+", rendered):
            return
        source = self.page.source(start, start + len(raw))
        visible, metadata, unsupported = display_projection(raw, start)
        for left, right in metadata:
            self.mark(left, right, "metadata", "display_presentation")
        for left, right, template_name, parameter in unsupported:
            self.issue("unsupported_display_argument", left, right, template=template_name, parameter=parameter)
        source_kind = "wiki_editorial" if wiki_annotation else "unknown" if kind == "description" else "game_excerpt"
        unit = {"unit_id": stable_id("unit", self.page.identity, source["wikitext_sha256"], start, start + len(raw), kind),
                "type": kind, "text": rendered, "speaker": speaker, "scene_id": scene["scene_id"] if scene else None,
                "speaker_status": "not_applicable" if speaker is None else speaker_status,
                "branch_path": branch, "branch_status": "unresolved" if branch is None else "resolved",
                "source": source, "source_kind": source_kind}
        unit["text_spans"] = [self.page.source(left, right) for left, right in visible]
        unit["display_status"] = "partial" if unsupported else "resolved"
        if speaker_source:
            unit["speaker_source"] = speaker_source
            _, speaker_metadata, speaker_unknown = display_projection(self.page.text[speaker_source["start"]:speaker_source["end"]], speaker_source["start"])
            for left, right in speaker_metadata:
                self.mark(left, right, "metadata", "speaker_display_presentation")
            for left, right, template_name, parameter in speaker_unknown:
                self.issue("unsupported_display_argument", left, right, template=template_name, parameter=parameter)
        self.units.append(unit)
        if scene:
            scene["empty"] = False
        for left, right in visible:
            self.mark(left, right, "exported", "visible_text_leaf")

    def template(self, node, start, end, scene, branch, kind, outside=False):
        name = str(node.name).strip()
        params = list(template_params(node, start))
        by_name = {p[0]: p for p in params}
        if name in BUSINESS | {"剧情"} or VOICE.fullmatch(name):
            self.business_template(node, start, end, branch=branch, parent_scene=scene)
        elif name in {"剧情选项", "选项"}:
            group_id = stable_id("choice", self.page.identity, start)
            suffixes = sorted({int(m.group(1)) for key in by_name if (m := re.fullmatch(r"(?:选项|剧情|选择)(\d+)", key))})
            for number in suffixes:
                option = by_name.get("选项" + str(number))
                response = by_name.get("剧情" + str(number)) or by_name.get("选择" + str(number))
                unknown_label = []
                label = display_text(option[1], unknown=unknown_label) if option else ""
                step = {"kind": "choice", "group_id": group_id, "option_id": str(number), "label": label, "condition": None,
                        "group_source": self.page.source(start, end),
                        "label_source": self.page.source(option[2], option[3]) if option else None,
                        "content_source": self.page.source(response[2], response[3]) if response else None}
                path = None if branch is None or not label or unknown_label else branch + [step]
                if option:
                    self.emit(option[1], option[2], scene, path, "option")
                if response:
                    if path is None:
                        self.issue("unresolved_choice", response[2], response[3])
                    self.walk_prose(response[1], response[2], scene, path, kind)
            if not suffixes:
                self.issue("unsupported_choice_shape", start, end)
        elif name == "#tag:tabber":
            body_start = start + 3 + len(str(node.name))
            self.tabber(str(node)[body_start - start:-2], body_start, scene, branch, kind, start)
        elif name in {"折叠", "折叠框"}:
            selected = next((by_name[key] for key in ("内容", "2") if key in by_name), None)
            if selected:
                label = display_text(by_name.get("标题", ("", ""))[1])
                path = branch
                if label and re.search(r"额外对话|可选|如果|条件", label):
                    title_param = by_name.get("标题")
                    path = None if branch is None else branch + [{"kind": "condition", "group_id": stable_id("condition", self.page.identity, start), "option_id": "content", "label": label, "condition": label,
                                                                "label_source": self.page.source(title_param[2], title_param[3]), "content_source": self.page.source(selected[2], selected[3])}]
                self.walk_prose(selected[1], selected[2], scene, path, kind)
                for param in params:
                    if param != selected:
                        if param[0] in {"标题", "折叠", "1", "展开", "宽度", "样式", "class", "style"}:
                            self.mark(param[2], param[3], "metadata", "fold_display_metadata")
                        else:
                            self.issue("unsupported_fold_argument", param[2], param[3], parameter=param[0])
            else:
                self.issue("unsupported_fold_shape", start, end)
        elif "人物对话" in name:
            speaker_param = next((by_name[k] for k in ("角色", "2", "1") if k in by_name), None)
            content = next((by_name[k] for k in ("内容", "3") if k in by_name), None)
            if content:
                unknown_speaker = []
                speaker = display_text(speaker_param[1], unknown=unknown_speaker) if speaker_param else ""
                if unknown_speaker:
                    self.issue("unknown_speaker_display", speaker_param[2], speaker_param[3])
                    speaker = ""
                self.emit(content[1], content[2], scene, branch, "dialogue", speaker_override=speaker,
                          speaker_source=self.page.source(speaker_param[2], speaker_param[3]) if speaker_param else None,
                          speaker_status="unresolved" if unknown_speaker else "resolved")
            else:
                self.issue("unsupported_dialogue_shape", start, end)
        elif name.startswith(":"):
            if params:
                self.issue("unsupported_template_arguments", start, end)
            else:
                self.dependency(name[1:].strip(), "transclusion", start, end, scene=scene, branch=branch)
        elif name in META or name.startswith(("DISPLAYTITLE:", "#info:", "#css:")):
            self.mark(start, end, "non_story", "wiki_presentation")
        elif outside and display_param(node) is not None:
            selected = display_param(node)
            for key, raw, raw_start, raw_end in params:
                if key == str(selected.name).strip():
                    self.walk_prose(raw, raw_start, scene, branch, "description")
                else:
                    self.mark(raw_start, raw_end, "metadata", "display_metadata")
        else:
            target = name if name.startswith(("模板:", "Template:")) else "模板:" + name
            if self.resolve_page and self.resolve_page(target) and not name.startswith("#"):
                if params:
                    self.issue("unsupported_template_arguments", start, end)
                else:
                    self.dependency(target, "template", start, end, scene=scene, branch=branch)
            else:
                self.issue("unknown_template", start, end)

    def tabber(self, raw, start, scene, branch, kind, group_start):
        node_spans = list(nodes_with_spans(raw, start))
        delimiters = []
        for match in re.finditer(r"\{\{!\}\}-\{\{!\}\}|\|-\|", raw):
            absolute = start + match.start()
            if any(s <= absolute < e and (not isinstance(node, Template) or str(node.name).strip() == "!") and (isinstance(node, Text) or isinstance(node, Template)) for node, s, e in node_spans):
                delimiters.append((match.start(), match.end()))
        previous = 0
        parts = []
        for left, right in delimiters:
            parts.append((previous, left))
            previous = right
        parts.append((previous, len(raw)))
        group_id = stable_id("tab", self.page.identity, group_start)
        for index, (left, right) in enumerate(parts):
            segment = raw[left:right]
            label_match = re.match(r"\s*([^=\n]+)=", segment)
            if not label_match:
                self.issue("unresolved_tab", start + left, start + right)
                self.walk_prose(segment, start + left, scene, None, kind)
                continue
            unknown_label = []
            label = display_text(label_match.group(1), unknown=unknown_label)
            if unknown_label:
                self.issue("unresolved_tab_label", start + left + label_match.start(1), start + left + label_match.end(1))
            path = None if branch is None or unknown_label else branch + [{"kind": "tab", "group_id": group_id, "option_id": str(index + 1), "label": label, "condition": label,
                                                        "label_source": self.page.source(start + left + label_match.start(1), start + left + label_match.end(1)),
                                                        "content_source": self.page.source(start + left + label_match.end(), start + right)}]
            self.mark(start + left, start + left + label_match.end(), "metadata", "tab_condition")
            self.walk_prose(segment[label_match.end():], start + left + label_match.end(), scene, path, kind)


def recover_page(parser, payload, *, raw_file="", resolve_page=None):
    return RecoveryExtractor(parser, SourcePage.from_payload(payload, raw_file), resolve_page).run()
