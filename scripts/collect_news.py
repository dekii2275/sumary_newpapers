"""CLI Entrypoint điều phối luồng thu thập tin tức tự động quy mô lớn (Two-Stage News Collector).

Quy trình hoạt động:
1. Stage 1 (Discovery): Quét RSS Feed XML, REST API JSON hoặc Listing HTML để khám phá các bài viết mới nhất.
2. Deduplication: Lọc bỏ các bài đã từng cào trước đó dựa trên PostgreSQL DB (raw_articles) hoặc Local Hash SHA-256.
3. Stage 2 (Extraction): Bóc tách toàn văn HTML qua Crawler Pipeline (GenericParser + Trafilatura fallback).
4. Storage: Lưu trữ file nén mã nguồn .html.gz + json metadata local và tự động ghi vào DB (bảng rawdata & raw_articles).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# Đảm bảo import được các module gốc của dự án như `database`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

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
    parser.add_argument(
        "--save-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Tự động kết nối và lưu dữ liệu cào vào cơ sở dữ liệu PostgreSQL (mặc định: True).",
    )
    parser.add_argument(
        "--from-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Lấy danh sách các nguồn cào trực tiếp từ cơ sở dữ liệu PostgreSQL (mặc định: True).",
    )
    parser.add_argument(
        "--save-local",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Lưu bản sao dữ liệu thô (.html.gz và .json) vào thư mục local crawl_data/ (mặc định: False).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ thực hiện khám phá bài viết (Discovery), không cào nội dung chi tiết.",
    )
    return parser.parse_args()


def process_source(
    source_name: str,
    limit: int = 10,
    force: bool = False,
    delay: float = 1.5,
    dry_run: bool = False,
    save_db: bool = False,
    save_local: bool = False,
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

    # Nạp danh sách bài đã cào sẵn trong DB bằng 1 query duy nhất (Batch URL Check)
    existing_db_urls: set[str] = set()
    if not force and discovered_items:
        try:
            from database.operations import get_existing_urls
            urls_to_check = [item.url for item in discovered_items]
            existing_db_urls = get_existing_urls(urls_to_check)
        except Exception as check_err:
            print(f"⚠️ Cảnh báo kiểm tra trùng lặp DB hàng loạt thất bại: {check_err}")

    stats = {
        "discovered": len(discovered_items),
        "skipped": 0,
        "success": 0,
        "failed": 0,
    }

    if dry_run:
        print("ℹ️ Chế độ Dry-Run bật: Bỏ qua giai đoạn Stage 2 (Extraction & Save DB).")
        return stats

    # Stage 2: Deduplication & Full-text Extraction
    for idx, item in enumerate(discovered_items, 1):
        clean_url = item.url.strip()
        print(f"\n[{idx:02d}/{len(discovered_items):02d}] Xử lý: {item.title or clean_url[:60]}")

        # 1. Kiểm tra trùng lặp qua Database (bảng raw_articles)
        if not force and clean_url in existing_db_urls:
            print(f"   ⏩ BỎ QUA (Đã tồn tại trong Database `raw_articles`)")
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
                save_local=save_local,
            )
            status = result.get("crawl_status")

            if save_db:
                try:
                    from database.operations import save_crawl_result_to_db
                    db_res = save_crawl_result_to_db(result)
                    result["db_saved"] = db_res
                except Exception as db_err:
                    print(f"   ⚠️ Lỗi lưu Database: {db_err}")

            if status == "SUCCESS":
                stats["success"] += 1
                content_str = str(result.get("content_raw") or result.get("content") or "")
                words = len(content_str.split())
                print(f"   ✅ CÀO THÀNH CÔNG! ({words} từ, Tác giả: {result.get('author') or 'N/A'})")
            else:
                stats["failed"] += 1
                print(f"   ⚠️ TRẠNG THÁI: {status} ({result.get('error') or 'Không rõ nguyên nhân'})")

        except Exception as exc:
            stats["failed"] += 1
            print(f"   ❌ LỖI NGOẠI LỆ: {exc}")

    return stats


def run_news_collector(
    source: str | None = None,
    channel_type: str = "all",
    limit: int = 10,
    force: bool = False,
    delay: float = 1.5,
    dry_run: bool = False,
    save_db: bool = True,
    from_db: bool = True,
    save_local: bool = False,
    all_sources: bool = False,
) -> dict[str, int]:
    """Hàm Python API điều phối luồng thu thập tin tức tự động (có thể import và gọi từ Airflow hoặc script khác)."""
    if from_db: # Nạp cấu hình nguồn từ PostgreSQL DB 
        registry.load_from_db()

    all_configs = registry.get_all_configs() if hasattr(registry, "get_all_configs") else registry._configs

    target_sources: list[str] = []
    if source:
        target_sources = [source.lower().strip()]
    elif all_sources:
        target_sources = list(all_configs.keys())
    else:
        for name, cfg in all_configs.items():
            if channel_type == "all" or cfg.channel_type == channel_type:
                target_sources.append(name)

    if not target_sources:
        print("⚠️ Không có nguồn nào phù hợp với bộ lọc chỉ định.")
        print(f"Các nguồn khả dụng hiện có: {list(all_configs.keys())}")
        return {"discovered": 0, "skipped": 0, "success": 0, "failed": 0}

    print(f"\n🚀 KHỞI ĐỘNG HỆ THỐNG THU THẬP TIN TỨC ĐA NGUỒN")
    print(f"   Nạp nguồn từ DB: {'BẬT' if from_db else 'TẮT'} | Danh sách thực thi ({len(target_sources)}): {target_sources}")
    print(f"   Chế độ Dry-Run: {'BẬT' if dry_run else 'TẮT'} | Ép cào lại (--force): {'BẬT' if force else 'TẮT'} | Lưu DB: {'BẬT' if save_db else 'TẮT'} | Lưu Local: {'BẬT' if save_local else 'TẮT'}")

    total_stats = {"discovered": 0, "skipped": 0, "success": 0, "failed": 0}
    start_total = time.time()

    for src in target_sources:
        source_stat = process_source(
            source_name=src,
            limit=limit,
            dry_run=dry_run,
            force=force,
            delay=delay,
            save_db=save_db,
            save_local=save_local,
        )
        for key in total_stats:
            total_stats[key] += source_stat[key]

    total_elapsed = time.time() - start_total
    print(f"\n{'='*70}")
    print(f"📊 BÁO CÁO TỔNG HỢP KẾT QUẢ THU THẬP TIN TỨC")
    print(f"{'='*70}")
    print(f"   - Tổng số bài phát hiện (Discovered): {total_stats['discovered']}")
    if not dry_run:
        print(f"   - Bỏ qua do trùng lặp (Skipped):     {total_stats['skipped']}")
        print(f"   - Bóc tách thành công (Success):     {total_stats['success']}")
        print(f"   - Cào thất bại / Lỗi (Failed):       {total_stats['failed']}")
    print(f"   - Tổng thời gian thực thi:           {total_elapsed:.2f} giây")
    print(f"{'='*70}\n")

    return total_stats


def main() -> None:
    """Điểm khởi chạy chính từ dòng lệnh (CLI)."""
    args = parse_args()
    run_news_collector(
        source=args.source,
        channel_type=args.type,
        limit=args.limit,
        force=args.force,
        delay=args.delay,
        dry_run=args.dry_run,
        save_db=args.save_db,
        from_db=args.from_db,
        save_local=args.save_local,
        all_sources=args.all,
    )


if __name__ == "__main__":
    main()
