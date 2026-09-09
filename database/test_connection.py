"""Script dòng lệnh (CLI) kiểm tra kết nối tới cơ sở dữ liệu PostgreSQL.

Cách dùng:
    python database/test_connection.py
    # hoặc
    python -m database.test_connection
"""

from __future__ import annotations

import json
import os
import sys

# Thêm thư mục gốc dự án vào sys.path để có thể chạy script độc lập
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.connection import get_database_url, test_connection, _mask_url_password


def main() -> int:
    print("=" * 60)
    print("🔍 KIỂM TRA KẾT NỐI CƠ SỞ DỮ LIỆU POSTGRESQL")
    print("=" * 60)

    raw_url = get_database_url()
    print(f"Target URL: {_mask_url_password(raw_url)}")
    print("Đang thử kết nối...")

    result = test_connection()

    if not result.get("connected"):
        print("\n❌ KẾT NỐI THẤT BẠI!")
        print(f"- Lỗi ({result.get('error_type')}): {result.get('error_message')}")
        print("\n💡 HƯỚNG DẪN KHẮC PHỤC:")
        print("1. Đảm bảo container PostgreSQL đang chạy:")
        print("   docker compose up -d postgres")
        print("2. Kiểm tra biến môi trường:")
        print("   - Nếu chạy ngoài máy host: POSTGRES_PORT=15432, POSTGRES_HOST=localhost")
        print("   - Nếu chạy trong Docker container: POSTGRES_PORT=5432, POSTGRES_HOST=postgres")
        print("=" * 60)
        return 1

    print("\n✅ KẾT NỐI THÀNH CÔNG!")
    print(f"- Driver: {result.get('driver')}")
    print(f"- Database: {result.get('database')}")
    print(f"- User: {result.get('user')}")
    print(f"- Server Version: {result.get('server_version')}")

    tables = result.get("tables", [])
    print(f"- Các bảng hiện có trong schema public ({len(tables)}): {', '.join(tables) if tables else '(chưa có bảng nào)'}")

    if "raw_articles" in tables:
        try:
            from database.connection import execute_query
            rows = execute_query("SELECT count(*) FROM raw_articles;")
            total_rows = rows[0]["count"] if rows else 0
            print(f"- Bảng 'raw_articles': tổng cộng {total_rows} bản ghi")
        except Exception as e:
            print(f"- Lỗi khi đọc bảng raw_articles: {e}")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

