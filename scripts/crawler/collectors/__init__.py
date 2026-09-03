"""Package collectors: Quản lý các bộ khám phá tin tức (Stage 1: Discovery) qua RSS, API, Listing."""

from __future__ import annotations

from .base import BaseCollector, DiscoveredArticle
from .rss_collector import RssCollector
from .api_collector import ApiCollector
from .listing_collector import ListingCollector
from ..config_loader import SourceConfig


def get_collector_for_source(config: SourceConfig) -> BaseCollector:
    """Khởi tạo Collector tương ứng theo cấu hình nguồn báo.
    
    Thứ tự ưu tiên:
    1. Nếu channel_type == "rss" hoặc có rss_feeds -> RssCollector
    2. Nếu channel_type == "api" hoặc có api -> ApiCollector
    3. Mặc định hoặc có listing_urls -> ListingCollector
    """
    if config.channel_type == "rss" or config.rss_feeds:
        return RssCollector()
    if config.channel_type == "api" or config.api:
        return ApiCollector()
    return ListingCollector()


__all__ = [
    "BaseCollector",
    "DiscoveredArticle",
    "RssCollector",
    "ApiCollector",
    "ListingCollector",
    "get_collector_for_source",
]
