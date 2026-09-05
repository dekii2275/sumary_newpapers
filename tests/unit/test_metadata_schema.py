import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from crawl_contract import (  # noqa: E402
    METADATA_FIELDS,
    metadata_schema_version,
    validate_metadata,
)


class MetadataSchemaTests(unittest.TestCase):
    def setUp(self):
        fixture_root = ROOT / "tests" / "fixtures" / "metadata"
        self.success = json.loads((fixture_root / "v2_success.json").read_text())
        self.failed = json.loads((fixture_root / "v2_failed.json").read_text())

    def test_success_metadata_validates(self):
        self.assertEqual(validate_metadata(self.success), 2)
        self.assertTrue(set(METADATA_FIELDS).issubset(self.success))

    def test_failed_metadata_and_optional_fields_validate(self):
        self.assertEqual(validate_metadata(self.failed), 2)
        self.assertIsNone(self.failed["author"])
        self.assertIsNone(self.failed["published_at"])

    def test_legacy_metadata_is_not_treated_as_v2(self):
        legacy = {
            "source": "vnexpress",
            "raw_html_path": "crawl_data/raw/example.html.gz",
            "crawl_status": "SUCCESS",
        }
        self.assertEqual(metadata_schema_version(legacy), 1)
        with self.assertRaises(ValueError):
            validate_metadata(legacy)
        self.assertEqual(validate_metadata(legacy, allow_legacy=True), 1)

    def test_missing_v2_field_is_rejected(self):
        invalid = dict(self.success)
        del invalid["crawl_run_id"]
        with self.assertRaisesRegex(ValueError, "crawl_run_id"):
            validate_metadata(invalid)


if __name__ == "__main__":
    unittest.main()
