# Airflow scheduler cho Step 1

Stack Airflow được thêm vào Docker Compose để chạy crawler định kỳ. Airflow dùng
PostgreSQL riêng cho metadata của chính nó; crawler vẫn ghi dữ liệu nghiệp vụ vào
PostgreSQL `news_db` hiện tại, bảng `rawdata`.

## Khởi động

Tạo file `.env` ở thư mục gốc bằng cách copy từ `.env.example` (không commit file `.env` này):

```bash
cp .env.example .env
```

Cấu hình các biến chính theo nhu cầu:

```dotenv
CRAWL_URLS=https://vnexpress.net/duong-dan-bai-viet-1.html,https://vnexpress.net/duong-dan-bai-viet-2.html
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=change-me
```

`CRAWL_URLS` là danh sách URL bài báo, phân cách bằng dấu phẩy. URL được
chuẩn hóa, loại tracking parameters và loại trùng trước khi crawl.

Ở Step 1, nếu `CRAWL_URLS` rỗng thì DAG chuyển sang manual-only mode
(`schedule=None`), vì vậy Airflow không tự tạo các scheduled run chắc chắn thất
bại. Sau khi điền URL và restart các container Airflow, DAG dùng lịch trong
`CRAWL_SCHEDULE` (mặc định mỗi 6 giờ: `0 */6 * * *`). Nếu trigger khi chưa cấu
hình URL, task vẫn fail rõ ràng với thông báo cấu hình.

Khởi động các service:

```bash
docker compose up -d --build airflow-init airflow-webserver airflow-scheduler
```

Mở Airflow tại <http://localhost:18088>, đăng nhập bằng tài khoản trong `.env`,
bật DAG `crawl_vnexpress_step1`, rồi bấm **Trigger DAG** để chạy thử.

Xem log:

```bash
docker compose logs -f airflow-scheduler
```

Raw HTML gzip và metadata JSON vẫn được ghi vào `crawl_data/`; mỗi lần crawl
đồng thời thêm hoặc cập nhật một record vào bảng `rawdata`. `crawl_run_id` được
sinh deterministic từ Airflow `dag_id/run_id`, nên retry của cùng một DagRun
không tạo record mới cho URL đã thành công. Artifact raw cũng dùng path ổn định
theo source/URL/run và được ghi atomically.

Một URL lỗi không dừng các URL tiếp theo. Task có thể retry; các record đã thành
công sẽ được bỏ qua, còn record lỗi được cập nhật lại thay vì insert trùng.

## Metadata schema v2

Metadata mới có `schema_version=2` và các trường:

```text
schema_version, source, url, final_url, title, author, published_at, content,
thumbnail_url, raw_object_key, raw_payload_type, raw_content_hash, status,
http_status, crawl_run_id, fetched_at
```

`error_type` và `error_message` được giữ thêm để chẩn đoán. Các file v1 có
`raw_html_path`/`crawl_status` không bị rewrite; có thể kiểm tra orphan và hash
bằng command read-only:

```bash
python scripts/reconcile_crawl_artifacts.py
```

Khi chạy trong container Airflow:

```bash
docker compose exec airflow-scheduler \
  python /opt/project/scripts/reconcile_crawl_artifacts.py
```

## Dừng và reset dữ liệu local

```bash
docker compose down
docker compose down -v
```

`docker compose down -v` xoá metadata Airflow và dữ liệu PostgreSQL local; chỉ
dùng khi muốn reset môi trường phát triển.

## Rawdata schema

The canonical crawl fields in `rawdata` are:

```text
id, source_id, url, final_url, http_status,
raw_object_key, raw_payload_type, raw_content_hash,
crawl_run_id, status, fetched_at
```

`crawl_run_id` is shared by all URLs processed in one Airflow DAG run.
`raw_payload_type` is `text/html` when a rendered HTML payload is saved.
The legacy diagnostic fields `error_type`, `error_message`, and `created_at`
remain for backward compatibility with existing records.
