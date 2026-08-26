"""Schedule the Step 1 VnExpress crawler and persist each raw crawl record."""

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

sys.path.insert(0, "/opt/project/scripts")

from crawl_to_db import (  # noqa: E402
    SeleniumFetcher,
    crawl_article,
    insert_rawdata,
)


def _configured_urls() -> list[str]:
    return [
        url.strip()
        for url in os.getenv("CRAWL_URLS", "").split(",")
        if url.strip()
    ]


def run_crawler_batch() -> None:
    urls = _configured_urls()
    if not urls:
        raise AirflowException(
            "CRAWL_URLS is empty. Set it to one or more comma-separated "
            "article URLs before enabling the DAG."
        )

    source_id = int(os.getenv("CRAWL_SOURCE_ID", "1"))
    source_name = os.getenv("CRAWL_SOURCE_NAME", "vnexpress")
    timeout = int(os.getenv("CRAWL_TIMEOUT_SECONDS", "20"))
    database_url = os.environ["DATABASE_URL"]
    crawl_run_id = uuid4()
    results: list[dict[str, object]] = []
    failures: list[str] = []

    # One browser session is reused for the sequential Step 1 batch.
    fetcher = SeleniumFetcher(timeout=timeout)
    try:
        for url in urls:
            record = crawl_article(
                url=url,
                source_id=source_id,
                source_name=source_name,
                timeout=timeout,
                fetcher=fetcher,
                crawl_run_id=crawl_run_id,
            )
            record_id = insert_rawdata(record, database_url)
            result = {"id": record_id, "url": record.url, "status": record.status}
            results.append(result)
            if record.status != "SUCCESS":
                failures.append(f"{record.url}: {record.status}")
    finally:
        fetcher.close()

    print(json.dumps(results, ensure_ascii=False))
    if failures:
        raise AirflowException("One or more URLs failed: " + "; ".join(failures))


with DAG(
    dag_id="crawl_vnexpress_step1",
    description="Crawl configured VnExpress articles into the rawdata table",
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
