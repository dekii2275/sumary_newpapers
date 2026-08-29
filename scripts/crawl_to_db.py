"""Điểm khởi chạy dòng lệnh (CLI Entrypoint) để cào bài viết và lưu vào crawl_data/.

Hỗ trợ tự động nhận diện nguồn tin (source) và công cụ tải (fetcher) từ tên miền URL.
"""

from __future__ import annotations

import argparse
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from crawler.fetchers.selenium_fetcher import SeleniumFetcher
from crawler.fetchers.http_fetcher import HttpFetcher
from crawler.parsers.generic_parser import GenericParser
from crawler.registry import registry
from crawler.pipeline import crawl_article


def parse_args() -> argparse.Namespace:
    """Phân tích các đối số dòng lệnh truyền vào."""
    parser = argparse.ArgumentParser(
        description="Cào một bài báo tin tức và lưu kết quả (.html.gz và .json) vào crawl_data/."
    )
    parser.add_argument("url", help="Đường dẫn URL của bài báo cần cào")
    parser.add_argument(
        "--source-name",
        default=None,
        help="Tên nguồn cào (mặc định: tự động nhận diện qua tên miền URL)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Thời gian chờ tải trang tính theo giây (mặc định: lấy từ cấu hình nguồn)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ép buộc cào lại bài viết dù đã từng cào và lưu trữ trước đó",
    )
    return parser.parse_args()


def main() -> None:
    """Hàm thực thi chính khi chạy script từ dòng lệnh."""
    args = parse_args()
    metadata = crawl_article(
        url=args.url,
        source_name=args.source_name,
        timeout=args.timeout,
        force=args.force,
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2, default=str))



if __name__ == "__main__":
    main()
