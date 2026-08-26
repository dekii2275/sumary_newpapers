FROM apache/airflow:2.10.5-python3.12

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

COPY scripts/requirements.txt /tmp/crawler-requirements.txt
RUN pip install --no-cache-dir -r /tmp/crawler-requirements.txt
