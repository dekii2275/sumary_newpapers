"""DAG Airflow (Test) điều phối luồng cào tin tức tự động đa nguồn (Auto News Collector).

Clone từ file chính auto_collect_news_dag.py để phục vụ việc test tính năng cào dữ liệu
vào thời điểm 19:30 UTC+7 (12:30 UTC).
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
import pendulum
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator

# Thêm đường dẫn project vào sys.path
for path in (
    "/opt/project",
    "/opt/project/scripts",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts")),
):
    if path not in sys.path and os.path.exists(path):
        sys.path.insert(0, path)

from scripts.collect_news import run_news_collector  # noqa: E402


def execute_news_collection(**context: object) -> None:
    """Task callable chạy pipeline cào tin tức tự động tiêu chuẩn."""
    # Nếu có cấu hình qua biến môi trường thì truyền vào, ngược lại gọi run_news_collector() không tham số
    kwargs = {}
    if os.getenv("CRAWL_SOURCE"):
        kwargs["source"] = os.getenv("CRAWL_SOURCE")
    if os.getenv("CRAWL_LIMIT"):
        kwargs["limit"] = int(os.getenv("CRAWL_LIMIT"))
    if os.getenv("CRAWL_FORCE"):
        kwargs["force"] = os.getenv("CRAWL_FORCE", "").lower() == "true"

    stats = run_news_collector(**kwargs)

    print(f"📊 Kết quả Airflow DagRun (Test): {stats}")
    if stats.get("failed", 0) > 0 and stats.get("success", 0) == 0 and stats.get("discovered", 0) > 0:
        raise AirflowException("Tất cả các lượt cào bài viết đều thất bại.")


with DAG(
    dag_id="test_auto_news_collector",
    description="DAG Test điều phối thu thập tin tức tự động lúc 19:30 UTC+7",
    schedule="0 20 * * *",  # Hằng ngày (Giờ UTC+7 - Asia/Ho_Chi_Minh)
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={
        "owner": "news-platform-test",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["test", "crawler", "multi-source", "postgres"],
) as dag:
    task_collect = PythonOperator(
        task_id="test_collect_news_task",
        python_callable=execute_news_collection,
    )
