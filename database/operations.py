"""Module cung cấp các thao tác CRUD với cơ sở dữ liệu PostgreSQL (bảng raw_articles và sources)."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any

from database.connection import get_connection


def _extract_dict(record: Any) -> dict[str, Any]:
    """Chuyển đổi record từ dict, dataclass hoặc object thành dict chuẩn."""
    if isinstance(record, dict):
        return dict(record)
    if dataclasses.is_dataclass(record):
        return dataclasses.asdict(record)
    if hasattr(record, "model_dump"):  # Pydantic v2
        return record.model_dump()
    if hasattr(record, "dict"):  # Pydantic v1
        return record.dict()
    if hasattr(record, "__dict__"):
        return vars(record)
    raise TypeError(f"Không thể chuyển đổi kiểu dữ liệu {type(record)} thành dict")


def ensure_source_exists(
    source_name: str = "unknown",
    source_url: str | None = None,
    source_type: str = "crawler",
    database_url: str | None = None,
) -> int:
    """Tra cứu `source_id` theo tên `source_name`. Nếu chưa có trong bảng `sources` thì tự động thêm mới."""
    if not source_name:
        source_name = "unknown"

    clean_name = source_name.lower().strip()

    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM sources WHERE LOWER(name) = %(name)s LIMIT 1;",
            {"name": clean_name},
        )
        row = cursor.fetchone()
        if row:
            cursor.close()
            return int(row[0] if not isinstance(row, dict) else row["id"])

        url = source_url or f"https://{clean_name}.com"
        cursor.execute(
            """
            INSERT INTO sources (name, url, source_type, is_active)
            VALUES (%(name)s, %(url)s, %(source_type)s, TRUE)
            ON CONFLICT (url) DO UPDATE SET name = EXCLUDED.name
            RETURNING id;
            """,
            {"name": clean_name, "url": url, "source_type": source_type},
        )
        inserted = cursor.fetchone()
        source_id = inserted[0] if inserted else 1
        cursor.close()
        return int(source_id)


def check_url_exists(
    url: str,
    source_id: int | None = None,
    database_url: str | None = None,
    only_success: bool = False,
) -> bool:
    """Kiểm tra nhanh URL đã được cào và lưu trong bảng `raw_articles` hay chưa."""
    clean_url = str(url or "").strip()
    if not clean_url:
        return False

    status_filter = "AND status = 'SUCCESS'" if only_success else ""
    if source_id is not None:
        query = f"""
            SELECT 1 FROM raw_articles
            WHERE external_url = %(url)s AND source_id = %(source_id)s {status_filter}
            LIMIT 1;
        """
        params = {"url": clean_url, "source_id": source_id}
    else:
        query = f"""
            SELECT 1 FROM raw_articles
            WHERE external_url = %(url)s {status_filter}
            LIMIT 1;
        """
        params = {"url": clean_url}

    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        exists = cursor.fetchone() is not None
        cursor.close()
        return exists


def get_existing_urls(
    urls: list[str],
    database_url: str | None = None,
) -> set[str]:
    """Truy vấn 1 lần duy nhất danh sách các URL đã tồn tại trong DB (Batch Check)."""
    clean_urls = list({u.strip() for u in urls if u and u.strip()})
    if not clean_urls:
        return set()

    query = "SELECT external_url FROM raw_articles WHERE external_url = ANY(%(urls)s);"
    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query, {"urls": clean_urls})
        rows = cursor.fetchall()
        existing = {r[0] if not isinstance(r, dict) else r["external_url"] for r in rows}
        cursor.close()
        return existing


def get_active_sources_from_db(database_url: str | None = None) -> list[dict[str, Any]]:
    """Lấy danh sách các nguồn tin tức đang hoạt động (is_active = TRUE) từ bảng `sources`."""
    query = """
        SELECT id, name, url, source_type, is_active, created_at
        FROM sources
        WHERE is_active = TRUE
        ORDER BY id ASC;
    """
    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        results: list[dict[str, Any]] = []
        if cursor.description:
            colnames = [col[0] for col in cursor.description]
            for row in rows:
                if isinstance(row, dict):
                    results.append(dict(row))
                else:
                    results.append(dict(zip(colnames, row)))
        cursor.close()
        return results


def count_raw_articles(status: str | None = None, database_url: str | None = None) -> int:
    """Đếm tổng số bản ghi trong bảng `raw_articles`, có thể lọc theo status."""
    if status:
        query = "SELECT COUNT(*) FROM raw_articles WHERE status = %(status)s;"
        params = {"status": status}
    else:
        query = "SELECT COUNT(*) FROM raw_articles;"
        params = {}

    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        return int(count)


# Giữ alias cho tương thích ngược
count_rawdata = count_raw_articles


def _parse_timestamp(val: Any) -> datetime | None:
    """Chuyển đổi các định dạng thời gian (ISO, tiếng Việt, v.v.) sang đối tượng datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    val_str = str(val).strip()
    if not val_str:
        return None

    try:
        return datetime.fromisoformat(val_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass

    try:
        import dateparser
        parsed = dateparser.parse(val_str, languages=["vi", "en"])
        if parsed:
            return parsed
    except Exception:
        pass

    return None


def insert_raw_article(record: Any, database_url: str | None = None) -> int:
    """Chèn một bài viết thô vào bảng `raw_articles` và trả về `id` vừa được sinh ra."""
    data = _extract_dict(record)
    now_utc = datetime.now(timezone.utc)

    source_id = data.get("source_id")
    if not source_id:
        source_name = data.get("source") or data.get("source_name")
        if not source_name and (data.get("url") or data.get("external_url")):
            target_url = str(data.get("url") or data.get("external_url"))
            try:
                from scripts.crawler.registry import registry
                cfg = registry.get_config_by_url(target_url)
                if cfg:
                    source_name = cfg.source_name
            except Exception:
                pass
        source_id = ensure_source_exists(source_name or "unknown", database_url=database_url)
    else:
        source_id = int(source_id)

    pub_at = _parse_timestamp(data.get("published_at"))

    params = {
        "source_id": source_id,
        "canonical_article_id": data.get("canonical_article_id"),
        "external_url": str(data.get("url") or data.get("external_url")).strip(),
        "title_raw": data.get("title") or data.get("title_raw"),
        "content_raw": data.get("content") or data.get("content_raw"),
        "author": data.get("author"),
        "published_at": pub_at,
        "collected_at": data.get("fetched_at") or data.get("collected_at") or now_utc,
        "status": data.get("crawl_status") or data.get("status") or "SUCCESS",
    }

    query = """
        INSERT INTO raw_articles (
            source_id,
            canonical_article_id,
            external_url,
            title_raw,
            content_raw,
            author,
            published_at,
            collected_at,
            status
        ) VALUES (
            %(source_id)s,
            %(canonical_article_id)s,
            %(external_url)s,
            %(title_raw)s,
            %(content_raw)s,
            %(author)s,
            %(published_at)s,
            %(collected_at)s,
            %(status)s
        )
        RETURNING id;
    """

    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        inserted_id = row[0] if row else None
        cursor.close()

    if inserted_id is None:
        raise RuntimeError("Thao tác chèn vào bảng raw_articles không trả về id")

    return int(inserted_id)


def save_crawl_result_to_db(
    metadata: dict[str, Any],
    database_url: str | None = None,
) -> dict[str, Any]:
    """Lưu kết quả cào (metadata) vào PostgreSQL DB (bảng `raw_articles`)."""
    raw_article_id = None
    crawl_status = metadata.get("crawl_status") or metadata.get("status") or "SUCCESS"
    try:
        raw_article_id = insert_raw_article(metadata, database_url=database_url)
    except Exception as error:
        print(f"⚠️ Không thể chèn vào raw_articles: {error}")

    return {
        "raw_article_id": raw_article_id,
        "status": crawl_status,
        "url": metadata.get("url") or metadata.get("external_url"),
    }
