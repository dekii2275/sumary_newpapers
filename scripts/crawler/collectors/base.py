"""Module định nghĩa lớp cơ sở (BaseCollector) và thực thể bài viết được khám phá (DiscoveredArticle)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from ..config_loader import SourceConfig


@dataclass
class DiscoveredArticle:
    """Đối tượng đại diện cho một bài viết được khám phá từ RSS, API hoặc Listing."""
    url: str
    title: str | None = None
    published_at: str | None = None
    summary: str | None = None
    author: str | None = None
    thumbnail_url: str | None = None
    source_name: str = ""
    discovery_method: Literal["rss", "api", "listing", "direct"] = "direct"
    raw_metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Chuyển đổi đối tượng sang từ điển thông thường."""
        return {
            "url": self.url,
            "title": self.title,
            "published_at": self.published_at,
            "summary": self.summary,
            "author": self.author,
            "thumbnail_url": self.thumbnail_url,
            "source_name": self.source_name,
            "discovery_method": self.discovery_method,
            "raw_metadata": self.raw_metadata,
        }


class BaseCollector(ABC):
    """Giao diện trừu tượng cho tất cả các Collector (RSS, REST API, Listing HTML)."""

    @abstractmethod
    def collect(
        self, config: SourceConfig, limit: int | None = None
    ) -> list[DiscoveredArticle]:
        """Thu thập danh sách các bài viết mới từ nguồn theo cấu hình.
        
        Args:
            config: Cấu hình nguồn báo.
            limit: Số lượng bài viết tối đa cần lấy.
            
        Returns:
            list[DiscoveredArticle]: Danh sách các bài viết phát hiện được.
        """
        raise NotImplementedError
