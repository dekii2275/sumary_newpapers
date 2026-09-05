"""Crawl VnExpress articles and persist Step 1 raw records.

The module keeps fetching, parsing, local artifact storage, and PostgreSQL
persistence as separate operations. New metadata is written as schema v2;
existing v1 files are left untouched and can be identified by the compatibility
helpers in :mod:`crawl_contract`.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from crawl_contract import (
    METADATA_SCHEMA_VERSION,
    metadata_schema_version,
    normalize_url,
    safe_source_name,
    url_hash,
    validate_metadata,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "crawl_data"
DEFAULT_DATABASE_URL = (
    "postgresql://news_user:news_password_dev@localhost:15432/news_db"
)
PAGE_TIMEOUT_SECONDS = 20
USER_AGENT = "AI-Tech-News-Research-Crawler/0.1"


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    value = " ".join(value.split())
    return value or None


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

    def fetch(self, url: str) -> dict[str, object]:
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
            # Selenium does not expose the network response status reliably.
            # Keep the field in the contract for the future HTTP fetcher.
            "http_status": None,
        }

    def close(self) -> None:
        self.driver.quit()


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


def artifact_paths(
    source_name: str, url: str, crawl_run_id: UUID
) -> tuple[Path, Path]:
    """Return stable raw/metadata paths for one URL in one crawl run."""

    source_key = safe_source_name(source_name)
    run_key = str(crawl_run_id)
    artifact_id = f"{url_hash(url)}_{crawl_run_id.hex}"
    raw_base = OUTPUT_ROOT / "raw" / source_key / "runs" / run_key
    metadata_base = OUTPUT_ROOT / "metadata" / source_key / "runs" / run_key
    return (
        raw_base / f"{artifact_id}.html.gz",
        metadata_base / f"{artifact_id}.json",
    )


def _relative_object_key(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def _atomic_write_gzip(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        with gzip.open(temporary_path, "wt", encoding="utf-8") as gzip_file:
            gzip_file.write(html)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def _read_gzip(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as gzip_file:
        return gzip_file.read()


def _build_metadata(
    *,
    source_name: str,
    url: str,
    final_url: str | None,
    article: dict[str, str | None],
    raw_object_key: str | None,
    raw_content_hash: str | None,
    status: str,
    http_status: int | None,
    crawl_run_id: UUID,
    fetched_at: datetime,
    error_type: str | None,
    error_message: str | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "schema_version": METADATA_SCHEMA_VERSION,
        "source": source_name,
        "url": url,
        "final_url": final_url,
        "title": article.get("title"),
        "author": article.get("author"),
        "published_at": article.get("published_at"),
        "content": article.get("content"),
        "thumbnail_url": article.get("thumbnail_url"),
        "raw_object_key": raw_object_key,
        "raw_payload_type": "text/html" if raw_object_key else None,
        "raw_content_hash": raw_content_hash,
        "status": status,
        "http_status": http_status,
        "crawl_run_id": str(crawl_run_id),
        "fetched_at": fetched_at.isoformat(),
        "error_type": error_type,
        "error_message": error_message,
    }
    validate_metadata(metadata)
    return metadata


def _write_metadata(
    *,
    source_name: str,
    url: str,
    crawl_run_id: UUID,
    final_url: str | None,
    article: dict[str, str | None],
    raw_object_key: str | None,
    raw_content_hash: str | None,
    status: str,
    http_status: int | None,
    fetched_at: datetime,
    error_type: str | None,
    error_message: str | None,
) -> str:
    _, metadata_path = artifact_paths(source_name, url, crawl_run_id)
    metadata = _build_metadata(
        source_name=source_name,
        url=url,
        final_url=final_url,
        article=article,
        raw_object_key=raw_object_key,
        raw_content_hash=raw_content_hash,
        status=status,
        http_status=http_status,
        crawl_run_id=crawl_run_id,
        fetched_at=fetched_at,
        error_type=error_type,
        error_message=error_message,
    )
    _atomic_write_text(
        metadata_path,
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
    )
    return _relative_object_key(metadata_path)


def save_artifacts(
    html: str,
    source_name: str,
    url: str,
    fetched_at: datetime,
    article: dict[str, str | None],
    *,
    final_url: str | None = None,
    http_status: int | None = None,
    status: str = "SUCCESS",
    crawl_run_id: UUID | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> tuple[str, str]:
    """Atomically persist immutable raw HTML and canonical metadata.

    The path is stable for ``(source, normalized_url, crawl_run_id)``. If a
    retry reaches an existing path, it reuses that raw payload rather than
    creating or overwriting a second artifact.
    """

    crawl_run_id = crawl_run_id or uuid4()
    raw_path, _ = artifact_paths(source_name, url, crawl_run_id)
    if raw_path.exists():
        persisted_html = _read_gzip(raw_path)
    else:
        persisted_html = html
        _atomic_write_gzip(raw_path, html)

    raw_content_hash = hashlib.sha256(persisted_html.encode("utf-8")).hexdigest()
    raw_object_key = _relative_object_key(raw_path)
    _write_metadata(
        source_name=source_name,
        url=url,
        crawl_run_id=crawl_run_id,
        final_url=final_url,
        article=article,
        raw_object_key=raw_object_key,
        raw_content_hash=raw_content_hash,
        status=status,
        http_status=http_status,
        fetched_at=fetched_at,
        error_type=error_type,
        error_message=error_message,
    )
    return raw_object_key, raw_content_hash


def load_existing_artifact(
    source_name: str, url: str, crawl_run_id: UUID
) -> tuple[str, dict[str, Any]] | None:
    """Load a stable artifact left by an earlier attempt of this run."""

    raw_path, metadata_path = artifact_paths(source_name, url, crawl_run_id)
    if not raw_path.exists():
        return None

    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and metadata_schema_version(loaded) == 2:
            metadata = loaded
    return _read_gzip(raw_path), metadata


def find_rawdata(
    source_id: int, url: str, crawl_run_id: UUID, database_url: str
) -> tuple[int, str] | None:
    query = """
        SELECT id, status
        FROM rawdata
        WHERE source_id = %s AND crawl_run_id = %s AND url = %s
        ORDER BY id
        LIMIT 1
    """
    with psycopg.connect(database_url) as connection:
        result = connection.execute(query, (source_id, crawl_run_id, url))
        row = result.fetchone()
    return (int(row[0]), str(row[1])) if row else None


def insert_rawdata(record: RawDataRecord, database_url: str) -> int:
    """Insert or update one run/url record without creating retry duplicates.

    This application-level check is intentionally used before the future
    uniqueness migration. Airflow's ``max_active_runs=1`` keeps this Step 1
    path single-writer while the duplicate inventory is cleaned up later.
    """

    values = asdict(record)
    update_query = """
        UPDATE rawdata
        SET final_url = %(final_url)s,
            http_status = %(http_status)s,
            raw_object_key = %(raw_object_key)s,
            raw_payload_type = %(raw_payload_type)s,
            raw_content_hash = %(raw_content_hash)s,
            status = %(status)s,
            error_type = %(error_type)s,
            error_message = %(error_message)s,
            fetched_at = %(fetched_at)s,
            created_at = %(created_at)s
        WHERE id = (
            SELECT id FROM rawdata
            WHERE source_id = %(source_id)s
              AND crawl_run_id = %(crawl_run_id)s
              AND url = %(url)s
            ORDER BY id
            LIMIT 1
        )
        RETURNING id
    """
    insert_query = """
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
        result = connection.execute(update_query, values)
        row = result.fetchone()
        if row:
            return int(row[0])
        result = connection.execute(insert_query, values)
        return int(result.fetchone()[0])


def _record(
    *,
    source_id: int,
    url: str,
    final_url: str | None,
    http_status: int | None,
    raw_object_key: str | None,
    raw_content_hash: str | None,
    crawl_run_id: UUID,
    status: str,
    error_type: str | None,
    error_message: str | None,
    fetched_at: datetime,
) -> RawDataRecord:
    return RawDataRecord(
        source_id=source_id,
        url=url,
        final_url=final_url,
        http_status=http_status,
        raw_object_key=raw_object_key,
        raw_payload_type="text/html" if raw_object_key else None,
        raw_content_hash=raw_content_hash,
        crawl_run_id=crawl_run_id,
        status=status,
        error_type=error_type,
        error_message=error_message,
        fetched_at=fetched_at,
        created_at=fetched_at,
    )


def crawl_article(
    url: str,
    source_id: int,
    source_name: str,
    timeout: int,
    fetcher: SeleniumFetcher | None = None,
    crawl_run_id: UUID | None = None,
) -> RawDataRecord:
    fetched_at = datetime.now(timezone.utc)
    crawl_run_id = crawl_run_id or uuid4()
    try:
        normalized_url = normalize_url(url)
    except ValueError as error:
        return _record(
            source_id=source_id,
            url=str(url).strip(),
            final_url=None,
            http_status=None,
            raw_object_key=None,
            raw_content_hash=None,
            crawl_run_id=crawl_run_id,
            status="INVALID_URL",
            error_type=type(error).__name__,
            error_message=str(error),
            fetched_at=fetched_at,
        )

    response: dict[str, object] = {}
    article: dict[str, str | None] = {}
    html = ""
    raw_object_key: str | None = None
    raw_content_hash: str | None = None
    status = "UNKNOWN_ERROR"
    error_type: str | None = None
    error_message: str | None = None
    owns_fetcher = fetcher is None
    metadata_saved = False

    try:
        existing_artifact = load_existing_artifact(
            source_name, normalized_url, crawl_run_id
        )
        if existing_artifact:
            html, existing_metadata = existing_artifact
            response = {
                "final_url": existing_metadata.get("final_url") or normalized_url,
                "http_status": existing_metadata.get("http_status"),
            }
        else:
            if fetcher is None:
                fetcher = SeleniumFetcher(timeout=timeout)
            response = fetcher.fetch(normalized_url)
            html = str(response.get("html") or "")

        final_url = response.get("final_url")
        final_url = str(final_url) if final_url else None
        http_status = response.get("http_status")
        http_status = int(http_status) if isinstance(http_status, int) else None

        if not html.strip():
            status = "EMPTY_HTML"
            error_type = "EMPTY_HTML"
            error_message = "Rendered HTML is empty"
        else:
            try:
                article = VnExpressParser().parse(html)
            except Exception as error:
                status = "PARSE_FAILED"
                error_type = type(error).__name__
                error_message = str(error)
                raw_object_key, raw_content_hash = save_artifacts(
                    html,
                    source_name,
                    normalized_url,
                    fetched_at,
                    article,
                    final_url=final_url,
                    http_status=http_status,
                    status=status,
                    crawl_run_id=crawl_run_id,
                    error_type=error_type,
                    error_message=error_message,
                )
                metadata_saved = True

            if metadata_saved:
                return _record(
                    source_id=source_id,
                    url=normalized_url,
                    final_url=final_url,
                    http_status=http_status,
                    raw_object_key=raw_object_key,
                    raw_content_hash=raw_content_hash,
                    crawl_run_id=crawl_run_id,
                    status=status,
                    error_type=error_type,
                    error_message=error_message,
                    fetched_at=fetched_at,
                )

            status = "SUCCESS" if article.get("content") else "CONTENT_NOT_FOUND"
            if status != "SUCCESS":
                error_type = "CONTENT_NOT_FOUND"
                error_message = "No article body matched"
            raw_object_key, raw_content_hash = save_artifacts(
                html,
                source_name,
                normalized_url,
                fetched_at,
                article,
                final_url=final_url,
                http_status=http_status,
                status=status,
                crawl_run_id=crawl_run_id,
                error_type=error_type,
                error_message=error_message,
            )
            metadata_saved = True

        if not metadata_saved:
            _write_metadata(
                source_name=source_name,
                url=normalized_url,
                crawl_run_id=crawl_run_id,
                final_url=final_url,
                article=article,
                raw_object_key=raw_object_key,
                raw_content_hash=raw_content_hash,
                status=status,
                http_status=http_status,
                fetched_at=fetched_at,
                error_type=error_type,
                error_message=error_message,
            )
            metadata_saved = True
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

    if not metadata_saved:
        try:
            _write_metadata(
                source_name=source_name,
                url=normalized_url,
                crawl_run_id=crawl_run_id,
                final_url=(
                    str(response.get("final_url"))
                    if response.get("final_url")
                    else None
                ),
                article=article,
                raw_object_key=raw_object_key,
                raw_content_hash=raw_content_hash,
                status=status,
                http_status=(
                    int(response["http_status"])
                    if isinstance(response.get("http_status"), int)
                    else None
                ),
                fetched_at=fetched_at,
                error_type=error_type,
                error_message=error_message,
            )
        except Exception as metadata_error:
            status = "STORAGE_ERROR"
            error_type = type(metadata_error).__name__
            error_message = str(metadata_error)

    return _record(
        source_id=source_id,
        url=normalized_url,
        final_url=(
            str(response.get("final_url")) if response.get("final_url") else None
        ),
        http_status=(
            int(response["http_status"])
            if isinstance(response.get("http_status"), int)
            else None
        ),
        raw_object_key=raw_object_key,
        raw_content_hash=raw_content_hash,
        crawl_run_id=crawl_run_id,
        status=status,
        error_type=error_type,
        error_message=error_message,
        fetched_at=fetched_at,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl one VnExpress article and insert its raw record."
    )
    parser.add_argument("url", help="Article URL to crawl")
    parser.add_argument(
        "--source-id", type=int, default=1, help="Numeric source_id (default: 1)"
    )
    parser.add_argument(
        "--source-name", default="vnexpress", help="Source name (default: vnexpress)"
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
