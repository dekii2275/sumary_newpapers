"""Report inconsistencies between local crawl artifacts and ``rawdata``.

The command is read-only. It does not delete or rewrite artifacts and is safe
to run before the future uniqueness migration.

Usage:
    python scripts/reconcile_crawl_artifacts.py --database-url "$DATABASE_URL"
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from crawl_contract import metadata_schema_version  # noqa: E402


DEFAULT_DATABASE_URL = (
    "postgresql://news_user:news_password_dev@localhost:15432/news_db"
)


def _safe_project_path(project_root: Path, object_key: str) -> Path | None:
    candidate = (project_root / object_key).resolve()
    root = project_root.resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate


def _hash_gzip(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as gzip_file:
        for chunk in iter(lambda: gzip_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_db_rows(database_url: str) -> list[dict[str, Any]]:
    import psycopg

    query = """
        SELECT id, source_id, url, raw_object_key, raw_content_hash, status, crawl_run_id
        FROM rawdata
        ORDER BY id
    """
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(query).fetchall()
    return [
        {
            "id": row[0],
            "source_id": row[1],
            "url": row[2],
            "raw_object_key": row[3],
            "raw_content_hash": row[4],
            "status": row[5],
            "crawl_run_id": str(row[6]) if row[6] else None,
        }
        for row in rows
    ]


def reconcile(
    *,
    project_root: Path,
    db_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    metadata_root = project_root / "crawl_data" / "metadata"
    raw_root = project_root / "crawl_data" / "raw"
    db_by_key = {
        row["raw_object_key"]: row
        for row in db_rows
        if row.get("raw_object_key")
    }

    report: dict[str, list[dict[str, Any]]] = {
        "raw_files_without_database_row": [],
        "database_rows_without_raw_file": [],
        "hash_mismatches": [],
        "metadata_without_database_reference": [],
        "legacy_metadata_without_database_reference": [],
        "metadata_without_raw_reference": [],
        "database_duplicate_run_urls": [],
    }

    grouped_rows: dict[tuple[Any, Any, Any], list[int]] = {}
    for row in db_rows:
        key = (row.get("source_id"), row.get("crawl_run_id"), row.get("url"))
        grouped_rows.setdefault(key, []).append(int(row["id"]))
    for key, ids in grouped_rows.items():
        if len(ids) > 1:
            report["database_duplicate_run_urls"].append(
                {
                    "source_id": key[0],
                    "crawl_run_id": key[1],
                    "url": key[2],
                    "database_ids": ids,
                }
            )

    raw_files: dict[str, Path] = {}
    if raw_root.exists():
        for raw_path in raw_root.rglob("*.html.gz"):
            key = raw_path.relative_to(project_root).as_posix()
            raw_files[key] = raw_path

    if metadata_root.exists():
        for metadata_path in metadata_root.rglob("*.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                report["metadata_without_database_reference"].append(
                    {"metadata_path": str(metadata_path), "error": str(error)}
                )
                continue
            if not isinstance(metadata, dict):
                continue

            version = metadata_schema_version(metadata)
            raw_key = metadata.get("raw_object_key") or metadata.get("raw_html_path")
            raw_key = str(raw_key) if raw_key else None
            db_row = db_by_key.get(raw_key) if raw_key else None
            if db_row is None:
                item = {
                    "metadata_path": str(metadata_path),
                    "schema_version": version,
                    "raw_object_key": raw_key,
                }
                if version == 1:
                    report["legacy_metadata_without_database_reference"].append(item)
                else:
                    report["metadata_without_database_reference"].append(item)

            if not raw_key:
                report["metadata_without_raw_reference"].append(
                    {"metadata_path": str(metadata_path), "schema_version": version}
                )
                continue

            raw_path = _safe_project_path(project_root, raw_key)
            if raw_path is None or not raw_path.exists():
                report["database_rows_without_raw_file"].append(
                    {
                        "metadata_path": str(metadata_path),
                        "raw_object_key": raw_key,
                        "database_id": db_row["id"] if db_row else None,
                    }
                )
                continue

            expected_hash = metadata.get("raw_content_hash")
            if expected_hash:
                actual_hash = _hash_gzip(raw_path)
                if actual_hash != expected_hash:
                    report["hash_mismatches"].append(
                        {
                            "metadata_path": str(metadata_path),
                            "raw_object_key": raw_key,
                            "expected": expected_hash,
                            "actual": actual_hash,
                            "database_id": db_row["id"] if db_row else None,
                        }
                    )

    for raw_key, raw_path in raw_files.items():
        if raw_key not in db_by_key:
            report["raw_files_without_database_row"].append(
                {"raw_object_key": raw_key, "raw_path": str(raw_path)}
            )

    for row in db_rows:
        raw_key = row.get("raw_object_key")
        if not raw_key:
            continue
        raw_path = _safe_project_path(project_root, str(raw_key))
        if raw_path is None or not raw_path.exists():
            report["database_rows_without_raw_file"].append(
                {"database_id": row["id"], "raw_object_key": raw_key}
            )
        elif row.get("raw_content_hash"):
            actual_hash = _hash_gzip(raw_path)
            if actual_hash != row["raw_content_hash"]:
                report["hash_mismatches"].append(
                    {
                        "database_id": row["id"],
                        "raw_object_key": raw_key,
                        "expected": row["raw_content_hash"],
                        "actual": actual_hash,
                    }
                )

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="PostgreSQL connection URL",
    )
    parser.add_argument(
        "--skip-database",
        action="store_true",
        help="Only inspect metadata/raw files; do not connect to PostgreSQL",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = [] if args.skip_database else load_db_rows(args.database_url)
    report = reconcile(project_root=PROJECT_ROOT, db_rows=rows)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
