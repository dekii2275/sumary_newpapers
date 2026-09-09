"""Package quản lý kết nối và truy xuất cơ sở dữ liệu PostgreSQL của dự án AI Tech News."""

from database.connection import (
    execute_query,
    get_connection,
    get_database_url,
    test_connection,
)
from database.operations import (
    check_url_exists,
    count_rawdata,
    get_active_sources_from_db,
    insert_raw_article,
    save_crawl_result_to_db,
)

__all__ = [
    "get_connection",
    "get_database_url",
    "test_connection",
    "execute_query",
    "insert_raw_article",
    "save_crawl_result_to_db",
    "check_url_exists",
    "get_active_sources_from_db",
    "count_rawdata",
]
