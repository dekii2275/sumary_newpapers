import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from reconcile_crawl_artifacts import reconcile  # noqa: E402


class ReconcileTests(unittest.TestCase):
    def test_orphan_and_legacy_metadata_are_reported(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            project_root = Path(temporary_dir)
            raw_path = project_root / "crawl_data" / "raw" / "vnexpress" / "orphan.html.gz"
            metadata_path = (
                project_root / "crawl_data" / "metadata" / "vnexpress" / "legacy.json"
            )
            raw_path.parent.mkdir(parents=True)
            metadata_path.parent.mkdir(parents=True)
            payload = "legacy raw html"
            with gzip.open(raw_path, "wt", encoding="utf-8") as raw_file:
                raw_file.write(payload)
            metadata_path.write_text(
                json.dumps(
                    {
                        "source": "vnexpress",
                        "raw_html_path": raw_path.relative_to(project_root).as_posix(),
                        "crawl_status": "SUCCESS",
                    }
                ),
                encoding="utf-8",
            )
            report = reconcile(project_root=project_root, db_rows=[])
            self.assertEqual(len(report["legacy_metadata_without_database_reference"]), 1)
            self.assertEqual(len(report["raw_files_without_database_row"]), 1)
            self.assertEqual(report["hash_mismatches"], [])


if __name__ == "__main__":
    unittest.main()
