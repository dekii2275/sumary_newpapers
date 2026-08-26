# Airflow scheduler cho Step 1

Stack Airflow được thêm vào Docker Compose để chạy crawler định kỳ. Airflow dùng
PostgreSQL riêng cho metadata của chính nó; crawler vẫn ghi dữ liệu nghiệp vụ vào
PostgreSQL `news_db` hiện tại, bảng `rawdata`.

## Khởi động

Tạo file `.env` ở thư mục gốc (không commit file này):

```dotenv
CRAWL_URLS=https://vnexpress.net/duong-dan-bai-viet-1.html,https://vnexpress.net/duong-dan-bai-viet-2.html
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=change-me
```

`CRAWL_URLS` là danh sách URL bài báo, phân cách bằng dấu phẩy. DAG hiện chạy
theo lịch mỗi 6 giờ (`0 */6 * * *`) và mặc định bị pause khi mới tạo.

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
đồng thời thêm một record vào bảng `rawdata`. Các URL lỗi được ghi với trạng thái
thất bại, batch tiếp tục xử lý URL còn lại, và task Airflow sẽ retry/đánh dấu lỗi
để dễ theo dõi.

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
