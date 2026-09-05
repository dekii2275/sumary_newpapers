import gzip
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import crawl_to_db as crawler
except ModuleNotFoundError:  # pragma: no cover - local environment may lack deps
    crawler = None


@unittest.skipUnless(crawler, "crawler runtime dependencies are not installed")
class LocalStorageTests(unittest.TestCase):
    def test_atomic_storage_writes_v2_and_reuses_retry_path(self):
        original_root = crawler.PROJECT_ROOT
        original_output = crawler.OUTPUT_ROOT
        with tempfile.TemporaryDirectory() as temporary_dir:
            temporary_root = Path(temporary_dir)
            crawler.PROJECT_ROOT = temporary_root
            crawler.OUTPUT_ROOT = temporary_root / "crawl_data"
            run_id = uuid4()
            url = "https://example.com/article"
            article = {"title": "Title", "content": "Content", "author": None,
                       "published_at": None, "thumbnail_url": None}
            first_key, first_hash = crawler.save_artifacts(
                "<html>one</html>",
                "vnexpress",
                url,
                datetime.now(timezone.utc),
                article,
                crawl_run_id=run_id,
            )
            second_key, second_hash = crawler.save_artifacts(
                "<html>different retry payload</html>",
                "vnexpress",
                url,
                datetime.now(timezone.utc),
                article,
                crawl_run_id=run_id,
            )
            self.assertEqual(first_key, second_key)
            self.assertEqual(first_hash, second_hash)

            raw_files = list((temporary_root / "crawl_data" / "raw").rglob("*.html.gz"))
            self.assertEqual(len(raw_files), 1)
            with gzip.open(raw_files[0], "rt", encoding="utf-8") as raw_file:
                self.assertEqual(raw_file.read(), "<html>one</html>")

            metadata_files = list(
                (temporary_root / "crawl_data" / "metadata").rglob("*.json")
            )
            self.assertEqual(len(metadata_files), 1)
            metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
            self.assertEqual(metadata["schema_version"], 2)
            self.assertEqual(metadata["raw_object_key"], first_key)
        crawler.PROJECT_ROOT = original_root
        crawler.OUTPUT_ROOT = original_output


if __name__ == "__main__":
    unittest.main()
