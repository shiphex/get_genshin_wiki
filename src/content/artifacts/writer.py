"""Artifacts writer backed by shared storage modules."""

from __future__ import annotations

from src.storage.base_storage import BaseNamespaceStorage


class ArtifactStorage(BaseNamespaceStorage):
    """圣遗物数据存储器"""

    namespace = "artifacts"

    def build_clean_text(self, record) -> str:
        lines = [f"# {record.info.套装名称 or record.title}", ""]
        if record.info.稀有度:
            lines.extend([f"稀有度：{record.info.稀有度}", ""])
        if record.info.TAG:
            lines.extend([f"TAG：{record.info.TAG}", ""])
        if record.info.实装版本:
            lines.extend([f"实装版本：{record.info.实装版本}", ""])
        if record.info.两件套效果:
            lines.extend([f"2件套：{record.info.两件套效果}", ""])
        if record.info.四件套效果:
            lines.extend([f"4件套：{record.info.四件套效果}", ""])
        lines.extend(["## 部件", ""])
        for piece in record.info.部件列表:
            lines.extend([f"### {piece.类型} - {piece.名称}", ""])
            if piece.描述:
                lines.extend([piece.描述, ""])
            if piece.故事:
                lines.extend([piece.故事, ""])
        if record.info.获取途径:
            lines.extend(["## 获取途径", ""])
            for item in record.info.获取途径:
                parts = [item.类型]
                if item.副本类型:
                    parts.append(item.副本类型)
                if item.副本名称:
                    parts.append(item.副本名称)
                if item.副本等级:
                    parts.append(item.副本等级)
                if item.NPC姓名:
                    parts.append(item.NPC姓名)
                if item.获取方式:
                    parts.append(item.获取方式)
                if item.详细描述:
                    parts.append(item.详细描述)
                lines.extend([" - ".join(parts), ""])
        return "\n".join(lines).strip() + "\n"

    def save_artifact(self, artifact, raw_html: str = "") -> None:
        self.save(record=artifact, raw_html=raw_html, structured=artifact.to_dict())

    def save_failed_artifact(self, title: str, reason: str) -> None:
        self.save_failed(title, reason)

    def load_saved_artifacts(self) -> set[str]:
        return self.load_saved_titles()

    def load_failed_artifacts(self) -> set[str]:
        return self.load_failed_titles()
