import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from crawl_contract import normalize_url  # noqa: E402


class UrlNormalizationTests(unittest.TestCase):
    def test_tracking_fragments_host_case_and_default_port(self):
        self.assertEqual(
            normalize_url(
                " HTTPS://EXAMPLE.COM:443/news?id=10&utm_source=feed#comments "
            ),
            "https://example.com/news?id=10",
        )

    def test_empty_path_is_preserved_as_root(self):
        self.assertEqual(normalize_url("https://example.com"), "https://example.com/")

    def test_meaningful_trailing_slash_is_not_removed(self):
        self.assertEqual(
            normalize_url("https://example.com/category/"),
            "https://example.com/category/",
        )

    def test_invalid_urls_are_rejected(self):
        for value in ("", "example.com/article", "ftp://example.com/a"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_url(value)


if __name__ == "__main__":
    unittest.main()
