"""存储模块 - 武器数据写入"""
import json
import logging
from pathlib import Path

from src.parser.arms_parser import Arm

logger = logging.getLogger(__name__)


class ArmStorage:
    """武器数据存储器"""

    def __init__(self, base_dir: str = "storage/arm"):
        self.base_dir = Path(base_dir)
        self.raw_dir = self.base_dir / "raw"
        self.clean_dir = self.base_dir / "cleaned"

        # 确保目录存在
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.clean_dir.mkdir(parents=True, exist_ok=True)

        self.arms_file = self.base_dir / "arms.jsonl"
        self.failed_file = self.base_dir / "failed_arms.txt"

    def save_arm(self, arm: Arm) -> None:
        """保存单件武器数据

        Args:
            arm: Arm 对象
        """
        try:
            # 保存为 JSONL（结构化数据）
            with open(self.arms_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(arm.to_dict(), ensure_ascii=False) + "\n")

            # 保存清洗后的纯文本
            clean_file = self.clean_dir / f"{arm.title}.txt"
            with open(clean_file, "w", encoding="utf-8") as f:
                # 写入武器信息
                f.write(f"# {arm.info.名称}\n\n")
                f.write(f"稀有度：{arm.info.稀有度}\n\n")
                if arm.info.性能描述文本:
                    f.write(f"性能描述：{arm.info.性能描述文本}\n\n")
                if arm.info.武器技能:
                    f.write(f"武器技能：{arm.info.武器技能}\n\n")
                if arm.info.武器技能文本描述:
                    f.write(f"技能描述：{arm.info.武器技能文本描述}\n\n")
                if arm.info.武器介绍:
                    f.write(f"武器介绍：\n{arm.info.武器介绍}\n\n")
                if arm.info.突破材料:
                    f.write(f"突破材料：{', '.join(arm.info.突破材料)}\n\n")
                if arm.info.获取途径:
                    f.write(f"获取途径：{arm.info.获取途径}\n\n")
                if arm.info.武器类型:
                    f.write(f"武器类型：{arm.info.武器类型}\n\n")
                if arm.info.武器TAG:
                    f.write(f"武器TAG：{arm.info.武器TAG}\n\n")
                if arm.info.故事:
                    f.write(f"故事：\n{arm.info.故事}\n\n")

            logger.info(f"已保存武器: {arm.title}")

        except Exception as e:
            logger.error(f"保存武器失败 {arm.title}: {e}")
            raise

    def save_failed_arm(self, title: str, reason: str) -> None:
        """记录失败的武器

        Args:
            title: 武器标题
            reason: 失败原因
        """
        with open(self.failed_file, "a", encoding="utf-8") as f:
            f.write(f"{title}\t{reason}\n")

    def load_saved_arms(self) -> set[str]:
        """加载已保存的武器标题集合

        Returns:
            已保存的武器标题集合
        """
        saved = set()
        if self.arms_file.exists():
            with open(self.arms_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        saved.add(data["title"])
                    except json.JSONDecodeError:
                        continue
        return saved

    def load_failed_arms(self) -> set[str]:
        """加载已失败的武器标题集合

        Returns:
            已失败的武器标题集合
        """
        failed = set()
        if self.failed_file.exists():
            with open(self.failed_file, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if parts:
                        failed.add(parts[0])
        return failed
