"""Module cung cấp các thao tác CRUD với bảng `rawdata` trong PostgreSQL."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

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


def insert_rawdata(record: Any, database_url: str | None = None) -> int:
    """Chèn một bản ghi thô vào bảng `rawdata` và trả về `id` vừa được sinh ra.

    Hỗ trợ đối số `record` dạng dict, dataclass hoặc Pydantic model.
    """
    data = _extract_dict(record)

    now_utc = datetime.now(timezone.utc)
    crawl_run_id = data.get("crawl_run_id")
    if crawl_run_id is None:
        crawl_run_id = str(uuid4())
    else:
        crawl_run_id = str(crawl_run_id)

    params = {
        "source_id": int(data.get("source_id", 1)),
        "url": str(data["url"]),
        "final_url": data.get("final_url"),
        "http_status": data.get("http_status"),
        "raw_object_key": data.get("raw_object_key") or data.get("raw_html_path"),
        "raw_payload_type": data.get("raw_payload_type", "text/html"),
        "raw_content_hash": data.get("raw_content_hash"),
        "crawl_run_id": crawl_run_id,
        "status": str(data.get("status") or data.get("crawl_status") or "SUCCESS"),
        "error_type": data.get("error_type"),
        "error_message": data.get("error_message") or data.get("error"),
        "fetched_at": data.get("fetched_at") or now_utc,
        "created_at": data.get("created_at") or now_utc,
    }

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
        RETURNING id;
    """

    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        inserted_id = row[0] if row else None
        cursor.close()

    if inserted_id is None:
        raise RuntimeError("Thao tác chèn vào bảng rawdata không trả về id")

    return int(inserted_id)


def get_rawdata_by_id(record_id: int, database_url: str | None = None) -> dict[str, Any] | None:
    """Truy vấn một bản ghi theo ID từ bảng `rawdata`."""
    query = """
        SELECT
            id,
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
        FROM rawdata
        WHERE id = %(id)s;
    """
    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query, {"id": record_id})
        row = cursor.fetchone()
        if not row:
            cursor.close()
            return None

        # Map tên cột nếu cursor không tự chuyển sang dict
        if hasattr(cursor, "description") and cursor.description:
            colnames = [col[0] for col in cursor.description]
            if isinstance(row, dict):
                result = dict(row)
            else:
                result = dict(zip(colnames, row))
        else:
            result = {"id": row[0]}
        cursor.close()
        return result


def check_url_exists(
    url: str,
    source_id: int | None = None,
    database_url: str | None = None,
) -> bool:
    """Kiểm tra nhanh URL đã được cào thành công trước đó hay chưa."""
    if source_id is not None:
        query = """
            SELECT 1 FROM rawdata
            WHERE url = %(url)s AND source_id = %(source_id)s AND status = 'SUCCESS'
            LIMIT 1;
        """
        params = {"url": url, "source_id": source_id}
    else:
        query = """
            SELECT 1 FROM rawdata
            WHERE url = %(url)s AND status = 'SUCCESS'
            LIMIT 1;
        """
        params = {"url": url}

    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        exists = cursor.fetchone() is not None
        cursor.close()
        return exists


def count_rawdata(status: str | None = None, database_url: str | None = None) -> int:
    """Đếm tổng số bản ghi trong bảng `rawdata`, có thể lọc theo status."""
    if status:
        query = "SELECT COUNT(*) FROM rawdata WHERE status = %(status)s;"
        params = {"status": status}
    else:
        query = "SELECT COUNT(*) FROM rawdata;"
        params = {}

    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        return int(count)


def get_latest_rawdata(limit: int = 10, database_url: str | None = None) -> list[dict[str, Any]]:
    """Lấy danh sách các bản ghi mới nhất từ bảng `rawdata`."""
    query = """
        SELECT
            id,
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
        FROM rawdata
        ORDER BY id DESC
        LIMIT %(limit)s;
    """
    with get_connection(database_url) as conn:
        cursor = conn.cursor()
        cursor.execute(query, {"limit": limit})
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

