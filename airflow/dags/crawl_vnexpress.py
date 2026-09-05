"""DAG Airflow định lịch thu thập tin tức VnExpress (Step 1) và lưu dữ liệu thô vào bảng rawdata."""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from uuid import UUID, uuid4

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator

for path in ("/opt/project", "/opt/project/scripts"):
    if path not in sys.path:
        sys.path.insert(0, path)

from crawl_to_db import (  # noqa: E402
    SeleniumFetcher,
    crawl_article,
    find_rawdata,
    insert_rawdata,
    normalize_url,
)
from crawl_config import (  # noqa: E402
    parse_configured_urls,
    schedule_for_manual_urls,
    stable_crawl_run_id,
)


def _configured_urls() -> list[str]:
    try:
        return parse_configured_urls(
            os.getenv("CRAWL_URLS", ""), normalize_url
        )
    except ValueError as error:
        raise AirflowException(str(error)) from error


def _crawl_run_id_from_context(context: dict[str, object]) -> UUID:
    dag_run = context.get("dag_run")
    airflow_run_id = getattr(dag_run, "run_id", None)
    dag_id = getattr(dag_run, "dag_id", "crawl_vnexpress_step1")
    if airflow_run_id:
        return stable_crawl_run_id(str(dag_id), str(airflow_run_id))
    # Direct invocation outside Airflow is a new crawl run.
    return uuid4()


def run_crawler_batch(**context: object) -> None:
    urls = _configured_urls()
    if not urls:
        raise AirflowException(
            "CRAWL_URLS is empty. Configure one or more comma-separated "
            "article URLs, restart Airflow, then trigger this manual DAG."
        )

    source_id = int(os.getenv("CRAWL_SOURCE_ID", "1"))
    source_name = os.getenv("CRAWL_SOURCE_NAME", "vnexpress")
    timeout = int(os.getenv("CRAWL_TIMEOUT_SECONDS", "20"))
    database_url = os.environ["DATABASE_URL"]
    crawl_run_id = _crawl_run_id_from_context(context)
    results: list[dict[str, object]] = []
    failures: list[str] = []

    # Tái sử dụng một phiên trình duyệt Selenium duy nhất cho toàn bộ danh sách URL trong batch để tối ưu hiệu năng
    fetcher = SeleniumFetcher(timeout=timeout)
    try:
        for url in urls:
            normalized_url = normalize_url(url)
            existing = find_rawdata(
                source_id, normalized_url, crawl_run_id, database_url
            )
            if existing and existing[1] == "SUCCESS":
                results.append(
                    {
                        "id": existing[0],
                        "url": normalized_url,
                        "status": "SKIPPED_EXISTING",
                    }
                )
                continue

            record = crawl_article(
                url=normalized_url,
                source_id=source_id,
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
    description="Crawl configured VnExpress articles into the rawdata table",
    # An empty manual URL list must not create scheduled runs that can only
    # fail. Configure CRAWL_URLS and restart the Airflow containers to enable
    # the six-hour schedule again.
    schedule=schedule_for_manual_urls(
        os.getenv("CRAWL_URLS", ""),
        os.getenv("CRAWL_SCHEDULE", "0 */6 * * *"),
    ),
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

