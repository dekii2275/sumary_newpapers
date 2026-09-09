"""Module quản lý đăng ký trung tâm (Source Registry).

Chịu trách nhiệm:
1. Quét và tải toàn bộ các file cấu hình YAML nguồn báo khi khởi động.
2. Tự động nhận diện nguồn báo tương ứng dựa trên tên miền (domain) của URL.
3. Tự động khởi tạo Fetcher (HTTP / Selenium) và GenericParser dựa 100% vào cấu hình YAML.
"""

from __future__ import annotations

from urllib.parse import urlparse
from .config_loader import SourceConfig, load_all_configs
from .fetchers.base import BaseFetcher
from .fetchers.http_fetcher import HttpFetcher
from .fetchers.selenium_fetcher import SeleniumFetcher
from .parsers.generic_parser import GenericParser


class SourceRegistry:
    """Registry trung tâm quản lý cấu hình nguồn cào, tự động ánh xạ domain và tạo fetcher/parser."""

    def __init__(self):
        self._configs: dict[str, SourceConfig] = {}
        self._domain_to_source: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        """Đọc lại toàn bộ các file cấu hình nguồn (.yaml) từ thư mục configs/sources/."""
        self._configs = load_all_configs()
        self._domain_to_source.clear()
        for source_name, config in self._configs.items():
            for domain in config.domains:
                # Lưu tên miền chữ thường để tra cứu không phân biệt hoa thường
                self._domain_to_source[domain.lower().strip()] = source_name

    def load_from_db(self, database_url: str | None = None) -> dict[str, SourceConfig]:
        """Nạp danh sách các nguồn hoạt động từ PostgreSQL Database (bảng sources)."""
        try:
            from database.operations import get_active_sources_from_db
            db_sources = get_active_sources_from_db(database_url=database_url)
        except Exception as e:
            print(f"⚠️ Cảnh báo: Không thể nạp nguồn từ Database: {e}")
            return self._configs

        db_configs: dict[str, SourceConfig] = {}
        for row in db_sources:
            s_name = row["name"].lower().strip()
            s_url = row.get("url") or ""
            s_type = (row.get("source_type") or "").lower()

            parsed = urlparse(s_url)
            domain = parsed.netloc.lower().strip()

            if s_type == "rss" or s_url.endswith(".rss") or ".rss" in s_url or "rss" in s_url:
                channel_type = "rss"
            elif s_type == "api":
                channel_type = "api"
            else:
                channel_type = "html"

            existing_cfg = self._configs.get(s_name)
            if existing_cfg:
                existing_cfg.source_id = row["id"]
                if channel_type == "rss" and s_url and s_url not in existing_cfg.rss_feeds:
                    existing_cfg.rss_feeds.append(s_url)
                elif channel_type == "html" and s_url and s_url not in existing_cfg.listing_urls:
                    existing_cfg.listing_urls.append(s_url)
                if domain and domain not in existing_cfg.domains:
                    existing_cfg.domains.append(domain)
                db_configs[s_name] = existing_cfg
            else:
                cfg = SourceConfig(
                    source_id=row["id"],
                    source_name=s_name,
                    display_name=row["name"].capitalize(),
                    channel_type=channel_type,
                    domains=[domain] if domain else [],
                    rss_feeds=[s_url] if channel_type == "rss" and s_url else [],
                    listing_urls=[s_url] if channel_type == "html" and s_url else [],
                )
                db_configs[s_name] = cfg

            if domain:
                self._domain_to_source[domain] = s_name

        self._configs.update(db_configs)
        return self._configs

    def get_all_configs(self) -> dict[str, SourceConfig]:
        """Lấy toàn bộ các cấu hình nguồn đã đăng ký."""
        return self._configs

    def get_config_by_name(self, source_name: str) -> SourceConfig | None:
        """Tìm cấu hình nguồn theo tên định danh (source_name)."""
        return self._configs.get(source_name.lower().strip())

    def get_config_by_url(self, url: str) -> SourceConfig | None:
        """Tự động tìm cấu hình nguồn khớp với tên miền chính hoặc tên miền phụ (subdomain) của URL."""
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").lower().strip()
        
        # Khớp chính xác tên miền hoặc khớp subdomain (ví dụ: 'vnexpress.net' khớp 'e.vnexpress.net')
        for domain, source_name in self._domain_to_source.items():
            if netloc == domain or netloc.endswith("." + domain):
                return self._configs.get(source_name)

        return None

    def resolve_config(
        self, source_name: str | None = None, url: str | None = None
    ) -> SourceConfig:
        """Giải quyết và trả về SourceConfig theo source_name hoặc tự động phân tích từ URL.
        
        Nếu không khớp nguồn nào, trả về cấu hình mặc định (fallback generic config).
        """
        config = None
        if source_name:
            config = self.get_config_by_name(source_name)
        if not config and url:
            config = self.get_config_by_url(url)

        if not config:
            # Tạo cấu hình generic mặc định nếu không khớp nguồn cấu hình sẵn
            inferred_name = source_name or "generic"
            if url and not source_name:
                domain = urlparse(url).netloc
                inferred_name = domain.replace("www.", "").split(".")[0] or "generic"

            config = SourceConfig(
                source_id=999,
                source_name=inferred_name,
                display_name=inferred_name.capitalize(),
                domains=[urlparse(url).netloc] if url else [],
            )

        return config

    def create_fetcher(
        self, config: SourceConfig, timeout: int | None = None
    ) -> BaseFetcher:
        """Khởi tạo thể hiện Fetcher tương ứng theo trường fetcher.type trong file YAML (HttpFetcher hoặc SeleniumFetcher)."""
        fetch_timeout = timeout if timeout is not None else config.fetcher.timeout
        if config.fetcher.type == "selenium":
            return SeleniumFetcher(timeout=fetch_timeout)
        return HttpFetcher(timeout=fetch_timeout)

    def create_parser(self, config: SourceConfig) -> GenericParser:
        """Khởi tạo bộ bóc tách GenericParser dựa trên cấu hình nguồn."""
        return GenericParser(config)


# Khởi tạo đối tượng Singleton Registry toàn cục
registry = SourceRegistry()
