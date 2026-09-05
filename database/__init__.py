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
    get_latest_rawdata,
    get_rawdata_by_id,
    insert_rawdata,
)

__all__ = [
    "get_connection",
    "get_database_url",
    "test_connection",
    "execute_query",
    "insert_rawdata",
    "get_rawdata_by_id",
    "check_url_exists",
    "count_rawdata",
    "get_latest_rawdata",
]

