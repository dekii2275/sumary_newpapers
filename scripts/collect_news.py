"""CLI Entrypoint điều phối luồng thu thập tin tức tự động quy mô lớn (Two-Stage News Collector).

Quy trình hoạt động:
1. Stage 1 (Discovery): Quét RSS Feed XML, REST API JSON hoặc Listing HTML để khám phá các bài viết mới nhất.
2. Deduplication: Lọc bỏ các bài đã từng cào trước đó dựa trên URL hash SHA-256 (tiết kiệm băng thông và CPU).
3. Stage 2 (Extraction): Bóc tách toàn văn HTML qua Crawler Pipeline (GenericParser + Trafilatura fallback).
4. Storage: Lưu trữ file nén mã nguồn .html.gz và tệp metadata chuẩn .json vào crawl_data/.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from crawler.registry import registry
from crawler.collectors import get_collector_for_source, DiscoveredArticle
from crawler.pipeline import crawl_article
from crawler.utils import find_existing_artifact


def parse_args() -> argparse.Namespace:
    """Phân tích các tham số dòng lệnh."""
    parser = argparse.ArgumentParser(
        description="Điều phối thu thập tin tức tự động qua RSS, API và HTML Crawler."
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Tên định danh nguồn cần cào (ví dụ: vnexpress, cafef, techcrunch, devto, vietnamnet).",
    )
    parser.add_argument(
        "--type",
        choices=["all", "rss", "api", "html"],
        default="all",
        help="Lọc các nguồn theo loại kênh thu thập (mặc định: all).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Số lượng bài viết tối đa cần khám phá cho mỗi nguồn (mặc định: 10).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ chạy bước Discovery (RSS/API) để xem danh sách bài mới, không tải HTML hay ghi đĩa.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bỏ qua bộ lọc trùng lặp, ép buộc cào lại bài viết dù đã lưu trữ trước đó.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Khoảng trễ cơ sở giữa các lượt request tải HTML để tránh bị chặn IP (giây, mặc định: 1.5).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Chạy toàn bộ các nguồn đã được đăng ký trong hệ thống.",
    )
    return parser.parse_args()


def process_source(
    source_name: str,
    limit: int,
    dry_run: bool,
    force: bool,
    delay: float,
) -> dict[str, int]:
    """Thực thi thu thập cho một nguồn báo cụ thể."""
    config = registry.get_config_by_name(source_name)
    if not config:
        print(f"❌ Không tìm thấy cấu hình cho nguồn: '{source_name}'")
        return {"discovered": 0, "skipped": 0, "success": 0, "failed": 0}

    print(f"\n{'='*70}")
    print(f"📡 BẮT ĐẦU THU THẬP NGUỒN: [{config.display_name or config.source_name}]")
    print(f"   Loại kênh: {config.channel_type.upper()} | Giới hạn: {limit} bài")
    print(f"{'='*70}")

    # Stage 1: Discovery
    collector = get_collector_for_source(config)
    start_time = time.time()
    discovered_items = collector.collect(config, limit=limit)
    elapsed_disc = time.time() - start_time

    print(f"🔍 [Stage 1 - Discovery] Tìm thấy {len(discovered_items)} bài viết ({elapsed_disc:.2f}s)")

    if dry_run:
        print("\n--- [CHẾ ĐỘ DRY-RUN: DANH SÁCH BÀI VIẾT KHÁM PHÁ] ---")
        for idx, item in enumerate(discovered_items, 1):
            pub = item.published_at or "Không rõ ngày"
            print(f"  {idx:02d}. [{pub}] {item.title or 'Không tiêu đề'}")
            print(f"      URL: {item.url}")
            if item.summary:
                print(f"      Tóm tắt: {item.summary[:120]}...")
        return {"discovered": len(discovered_items), "skipped": 0, "success": 0, "failed": 0}

    # Stage 2: Deduplication & Full-text Extraction
    stats = {
        "discovered": len(discovered_items),
        "skipped": 0,
        "success": 0,
        "failed": 0,
    }

    for idx, item in enumerate(discovered_items, 1):
        print(f"\n[{idx:02d}/{len(discovered_items):02d}] Xử lý: {item.title or item.url[:60]}")

        # Kiểm tra trùng lặp trước khi gửi request tải trang
        if not force:
            existing = find_existing_artifact(item.url, config.source_name)
            if existing:
                print(f"   ⏩ BỎ QUA (Đã cào trước đó lúc {existing.get('fetched_at')})")
                stats["skipped"] += 1
                continue

        # Jitter delay lịch sự giữa các request cào HTML
        if delay > 0:
            sleep_time = delay + random.uniform(0.5, 1.5)
            time.sleep(sleep_time)

        # Cào toàn văn HTML qua pipeline
        try:
            result = crawl_article(
                url=item.url,
                source_name=config.source_name,
                force=force,
                discovery_method=item.discovery_method,
                discovery_metadata=item.raw_metadata,
                fallback_title=item.title,
                fallback_published_at=item.published_at,
                fallback_author=item.author,
                fallback_thumbnail=item.thumbnail_url,
            )
            status = result.get("crawl_status")
            if status == "SUCCESS":
                stats["success"] += 1
                words = len((result.get("content") or "").split())
                print(f"   ✅ CÀO THÀNH CÔNG! ({words} từ, Tác giả: {result.get('author') or 'N/A'})")
                print(f"      File lưu: {result.get('raw_html_path')}")
            else:
                stats["failed"] += 1
                print(f"   ⚠️ TRẠNG THÁI: {status} ({result.get('error') or 'Không rõ nguyên nhân'})")
        except Exception as exc:
            stats["failed"] += 1
            print(f"   ❌ LỖI NGOẠI LỆ: {exc}")

    return stats


def main() -> None:
    """Điểm khởi chạy chính."""
    args = parse_args()
    all_configs = registry.get_all_configs() if hasattr(registry, "get_all_configs") else registry._configs

    target_sources: list[str] = []
    if args.source:
        target_sources = [args.source.lower().strip()]
    elif args.all:
        target_sources = list(all_configs.keys())
    else:
        # Nếu không chỉ định, lọc theo --type
        for name, cfg in all_configs.items():
            if args.type == "all" or cfg.channel_type == args.type:
                target_sources.append(name)

    if not target_sources:
        print("⚠️ Không có nguồn nào phù hợp với bộ lọc chỉ định.")
        print(f"Các nguồn khả dụng hiện có: {list(all_configs.keys())}")
        sys.exit(1)

    print(f"\n🚀 KHỞI ĐỘNG HỆ THỐNG THU THẬP TIN TỨC ĐA NGUỒN")
    print(f"   Danh sách nguồn thực thi ({len(target_sources)}): {target_sources}")
    print(f"   Chế độ Dry-Run: {'BẬT' if args.dry_run else 'TẮT'} | Ép cào lại (--force): {'BẬT' if args.force else 'TẮT'}")

    total_stats = {"discovered": 0, "skipped": 0, "success": 0, "failed": 0}
    start_total = time.time()

    for src in target_sources:
        source_stat = process_source(
            source_name=src,
            limit=args.limit,
            dry_run=args.dry_run,
            force=args.force,
            delay=args.delay,
        )
        for key in total_stats:
            total_stats[key] += source_stat[key]

    total_elapsed = time.time() - start_total
    print(f"\n{'='*70}")
    print(f"📊 BÁO CÁO TỔNG HỢP KẾT QUẢ THU THẬP TIN TỨC")
    print(f"{'='*70}")
    print(f"   - Tổng số bài phát hiện (Discovered): {total_stats['discovered']}")
    if not args.dry_run:
        print(f"   - Bỏ qua do trùng lặp (Skipped):     {total_stats['skipped']}")
        print(f"   - Bóc tách thành công (Success):     {total_stats['success']}")
        print(f"   - Cào thất bại / Lỗi (Failed):       {total_stats['failed']}")
    print(f"   - Tổng thời gian thực thi:           {total_elapsed:.2f} giây")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
