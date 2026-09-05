import os
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import crawl_to_db as crawler
except ModuleNotFoundError:  # pragma: no cover - local environment may lack deps
    crawler = None


@unittest.skipUnless(crawler, "crawler runtime dependencies are not installed")
class RetryIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.original_root = crawler.PROJECT_ROOT
        self.original_output = crawler.OUTPUT_ROOT
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp_dir.name)
        crawler.PROJECT_ROOT = self.temp_root
        crawler.OUTPUT_ROOT = self.temp_root / "crawl_data"

    def tearDown(self):
        crawler.PROJECT_ROOT = self.original_root
        crawler.OUTPUT_ROOT = self.original_output
        self.temp_dir.cleanup()

    def test_one_failed_url_does_not_stop_next_url(self):
        from selenium.common.exceptions import TimeoutException

        class SequenceFetcher:
            def __init__(self):
                self.calls = 0

            def fetch(self, url):
                self.calls += 1
                if self.calls == 1:
                    raise TimeoutException("timeout")
                return {
                    "final_url": url,
                    "http_status": None,
                    "html": (
                        "<h1>Title</h1><div class='fck_detail'>"
                        "<p>Content</p></div>"
                    ),
                }

            def close(self):
                pass

        fetcher = SequenceFetcher()
        run_id = uuid4()
        failed = crawler.crawl_article(
            "https://example.com/failed",
            1,
            "vnexpress",
            20,
            fetcher=fetcher,
            crawl_run_id=run_id,
        )
        succeeded = crawler.crawl_article(
            "https://example.com/succeeded",
            1,
            "vnexpress",
            20,
            fetcher=fetcher,
            crawl_run_id=run_id,
        )
        self.assertEqual(failed.status, "TIMEOUT")
        self.assertEqual(succeeded.status, "SUCCESS")
        self.assertEqual(fetcher.calls, 2)

    def test_same_run_retry_reuses_existing_artifact(self):
        class Fetcher:
            def __init__(self):
                self.calls = 0

            def fetch(self, url):
                self.calls += 1
                return {
                    "final_url": url,
                    "http_status": None,
                    "html": (
                        "<h1>Title</h1><div class='fck_detail'>"
                        "<p>Content</p></div>"
                    ),
                }

            def close(self):
                pass

        fetcher = Fetcher()
        run_id = uuid4()
        first = crawler.crawl_article(
            "https://example.com/article?utm_source=test",
            1,
            "vnexpress",
            20,
            fetcher=fetcher,
            crawl_run_id=run_id,
        )
        second = crawler.crawl_article(
            "https://EXAMPLE.com:443/article",
            1,
            "vnexpress",
            20,
            fetcher=fetcher,
            crawl_run_id=run_id,
        )
        self.assertEqual(first.status, "SUCCESS")
        self.assertEqual(second.status, "SUCCESS")
        self.assertEqual(fetcher.calls, 1)
        self.assertEqual(first.raw_object_key, second.raw_object_key)
        self.assertEqual(len(list((self.temp_root / "crawl_data").rglob("*.html.gz"))), 1)


@unittest.skipUnless(
    crawler and os.getenv("TEST_DATABASE_URL"),
    "set TEST_DATABASE_URL to run the PostgreSQL upsert integration test",
)
class DatabaseRetryIdempotencyTests(unittest.TestCase):
    def test_same_run_url_is_updated_not_duplicated(self):
        from datetime import datetime, timezone

        record_type = crawler.RawDataRecord
        run_id = uuid4()
        database_url = os.environ["TEST_DATABASE_URL"]
        first = record_type(
            source_id=999999,
            url=f"https://example.com/test-{run_id}.html",
            final_url=None,
            http_status=None,
            raw_object_key=None,
            raw_payload_type=None,
            raw_content_hash=None,
            crawl_run_id=run_id,
            status="TIMEOUT",
            error_type="TimeoutException",
            error_message="first attempt",
            fetched_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        second = first.__class__(**{**first.__dict__, "status": "SUCCESS"})
        try:
            first_id = crawler.insert_rawdata(first, database_url)
            second_id = crawler.insert_rawdata(second, database_url)
            self.assertEqual(first_id, second_id)
        finally:
            import psycopg

            with psycopg.connect(database_url) as connection:
                connection.execute(
                    "DELETE FROM rawdata WHERE source_id = %s AND crawl_run_id = %s",
                    (999999, run_id),
                )


if __name__ == "__main__":
    unittest.main()
