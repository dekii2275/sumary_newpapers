# Database Package - AI Tech News

Module Python quản lý cấu hình, kết nối và tương tác với cơ sở dữ liệu PostgreSQL (`tech_news_db`).

---

## 📂 Cấu trúc thư mục

```text
database/
├── __init__.py               # Export các hàm chính cho toàn bộ project sử dụng
├── connection.py             # Quản lý connection string, context manager, healthcheck
├── operations.py             # Các thao tác CRUD với bảng rawdata (insert_rawdata, query,...)
├── test_connection.py        # Script CLI kiểm tra kết nối CSDL và đọc số lượng bản ghi
├── init/
│   └── 001_create_database.sql # Script SQL khởi tạo database khi tạo container
├── migrations/
│   └── 002_add_rawdata_payload_and_run.sql # Script migration bổ sung cột
└── README.md                 # Tài liệu hướng dẫn này
```

---

## ⚙️ Cấu hình kết nối

Module tự động nhận diện kết nối thông qua biến môi trường:

### 1. Dùng biến `DATABASE_URL` (Khuyến nghị)
Ví dụ:
```bash
# Khi chạy từ máy host (ngoài Docker)
DATABASE_URL=postgresql://<user>:<password>@localhost:15432/<db_name>

# Khi chạy bên trong container Docker (Airflow / Backend)
DATABASE_URL=postgresql://<user>:<password>@postgres:5432/<db_name>
```

### 2. Dùng các biến môi trường riêng lẻ
Nếu không đặt `DATABASE_URL`, module sẽ tự động ghép nối từ các biến:
- `POSTGRES_USER` (mặc định: `postgres`)
- `POSTGRES_PASSWORD` (mặc định: `""`)
- `POSTGRES_HOST` (mặc định: `localhost` khi chạy ngoài host, `postgres` trong container)
- `POSTGRES_PORT` (mặc định: `15432` ngoài host, `5432` trong container)
- `POSTGRES_DB` (mặc định: `postgres`)

---

## 🚀 Hướng dẫn sử dụng

### 1. Kiểm tra kết nối từ dòng lệnh (CLI)

Khởi động PostgreSQL trước nếu chưa chạy:
```bash
docker compose up -d postgres
```

Chạy kiểm tra:
```bash
python database/test_connection.py
# hoặc
python -m database.test_connection
```

---

### 2. Sử dụng trong code Python

#### A. Mở kết nối với Context Manager (An toàn, tự động commit/rollback/close)
```python
from database import get_connection

with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM raw_articles;")
    count = cursor.fetchone()[0]
    print(f"Tổng số bản ghi: {count}")
    cursor.close()
```

#### B. Chèn dữ liệu bài cào vào bảng `raw_articles`
```python
from database import insert_raw_article

record = {
    "source": "vnexpress",
    "external_url": "https://vnexpress.net/bai-viet-mau-123.html",
    "title_raw": "Tiêu đề bài viết mẫu",
    "content_raw": "Nội dung bài viết...",
    "author": "Nguyễn Văn A",
    "published_at": "2026-09-08T10:00:00Z",
    "status": "SUCCESS",
}

new_id = insert_raw_article(record)
print(f"Đã lưu vào raw_articles với ID: {new_id}")
```

#### C. Kiểm tra bài viết đã được cào chưa (Deduplication)
```python
from database import check_url_exists

if check_url_exists("https://vnexpress.net/bai-viet-mau-123.html"):
    print("Bài viết đã tồn tại trong database, bỏ qua.")
```

---

## 📦 Yêu cầu thư viện (Drivers)

Module hỗ trợ cả:
- **`psycopg` (v3)** (Khuyến nghị): `pip install "psycopg[binary]"`
- **`psycopg2`**: `pip install psycopg2-binary`

