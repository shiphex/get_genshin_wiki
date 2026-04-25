"""Arms writer backed by shared storage modules."""

from __future__ import annotations

from src.storage.base_storage import BaseNamespaceStorage


class ArmStorage(BaseNamespaceStorage):
    """武器数据存储器"""

    namespace = "arms"

    def build_clean_text(self, record) -> str:
        lines = [f"# {record.info.名称}", ""]
        if record.info.稀有度:
            lines.extend([f"稀有度：{record.info.稀有度}", ""])
        if record.info.性能描述文本:
            lines.extend([f"性能描述：{record.info.性能描述文本}", ""])
        if record.info.武器技能:
            lines.extend([f"武器技能：{record.info.武器技能}", ""])
        if record.info.武器技能文本描述:
            lines.extend([f"技能描述：{record.info.武器技能文本描述}", ""])
        if record.info.武器介绍:
            lines.extend(["武器介绍：", record.info.武器介绍, ""])
        if record.info.突破材料:
            lines.extend([f"突破材料：{', '.join(record.info.突破材料)}", ""])
        if record.info.获取途径:
            lines.extend([f"获取途径：{record.info.获取途径}", ""])
        if record.info.武器类型:
            lines.extend([f"武器类型：{record.info.武器类型}", ""])
        if record.info.武器TAG:
            lines.extend([f"武器TAG：{record.info.武器TAG}", ""])
        if record.info.故事:
            lines.extend(["故事：", record.info.故事, ""])
        return "\n".join(lines).strip() + "\n"

    def save_arm(self, arm, raw_html: str = "") -> None:
        self.save(record=arm, raw_html=raw_html, structured=arm.to_dict())

    def save_failed_arm(self, title: str, reason: str) -> None:
        self.save_failed(title, reason)

    def load_saved_arms(self) -> set[str]:
        return self.load_saved_titles()

    def load_failed_arms(self) -> set[str]:
        return self.load_failed_titles()
