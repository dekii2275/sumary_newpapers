"""DAG Airflow định lịch thu thập tin tức VnExpress (Step 1) và lưu dữ liệu thô vào bảng rawdata."""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from uuid import uuid4

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator

for path in ("/opt/project", "/opt/project/scripts"):
    if path not in sys.path:
        sys.path.insert(0, path)

from crawler.fetchers.selenium_fetcher import SeleniumFetcher  # noqa: E402
from crawler.pipeline import crawl_article  # noqa: E402
from database.operations import insert_rawdata  # noqa: E402


def _configured_urls() -> list[str]:
    """Đọc danh sách các URL bài viết được cấu hình từ biến môi trường CRAWL_URLS (ngăn cách bằng dấu phẩy)."""
    return [
        url.strip()
        for url in os.getenv("CRAWL_URLS", "").split(",")
        if url.strip()
    ]


def run_crawler_batch() -> None:
    """Thực thi cào hàng loạt danh sách URL đã cấu hình và lưu vào CSDL PostgreSQL."""
    urls = _configured_urls()
    if not urls:
        raise AirflowException(
            "Biến môi trường CRAWL_URLS đang rỗng. Hãy cấu hình một hoặc nhiều "
            "URL bài viết (ngăn cách bởi dấu phẩy) trước khi kích hoạt DAG."
        )

    source_id = int(os.getenv("CRAWL_SOURCE_ID", "1"))
    source_name = os.getenv("CRAWL_SOURCE_NAME", "vnexpress")
    timeout = int(os.getenv("CRAWL_TIMEOUT_SECONDS", "20"))
    database_url = os.environ["DATABASE_URL"]
    crawl_run_id = uuid4()
    results: list[dict[str, object]] = []
    failures: list[str] = []

    # Tái sử dụng một phiên trình duyệt Selenium duy nhất cho toàn bộ danh sách URL trong batch để tối ưu hiệu năng
    fetcher = SeleniumFetcher(timeout=timeout)
    try:
        for url in urls:
            record = crawl_article(
                url=url,
                source_name=source_name,
                timeout=timeout,
                fetcher=fetcher,
            )
            record["source_id"] = source_id
            record["crawl_run_id"] = str(crawl_run_id)
            record_id = insert_rawdata(record, database_url)
            status = record.get("status") or record.get("crawl_status") or "UNKNOWN"
            article_url = str(record.get("url") or url)
            result = {"id": record_id, "url": article_url, "status": status}
            results.append(result)
            if status != "SUCCESS":
                failures.append(f"{article_url}: {status}")
    finally:
        fetcher.close()

    print(json.dumps(results, ensure_ascii=False))
    if failures:
        raise AirflowException("Một hoặc nhiều URL cào thất bại: " + "; ".join(failures))


with DAG(
    dag_id="crawl_vnexpress_step1",
    description="Cào các bài báo VnExpress đã cấu hình và lưu vào bảng rawdata",
    schedule="0 */6 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={
        "owner": "news-platform",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["step1", "crawler", "vnexpress"],
) as dag:
    crawl_articles = PythonOperator(
        task_id="crawl_articles",
        python_callable=run_crawler_batch,
    )

