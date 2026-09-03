"""Module thu thập tin tức qua giao thức RSS / Atom XML Feed (Stage 1: Discovery).

Sử dụng feedparser kết hợp cơ chế phân giải namespace, chuẩn hóa ngày tháng và xử lý XML lỗi.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
import feedparser

from .base import BaseCollector, DiscoveredArticle
from ..config_loader import SourceConfig
from ..utils import normalize_url, clean_text

logger = logging.getLogger(__name__)


class RssCollector(BaseCollector):
    """Bộ thu thập tin tức từ các kênh RSS / Atom Feed XML."""

    def __init__(self, user_agent: str | None = None):
        self.user_agent = (
            user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )

    def _parse_published_date(self, entry: dict[str, object]) -> str | None:
        """Chuẩn hóa ngày xuất bản từ struct_time hoặc chuỗi văn bản về định dạng ISO 8601 UTC."""
        time_struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if time_struct:
            try:
                dt = datetime.fromtimestamp(time.mktime(time_struct), tz=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

        raw_date = entry.get("published") or entry.get("updated")
        if isinstance(raw_date, str):
            return clean_text(raw_date)
        return None

    def _extract_author(self, entry: dict[str, object]) -> str | None:
        """Bóc tách tác giả hỗ trợ cả các namespace (dc:creator, author_detail)."""
        author = entry.get("author")
        if author and isinstance(author, str) and author.strip():
            return clean_text(author)

        author_detail = entry.get("author_detail")
        if isinstance(author_detail, dict) and author_detail.get("name"):
            return clean_text(str(author_detail["name"]))

        dc_creator = entry.get("dc_creator")
        if dc_creator and isinstance(dc_creator, str):
            return clean_text(dc_creator)

        return None

    def _extract_thumbnail(self, entry: dict[str, object]) -> str | None:
        """Bóc tách ảnh đại diện hỗ trợ media:content, media:thumbnail và enclosures."""
        media_content = entry.get("media_content")
        if isinstance(media_content, list) and len(media_content) > 0:
            url = media_content[0].get("url")
            if url:
                return clean_text(str(url))

        media_thumbnail = entry.get("media_thumbnail")
        if isinstance(media_thumbnail, list) and len(media_thumbnail) > 0:
            url = media_thumbnail[0].get("url")
            if url:
                return clean_text(str(url))

        enclosures = entry.get("enclosures")
        if isinstance(enclosures, list) and len(enclosures) > 0:
            for enc in enclosures:
                if "image" in str(enc.get("type", "")):
                    url = enc.get("href") or enc.get("url")
                    if url:
                        return clean_text(str(url))

        return None

    def _extract_summary(self, entry: dict[str, object]) -> str | None:
        """Lấy tóm tắt bài viết từ summary, description hoặc content và loại bỏ thẻ HTML rác."""
        from bs4 import BeautifulSoup

        raw_summary = entry.get("summary") or entry.get("description")
        if not raw_summary and entry.get("content"):
            content = entry.get("content")
            if isinstance(content, list) and len(content) > 0:
                raw_summary = content[0].get("value")

        if isinstance(raw_summary, str) and raw_summary.strip():
            # Xóa các thẻ HTML (thường là <a>, <img>) chèn trong RSS summary
            try:
                soup = BeautifulSoup(raw_summary, "html.parser")
                text = soup.get_text(" ", strip=True)
                return clean_text(text)
            except Exception:
                return clean_text(raw_summary)

        return None


    def collect(
        self, config: SourceConfig, limit: int | None = None
    ) -> list[DiscoveredArticle]:
        """Đọc toàn bộ các kênh RSS trong cấu hình nguồn và trả về danh sách DiscoveredArticle."""
        discovered: list[DiscoveredArticle] = []
        seen_urls: set[str] = set()

        if not config.rss_feeds:
            logger.info("Nguồn %s không có cấu hình rss_feeds.", config.source_name)
            return discovered

        for feed_url in config.rss_feeds:
            if limit and len(discovered) >= limit:
                break

            try:
                # Thiết lập request headers để tránh bị chặn bot
                parsed_feed = feedparser.parse(
                    feed_url,
                    request_headers={"User-Agent": self.user_agent},
                )

                if parsed_feed.bozo and parsed_feed.bozo_exception:
                    logger.debug(
                        "Cảnh báo cú pháp XML tại feed %s: %s",
                        feed_url,
                        parsed_feed.bozo_exception,
                    )

                status = getattr(parsed_feed, "status", 200)
                if status in (403, 429):
                    logger.warning("Feed %s trả về HTTP %d (Bị chặn/Rate limit)", feed_url, status)
                    continue

                for entry in parsed_feed.entries:
                    if limit and len(discovered) >= limit:
                        break

                    raw_link = entry.get("link")
                    if not raw_link or not isinstance(raw_link, str):
                        continue

                    url = normalize_url(raw_link)
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    title = clean_text(entry.get("title"))
                    published_at = self._parse_published_date(entry)
                    author = self._extract_author(entry)
                    summary = self._extract_summary(entry)
                    thumbnail = self._extract_thumbnail(entry)

                    article = DiscoveredArticle(
                        url=url,
                        title=title,
                        published_at=published_at,
                        summary=summary,
                        author=author,
                        thumbnail_url=thumbnail,
                        source_name=config.source_name,
                        discovery_method="rss",
                        raw_metadata={
                            "feed_url": feed_url,
                            "guid": entry.get("id") or entry.get("guid"),
                        },
                    )
                    discovered.append(article)

            except Exception as exc:
                logger.error("Lỗi khi đọc feed %s: %s", feed_url, exc)

        return discovered
