"""Module thu thập tin tức qua cào trang Danh mục / Listing (Stage 1: Discovery).

Dành cho các trang web không hỗ trợ RSS hay API.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests

from .base import BaseCollector, DiscoveredArticle
from ..config_loader import SourceConfig
from ..utils import normalize_url, clean_text

logger = logging.getLogger(__name__)


class ListingCollector(BaseCollector):
    """Bộ thu thập link bài viết từ các trang danh mục / chuyên mục HTML."""

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def _is_article_link(self, url: str, domains: list[str]) -> bool:
        """Kiểm tra xem một URL có phải là link bài viết tiềm năng hay không."""
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()

        # Kiểm tra đúng domain
        domain_match = any(
            netloc == d.lower() or netloc.endswith("." + d.lower()) for d in domains
        )
        if not domain_match:
            return False

        path = parsed.path.lower().strip("/")
        if not path:
            return False

        # Loại trừ các link trang tĩnh, danh mục cha, chính sách, tài khoản
        excluded_patterns = [
            "/tag/", "/tags/", "/category/", "/chuyen-muc/", "/login",
            "/search", "/rss", "/feed", "/contact", "/about", "/privacy",
            ".jpg", ".png", ".gif", ".css", ".js", "#",
        ]
        if any(p in parsed.path.lower() for p in excluded_patterns):
            return False

        # Link bài viết đối với đa số báo Việt Nam (VnExpress, Vietnamnet, Dân trí, CafeF) bắt buộc có đuôi .html / .chn
        if any(v_domain in netloc for v_domain in ["vietnamnet.vn", "vnexpress.net", "cafef.vn", "dantri.com.vn"]):
            return path.endswith(".html") or path.endswith(".chn")

        # Link bài viết quốc tế (như TechCrunch, Medium) thường có năm/tháng hoặc slug dài có số
        is_article = (
            path.endswith(".html")
            or path.endswith(".chn")
            or any(char.isdigit() for char in path)
            or len(path) > 30
        )
        return is_article



    def collect(
        self, config: SourceConfig, limit: int | None = None
    ) -> list[DiscoveredArticle]:
        """Tải các trang danh mục trong listing_urls và trích xuất các link bài viết mới."""
        discovered: list[DiscoveredArticle] = []
        seen_urls: set[str] = set()

        if not config.listing_urls:
            logger.info("Nguồn %s không có cấu hình listing_urls.", config.source_name)
            return discovered

        for listing_url in config.listing_urls:
            if limit and len(discovered) >= limit:
                break

            try:
                response = self.session.get(
                    listing_url,
                    headers=self.default_headers,
                    timeout=20,
                )
                if not response.ok:
                    logger.warning("Không thể tải trang listing %s (HTTP %d)", listing_url, response.status_code)
                    continue

                soup = BeautifulSoup(response.text, "lxml")

                # Tìm tất cả các thẻ a
                for a_tag in soup.find_all("a", href=True):
                    if limit and len(discovered) >= limit:
                        break

                    href = a_tag["href"].strip()
                    full_url = urljoin(listing_url, href)
                    normalized = normalize_url(full_url)

                    if normalized in seen_urls:
                        continue

                    if not self._is_article_link(normalized, config.domains):
                        continue

                    title = clean_text(a_tag.get_text(" ", strip=True))
                    if not title or len(title) < 10:
                        title = clean_text(a_tag.get("title"))

                    seen_urls.add(normalized)
                    article = DiscoveredArticle(
                        url=normalized,
                        title=title,
                        source_name=config.source_name,
                        discovery_method="listing",
                        raw_metadata={"listing_source": listing_url},
                    )
                    discovered.append(article)

            except Exception as exc:
                logger.error("Lỗi khi cào listing %s: %s", listing_url, exc)

        return discovered
