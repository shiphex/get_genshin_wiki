"""存储模块 - 圣遗物数据写入"""
import json
import logging
from pathlib import Path

from src.parser.artifacts_parser import Artifact

logger = logging.getLogger(__name__)


class ArtifactStorage:
    """圣遗物数据存储器"""

    def __init__(self, base_dir: str = "storage/artifacts"):
        self.base_dir = Path(base_dir)

        # 确保目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.artifacts_file = self.base_dir / "artifacts.jsonl"
        self.failed_file = self.base_dir / "failed_artifacts.txt"

    def save_artifact(self, artifact: Artifact) -> None:
        """保存单件圣遗物数据

        Args:
            artifact: Artifact 对象
        """
        try:
            # 保存为 JSONL（结构化数据）
            with open(self.artifacts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(artifact.to_dict(), ensure_ascii=False) + "\n")

            logger.info(f"已保存圣遗物: {artifact.title}")

        except Exception as e:
            logger.error(f"保存圣遗物失败 {artifact.title}: {e}")
            raise

    def save_failed_artifact(self, title: str, reason: str) -> None:
        """记录失败的圣遗物

        Args:
            title: 圣遗物标题
            reason: 失败原因
        """
        with open(self.failed_file, "a", encoding="utf-8") as f:
            f.write(f"{title}\t{reason}\n")

    def load_saved_artifacts(self) -> set:
        """加载已保存的圣遗物标题集合

        Returns:
            已保存的圣遗物标题集合
        """
        saved = set()
        if self.artifacts_file.exists():
            with open(self.artifacts_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        saved.add(data["title"])
                    except json.JSONDecodeError:
                        continue
        return saved

    def load_failed_artifacts(self) -> set:
        """加载已失败的圣遗物标题集合

        Returns:
            已失败的圣遗物标题集合
        """
        failed = set()
        if self.failed_file.exists():
            with open(self.failed_file, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if parts:
                        failed.add(parts[0])
        return failed
