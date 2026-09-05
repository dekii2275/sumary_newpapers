from datetime import datetime

from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator


def hello():
    print("Hello from Airflow!")


with DAG(
    dag_id="test_airflow",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    hello_task = PythonOperator(
        task_id="hello",
        python_callable=hello,
    )