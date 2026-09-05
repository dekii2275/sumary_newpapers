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
│   └── 001_create_rawdata.sql # Script SQL khởi tạo bảng rawdata khi tạo container
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
DATABASE_URL=postgresql://tech_admin:news_summary@localhost:15432/tech_news_db

# Khi chạy bên trong container Docker (Airflow / Backend)
DATABASE_URL=postgresql://tech_admin:news_summary@postgres:5432/tech_news_db
```

### 2. Dùng các biến môi trường riêng lẻ
Nếu không đặt `DATABASE_URL`, module sẽ tự động ghép nối từ các biến:
- `POSTGRES_USER` (mặc định: `tech_admin`)
- `POSTGRES_PASSWORD` (mặc định: `news_summary`)
- `POSTGRES_HOST` (mặc định: `localhost` khi chạy ngoài host, `postgres` trong container)
- `POSTGRES_PORT` (mặc định: `15432` ngoài host, `5432` trong container)
- `POSTGRES_DB` (mặc định: `tech_news_db`)

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
    cursor.execute("SELECT COUNT(*) FROM rawdata;")
    count = cursor.fetchone()[0]
    print(f"Tổng số bản ghi: {count}")
    cursor.close()
```

#### B. Chèn dữ liệu bài cào vào bảng `rawdata`
```python
from database import insert_rawdata

record = {
    "source_id": 1,
    "url": "https://vnexpress.net/bai-viet-mau-123.html",
    "final_url": "https://vnexpress.net/bai-viet-mau-123.html",
    "http_status": 200,
    "raw_object_key": "crawl_data/raw/vnexpress/2026/09/05/abc.html.gz",
    "raw_payload_type": "text/html",
    "raw_content_hash": "sha256_hash_here",
    "status": "SUCCESS",
}

new_id = insert_rawdata(record)
print(f"Đã lưu vào rawdata với ID: {new_id}")
```

#### C. Kiểm tra bài viết đã được cào chưa (Deduplication)
```python
from database import check_url_exists

if check_url_exists("https://vnexpress.net/bai-viet-mau-123.html"):
    print("Bài viết đã tồn tại trong database, bỏ qua.")
```

#### D. Lấy các bài báo mới cào gần nhất
```python
from database import get_latest_rawdata

articles = get_latest_rawdata(limit=5)
for article in articles:
    print(article["id"], article["url"], article["status"])
```

---

## 📦 Yêu cầu thư viện (Drivers)

Module hỗ trợ cả:
- **`psycopg` (v3)** (Khuyến nghị): `pip install "psycopg[binary]"`
- **`psycopg2`**: `pip install psycopg2-binary`

