"""Crawl one VnExpress article and persist the raw crawl record in PostgreSQL.

Usage:
    python scripts/crawl_to_db.py "https://vnexpress.net/example.html" --source-id 1

The script follows the Step 1 notebook flow:
Selenium fetch -> BeautifulSoup parse -> gzip raw HTML -> insert into rawdata.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import psycopg
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "crawl_data"
DEFAULT_DATABASE_URL = (
    "postgresql://news_user:news_password_dev@localhost:15432/news_db"
)
PAGE_TIMEOUT_SECONDS = 20
USER_AGENT = "AI-Tech-News-Research-Crawler/0.1"
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    clean_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(clean_query), "")
    )


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16]


class SeleniumFetcher:
    def __init__(self, timeout: int = PAGE_TIMEOUT_SECONDS) -> None:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"--user-agent={USER_AGENT}")

        self.timeout = timeout
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(timeout)

    def fetch(self, url: str) -> dict[str, str | None]:
        self.driver.get(url)
        WebDriverWait(self.driver, self.timeout).until(
            lambda driver: driver.execute_script(
                "return document.readyState"
            )
            == "complete"
        )
        return {
            "final_url": self.driver.current_url,
            "html": self.driver.page_source,
        }

    def close(self) -> None:
        self.driver.quit()


class VnExpressParser:
    CONTENT_SELECTORS = (
        ".fck_detail p",
        "article p",
        ".content_detail p",
    )

    @staticmethod
    def _first_text(
        soup: BeautifulSoup, selectors: tuple[str, ...]
    ) -> str | None:
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                text = clean_text(node.get_text(" ", strip=True))
                if text:
                    return text
        return None

    def parse(self, html: str) -> dict[str, str | None]:
        soup = BeautifulSoup(html, "lxml")

        title = self._first_text(soup, ("h1.title-detail", "h1", "title"))
        author = self._first_text(soup, (".author_mail", ".author"))

        published_at = None
        published_meta = soup.select_one("meta[property='article:published_time']")
        if published_meta:
            published_at = clean_text(published_meta.get("content"))
        if not published_at:
            published_at = self._first_text(soup, ("time[datetime]", ".date"))

        paragraphs_by_selector = [
            soup.select(selector) for selector in self.CONTENT_SELECTORS
        ]
        paragraphs = max(paragraphs_by_selector, key=len, default=[])
        content_parts = [
            text
            for paragraph in paragraphs
            if (text := clean_text(paragraph.get_text(" ", strip=True)))
        ]

        image_meta = soup.select_one("meta[property='og:image']")
        thumbnail_url = image_meta.get("content") if image_meta else None

        return {
            "title": title,
            "author": author,
            "published_at": published_at,
            "content": "\n\n".join(content_parts) or None,
            "thumbnail_url": clean_text(thumbnail_url),
        }


@dataclass
class RawDataRecord:
    source_id: int
    url: str
    final_url: str | None
    http_status: int | None
    raw_object_key: str | None
    raw_payload_type: str | None
    raw_content_hash: str | None
    crawl_run_id: UUID
    status: str
    error_type: str | None
    error_message: str | None
    fetched_at: datetime
    created_at: datetime


def save_artifacts(
    html: str,
    source_name: str,
    url: str,
    fetched_at: datetime,
    article: dict[str, str | None],
) -> tuple[str, str]:
    date_path = fetched_at.astimezone().strftime("%Y/%m/%d")
    crawl_id = f"{url_hash(url)}_{fetched_at.strftime('%H%M%S_%f')}"
    raw_path = OUTPUT_ROOT / "raw" / source_name / date_path / f"{crawl_id}.html.gz"
    metadata_path = (
        OUTPUT_ROOT / "metadata" / source_name / date_path / f"{crawl_id}.json"
    )

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    raw_content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    with gzip.open(raw_path, "wt", encoding="utf-8") as file:
        file.write(html)

    raw_object_key = raw_path.relative_to(PROJECT_ROOT).as_posix()
    metadata = {
        "source": source_name,
        "url": url,
        "title": article.get("title"),
        "author": article.get("author"),
        "published_at": article.get("published_at"),
        "content": article.get("content"),
        "thumbnail_url": article.get("thumbnail_url"),
        "raw_object_key": raw_object_key,
        "raw_content_hash": raw_content_hash,
        "fetched_at": fetched_at.isoformat(),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return raw_object_key, raw_content_hash


def insert_rawdata(record: RawDataRecord, database_url: str) -> int:
    query = """
        INSERT INTO rawdata (
            source_id,
            url,
            final_url,
            http_status,
            raw_object_key,
            raw_payload_type,
            raw_content_hash,
            crawl_run_id,
            status,
            error_type,
            error_message,
            fetched_at,
            created_at
        ) VALUES (
            %(source_id)s,
            %(url)s,
            %(final_url)s,
            %(http_status)s,
            %(raw_object_key)s,
            %(raw_payload_type)s,
            %(raw_content_hash)s,
            %(crawl_run_id)s,
            %(status)s,
            %(error_type)s,
            %(error_message)s,
            %(fetched_at)s,
            %(created_at)s
        )
        RETURNING id
    """
    with psycopg.connect(database_url) as connection:
        result = connection.execute(query, asdict(record))
        inserted_id = result.fetchone()[0]
    return inserted_id


def crawl_article(
    url: str,
    source_id: int,
    source_name: str,
    timeout: int,
    fetcher: SeleniumFetcher | None = None,
    crawl_run_id: UUID | None = None,
) -> RawDataRecord:
    normalized_url = normalize_url(url)
    fetched_at = datetime.now(timezone.utc)
    crawl_run_id = crawl_run_id or uuid4()
    created_at = fetched_at
    response: dict[str, str | None] = {}
    html = ""
    article: dict[str, str | None] = {}
    owns_fetcher = fetcher is None
    status = "UNKNOWN_ERROR"
    error_type: str | None = None
    error_message: str | None = None

    try:
        if fetcher is None:
            fetcher = SeleniumFetcher(timeout=timeout)
        response = fetcher.fetch(normalized_url)
        html = response.get("html") or ""

        if not html.strip():
            return RawDataRecord(
                source_id=source_id,
                url=normalized_url,
                final_url=response.get("final_url"),
                http_status=None,
                raw_object_key=None,
                raw_payload_type=None,
                raw_content_hash=None,
                crawl_run_id=crawl_run_id,
                status="EMPTY_HTML",
                error_type="EMPTY_HTML",
                error_message="Rendered HTML is empty",
                fetched_at=fetched_at,
                created_at=created_at,
            )

        article = VnExpressParser().parse(html)
        status = "SUCCESS" if article.get("content") else "CONTENT_NOT_FOUND"
        error_type = None if status == "SUCCESS" else "CONTENT_NOT_FOUND"
        error_message = None if status == "SUCCESS" else "No article body matched"
        raw_object_key, raw_content_hash = save_artifacts(
            html, source_name, normalized_url, fetched_at, article
        )

        return RawDataRecord(
            source_id=source_id,
            url=normalized_url,
            final_url=response.get("final_url"),
            http_status=None,
            raw_object_key=raw_object_key,
            raw_payload_type="text/html",
            raw_content_hash=raw_content_hash,
            crawl_run_id=crawl_run_id,
            status=status,
            error_type=error_type,
            error_message=error_message,
            fetched_at=fetched_at,
            created_at=created_at,
        )

    except TimeoutException as error:
        status = "TIMEOUT"
        error_type = type(error).__name__
        error_message = str(error)
    except WebDriverException as error:
        status = "BLOCKED"
        error_type = type(error).__name__
        error_message = str(error)
    except Exception as error:
        status = "UNKNOWN_ERROR"
        error_type = type(error).__name__
        error_message = str(error)
    finally:
        if owns_fetcher and fetcher is not None:
            fetcher.close()

    return RawDataRecord(
        source_id=source_id,
        url=normalized_url,
        final_url=response.get("final_url"),
        http_status=None,
        raw_object_key=None,
        raw_payload_type=None,
        raw_content_hash=None,
        crawl_run_id=crawl_run_id,
        status=status,
        error_type=error_type,
        error_message=error_message,
        fetched_at=fetched_at,
        created_at=created_at,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl one VnExpress article and insert its raw record."
    )
    parser.add_argument("url", help="Article URL to crawl")
    parser.add_argument(
        "--source-id",
        type=int,
        default=1,
        help="Numeric source_id stored in rawdata (default: 1)",
    )
    parser.add_argument(
        "--source-name",
        default="vnexpress",
        help="Source name used for local raw files (default: vnexpress)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=PAGE_TIMEOUT_SECONDS,
        help="Browser timeout in seconds (default: 20)",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="PostgreSQL connection URL",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    record = crawl_article(
        url=args.url,
        source_id=args.source_id,
        source_name=args.source_name,
        timeout=args.timeout,
    )
    inserted_id = insert_rawdata(record, args.database_url)
    output = {"id": inserted_id, **asdict(record)}
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
