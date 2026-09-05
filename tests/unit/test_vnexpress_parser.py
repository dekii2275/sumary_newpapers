import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from crawl_to_db import VnExpressParser
except ModuleNotFoundError:  # pragma: no cover - local environment may lack deps
    VnExpressParser = None


@unittest.skipUnless(VnExpressParser, "crawler runtime dependencies are not installed")
class VnExpressParserTests(unittest.TestCase):
    def setUp(self):
        fixture_root = ROOT / "tests" / "fixtures" / "vnexpress"
        self.fixture_root = fixture_root
        self.parser = VnExpressParser()

    def read(self, name: str) -> str:
        return (self.fixture_root / name).read_text(encoding="utf-8")

    def test_normal_article(self):
        article = self.parser.parse(self.read("normal.html"))
        self.assertEqual(article["title"], "A normal VnExpress article")
        self.assertEqual(article["author"], "Author Name")
        self.assertIn("First paragraph", article["content"])
        self.assertEqual(article["thumbnail_url"], "https://example.com/thumb.jpg")

    def test_missing_author_is_allowed(self):
        article = self.parser.parse(self.read("missing_author.html"))
        self.assertIsNone(article["author"])
        self.assertEqual(article["published_at"], "2026-08-26T08:30:00+07:00")
        self.assertTrue(article["content"])

    def test_empty_content_is_reported_as_none(self):
        article = self.parser.parse(self.read("no_content.html"))
        self.assertIsNone(article["content"])

    def test_blocked_page_has_no_article_body(self):
        article = self.parser.parse(self.read("blocked.html"))
        self.assertIsNone(article["content"])


if __name__ == "__main__":
    unittest.main()
