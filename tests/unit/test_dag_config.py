import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from crawl_config import (  # noqa: E402
    parse_configured_urls,
    schedule_for_manual_urls,
    stable_crawl_run_id,
)
from crawl_contract import normalize_url  # noqa: E402


class DagConfigTests(unittest.TestCase):
    def test_empty_urls_disable_schedule(self):
        self.assertIsNone(schedule_for_manual_urls("", "0 */6 * * *"))
        self.assertEqual(
            schedule_for_manual_urls(" https://example.com/a ", "0 */6 * * *"),
            "0 */6 * * *",
        )

    def test_urls_are_normalized_and_deduplicated(self):
        urls = parse_configured_urls(
            " https://EXAMPLE.com:443/a?utm_source=x&id=1,https://example.com/a?id=1, ",
            normalize_url,
        )
        self.assertEqual(urls, ["https://example.com/a?id=1"])

    def test_invalid_url_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "invalid URL"):
            parse_configured_urls("not-a-url", normalize_url)

    def test_run_id_is_stable_for_retries(self):
        first = stable_crawl_run_id("crawl_vnexpress_step1", "manual__abc")
        second = stable_crawl_run_id("crawl_vnexpress_step1", "manual__abc")
        other = stable_crawl_run_id("crawl_vnexpress_step1", "manual__def")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)


if __name__ == "__main__":
    unittest.main()
