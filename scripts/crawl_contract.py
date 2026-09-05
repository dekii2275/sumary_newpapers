"""Pure contracts shared by the Step 1 crawler and its tests."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {
    "_ga",
    "dclid",
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}

METADATA_SCHEMA_VERSION = 2
METADATA_FIELDS = (
    "schema_version",
    "source",
    "url",
    "final_url",
    "title",
    "author",
    "published_at",
    "content",
    "thumbnail_url",
    "raw_object_key",
    "raw_payload_type",
    "raw_content_hash",
    "status",
    "http_status",
    "crawl_run_id",
    "fetched_at",
)


def normalize_url(url: str) -> str:
    """Return a safe, deterministic URL for fetching and identity checks."""

    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"Invalid article URL: {url!r}")

    try:
        hostname = parts.hostname
        port = parts.port
    except ValueError as error:
        raise ValueError(f"Invalid article URL: {url!r}") from error

    if not hostname:
        raise ValueError(f"Invalid article URL: {url!r}")

    hostname = hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"

    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"

    clean_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    path = parts.path or "/"

    return urlunsplit((scheme, netloc, path, urlencode(clean_query), ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16]


def safe_source_name(source_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_name.strip())
    return cleaned or "unknown"


def metadata_schema_version(metadata: dict[str, object]) -> int | None:
    """Detect v2 explicitly and identify legacy v1 without upgrading it."""

    if metadata.get("schema_version") == METADATA_SCHEMA_VERSION:
        return METADATA_SCHEMA_VERSION
    if "raw_html_path" in metadata or "crawl_status" in metadata:
        return 1
    return None


def validate_metadata(
    metadata: dict[str, object], *, allow_legacy: bool = False
) -> int:
    """Validate the persisted metadata contract and return its version."""

    version = metadata_schema_version(metadata)
    if version == 1:
        if allow_legacy:
            return version
        raise ValueError("Legacy metadata v1 requires allow_legacy=True")
    if version != METADATA_SCHEMA_VERSION:
        raise ValueError("Metadata must declare schema_version=2")

    missing = [field for field in METADATA_FIELDS if field not in metadata]
    if missing:
        raise ValueError(f"Metadata v2 is missing fields: {', '.join(missing)}")
    if not isinstance(metadata["source"], str) or not metadata["source"]:
        raise ValueError("Metadata source must be a non-empty string")
    if not isinstance(metadata["url"], str) or not metadata["url"]:
        raise ValueError("Metadata url must be a non-empty string")
    if not isinstance(metadata["status"], str) or not metadata["status"]:
        raise ValueError("Metadata status must be a non-empty string")
    if not isinstance(metadata["fetched_at"], str) or not metadata["fetched_at"]:
        raise ValueError("Metadata fetched_at must be an ISO timestamp")

    http_status = metadata["http_status"]
    if http_status is not None and not isinstance(http_status, int):
        raise ValueError("Metadata http_status must be an integer or null")

    return METADATA_SCHEMA_VERSION
