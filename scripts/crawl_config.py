"""Configuration helpers for the manual Step 1 Airflow mode."""

from __future__ import annotations

from collections.abc import Callable
from uuid import NAMESPACE_URL, UUID, uuid5


def parse_configured_urls(
    raw_urls: str, normalizer: Callable[[str], str]
) -> list[str]:
    """Normalize, validate, and de-duplicate comma-separated article URLs."""

    urls: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    for raw_url in raw_urls.split(","):
        raw_url = raw_url.strip()
        if not raw_url:
            continue
        try:
            normalized_url = normalizer(raw_url)
        except ValueError:
            invalid.append(raw_url)
            continue
        if normalized_url not in seen:
            seen.add(normalized_url)
            urls.append(normalized_url)

    if invalid:
        joined = ", ".join(repr(url) for url in invalid)
        raise ValueError(f"CRAWL_URLS contains invalid URL(s): {joined}")
    return urls


def schedule_for_manual_urls(raw_urls: str, default_schedule: str) -> str | None:
    """Disable scheduled runs until manual URLs have been configured."""

    return default_schedule if raw_urls.strip() else None


def stable_crawl_run_id(dag_id: str, airflow_run_id: str) -> UUID:
    """Derive the same UUID for every retry of one Airflow DagRun."""

    return uuid5(NAMESPACE_URL, f"airflow://{dag_id}/{airflow_run_id}")
