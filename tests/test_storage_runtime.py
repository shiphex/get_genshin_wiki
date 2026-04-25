"""新架构存储层与运行时测试。"""

import json
import shutil
from pathlib import Path

from src.content.arms.parser import Arm, ArmInfo
from src.content.arms.writer import ArmStorage
from src.content.artifacts.parser import Artifact, ArtifactInfo
from src.content.artifacts.writer import ArtifactStorage
from src.content.books.parser import Book, BookInfo, BookVolume
from src.content.books.writer import BookStorage
from src.content.runtime import run_crawl


OUTPUT_ROOT = Path("tests/output/runtime_suite")


class FakeClient:
    def __init__(self, pages: dict[str, str], base_url: str = "https://wiki.biligame.com/ys/"):
        self.pages = pages
        self.base_url = base_url

    def get_page_html(self, title: str) -> str:
        return self.pages[title]


def _reset_output_dir() -> None:
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def test_namespace_writers_create_unified_layout():
    _reset_output_dir()

    book = Book(title="测试书籍", url="https://wiki.biligame.com/ys/测试书籍", fetched_at="2026-04-25T10:00:00")
    book.info = BookInfo(name="测试书籍")
    book.volumes = [BookVolume(title="第一卷", content="段落一\n\n段落二")]
    book_storage = BookStorage(storage_config={"output_dir": str(OUTPUT_ROOT)})
    book_storage.save_book(book, raw_html="<html>book</html>")

    arm = Arm(title="测试武器", url="https://wiki.biligame.com/ys/测试武器", fetched_at="2026-04-25T10:00:00")
    arm.info = ArmInfo(名称="测试武器", 稀有度="5星")
    arm_storage = ArmStorage(storage_config={"output_dir": str(OUTPUT_ROOT)})
    arm_storage.save_arm(arm, raw_html="<html>arm</html>")

    artifact = Artifact(title="测试圣遗物", url="https://wiki.biligame.com/ys/测试圣遗物", fetched_at="2026-04-25T10:00:00")
    artifact.info = ArtifactInfo(套装名称="测试圣遗物", 稀有度="4-5星")
    artifact_storage = ArtifactStorage(storage_config={"output_dir": str(OUTPUT_ROOT)})
    artifact_storage.save_artifact(artifact, raw_html="<html>artifact</html>")

    for namespace in ["books", "arms", "artifacts"]:
        namespace_dir = OUTPUT_ROOT / namespace
        assert (namespace_dir / "raw").exists()
        assert (namespace_dir / "cleaned").exists()
        assert (namespace_dir / "structured").exists()
        assert (namespace_dir / "failed").exists()
        assert (namespace_dir / "manifests").exists()

    assert (OUTPUT_ROOT / "books/structured/books.jsonl").exists()
    assert (OUTPUT_ROOT / "arms/structured/arms.jsonl").exists()
    assert (OUTPUT_ROOT / "artifacts/structured/artifacts.jsonl").exists()


def test_run_crawl_generates_manifest_and_alerts():
    _reset_output_dir()
    list_html = """
    <html><body>
        <a href="/ys/测试书籍">测试书籍</a>
    </body></html>
    """
    detail_html = """
    <html><body>
        <table class="wikitable"><tr><th>名称</th><td>测试书籍</td></tr></table>
        <h2><span class="mw-headline" id="第一卷">第一卷</span></h2>
        <p>第一段</p>
        <p>第二段</p>
    </body></html>
    """
    config = {
        "mediawiki": {
            "api_url": "https://wiki.biligame.com/ys/api.php",
            "base_url": "https://wiki.biligame.com/ys/",
            "request_interval": 0,
            "timeout": 5,
            "max_retries": 1,
            "user_agent": "test-agent",
        },
        "storage": {
            "output_dir": str(OUTPUT_ROOT),
        },
    }

    result = run_crawl(
        "books",
        config,
        client=FakeClient({"书籍一览": list_html, "测试书籍": detail_html}),
    )

    assert result.manifest["namespace"] == "books"
    assert result.manifest["fetched_count"] == 1
    assert result.manifest["saved_count"] == 1
    assert result.manifest_path.exists()
    assert result.alerts_path.exists()
    assert (OUTPUT_ROOT / "books/cleaned/测试书籍.txt").exists()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["warning_count"] == 0
    alerts = json.loads(result.alerts_path.read_text(encoding="utf-8"))
    assert alerts == []
