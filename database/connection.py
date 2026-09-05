"""Module quản lý kết nối tới cơ sở dữ liệu PostgreSQL.

Hỗ trợ:
- Tự động nhận diện cấu hình từ biến môi trường (DATABASE_URL hoặc các biến POSTGRES_*).
- Tự động hỗ trợ cả psycopg (phiên bản 3) lẫn psycopg2.
- Context manager an toàn (tự động commit / rollback và đóng kết nối).
- Hàm kiểm tra kết nối (healthcheck) trả về thông tin chi tiết.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator
from urllib.parse import quote_plus

# Thử import psycopg (phiên bản 3 - chuẩn khuyến nghị), nếu không có thì fallback sang psycopg2
try:
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore

    PSYCOPG_VERSION = 3
except ImportError:
    try:
        import psycopg2 as psycopg  # type: ignore
        from psycopg2.extras import RealDictCursor as dict_row  # type: ignore

        PSYCOPG_VERSION = 2
    except ImportError:
        psycopg = None
        dict_row = None
        PSYCOPG_VERSION = 0


DEFAULT_POSTGRES_USER = "tech_admin"
DEFAULT_POSTGRES_PASSWORD = "news_summary"
DEFAULT_POSTGRES_DB = "tech_news_db"
DEFAULT_CONTAINER_PORT = 5432
DEFAULT_HOST_PORT = 15432


def get_database_url() -> str:
    """Xác định chuỗi kết nối PostgreSQL (DATABASE_URL) từ biến môi trường.

    Thứ tự ưu tiên:
    1. Biến môi trường `DATABASE_URL` nếu đã được thiết lập.
    2. Tổng hợp từ các biến đơn lẻ: `POSTGRES_USER`, `POSTGRES_PASSWORD`,
       `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`.
    """
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    user = os.getenv("POSTGRES_USER", DEFAULT_POSTGRES_USER)
    password = os.getenv("POSTGRES_PASSWORD", DEFAULT_POSTGRES_PASSWORD)
    host = os.getenv("POSTGRES_HOST", "localhost")
    db = os.getenv("POSTGRES_DB", DEFAULT_POSTGRES_DB)

    # Nếu đang trỏ tới host docker 'postgres' thì mặc định cổng 5432, ngược lại trỏ localhost dùng cổng 15432
    default_port = DEFAULT_CONTAINER_PORT if host == "postgres" else DEFAULT_HOST_PORT
    port = os.getenv("POSTGRES_PORT", str(default_port))

    # Mã hóa ký tự đặc biệt trong mật khẩu nếu có
    encoded_user = quote_plus(user)
    encoded_password = quote_plus(password)

    return f"postgresql://{encoded_user}:{encoded_password}@{host}:{port}/{db}"


def _ensure_driver() -> None:
    """Kiểm tra xem thư viện driver psycopg đã được cài đặt hay chưa."""
    if psycopg is None:
        raise RuntimeError(
            "Chưa cài đặt driver kết nối PostgreSQL. "
            "Vui lòng cài đặt: pip install 'psycopg[binary]' (hoặc 'psycopg2-binary')."
        )


@contextmanager
def get_connection(
    database_url: str | None = None,
    connect_timeout: int = 5,
    autocommit: bool = False,
) -> Generator[Any, None, None]:
    """Context manager an toàn cung cấp kết nối CSDL PostgreSQL.

    - Tự động đóng kết nối khi thoát khối with.
    - Tự động commit khi kết thúc thành công, hoặc rollback nếu có ngoại lệ.
    """
    _ensure_driver()
    url = database_url or get_database_url()

    conn = psycopg.connect(url, connect_timeout=connect_timeout)
    if autocommit:
        conn.autocommit = True
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.close()


def test_connection(database_url: str | None = None) -> dict[str, Any]:
    """Kiểm tra khả năng kết nối tới cơ sở dữ liệu và trả về thông tin chi tiết."""
    url = database_url or get_database_url()

    try:
        _ensure_driver()
        with get_connection(url, connect_timeout=3) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version_row = cursor.fetchone()
            db_version = version_row[0] if version_row else "Unknown"

            cursor.execute("SELECT current_database(), current_user;")
            meta_row = cursor.fetchone()
            current_db = meta_row[0] if meta_row else None
            current_user = meta_row[1] if meta_row else None

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
                """
            )
            tables = [r[0] for r in cursor.fetchall()]

            cursor.close()

            return {
                "status": "success",
                "connected": True,
                "driver": f"psycopg v{PSYCOPG_VERSION}",
                "database": current_db,
                "user": current_user,
                "server_version": db_version,
                "tables": tables,
            }
    except Exception as error:
        return {
            "status": "error",
            "connected": False,
            "driver": f"psycopg v{PSYCOPG_VERSION}" if PSYCOPG_VERSION > 0 else "None",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "target_url": _mask_url_password(url),
        }


def _mask_url_password(url: str) -> str:
    """Ẩn mật khẩu trong chuỗi URL để log/hiển thị an toàn."""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(url)
        if parts.password:
            netloc = f"{parts.username}:****@{parts.hostname}"
            if parts.port:
                netloc += f":{parts.port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        pass
    return url


def execute_query(
    sql: str,
    params: tuple[Any, ...] | dict[str, Any] | None = None,
    database_url: str | None = None,
    as_dict: bool = True,
) -> list[dict[str, Any]] | list[tuple[Any, ...]]:
    """Thực thi câu truy vấn SELECT và trả về danh sách kết quả."""
    _ensure_driver()
    url = database_url or get_database_url()

    with get_connection(url) as conn:
        if as_dict and dict_row is not None:
            if PSYCOPG_VERSION == 3:
                cursor = conn.cursor(row_factory=dict_row)
            else:
                cursor = conn.cursor(cursor_factory=dict_row)
        else:
            cursor = conn.cursor()

        cursor.execute(sql, params or ())
        results = cursor.fetchall()
        cursor.close()
        return results
