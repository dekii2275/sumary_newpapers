"""Module thu thập tin tức qua REST API JSON (Stage 1: Discovery).

Hỗ trợ Rate Limiting, Phân trang đa hình, Circuit Breaker và trích xuất Schema mềm dẻo.
"""

from __future__ import annotations

import logging
import time
import requests

from .base import BaseCollector, DiscoveredArticle
from ..config_loader import SourceConfig
from ..utils import normalize_url, clean_text

logger = logging.getLogger(__name__)


def _get_nested_val(data: dict[str, object], path: str) -> object | None:
    """Truy xuất giá trị từ dict lồng nhau theo chuỗi phân cách bởi dấu chấm (ví dụ: 'user.name')."""
    if not path:
        return None
    keys = path.split(".")
    curr: object = data
    for key in keys:
        if isinstance(curr, dict) and key in curr:
            curr = curr[key]
        else:
            return None
    return curr


class ApiCollector(BaseCollector):
    """Bộ thu thập tin tức từ các REST API (JSON)."""

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI News Ingestion Collector/1.0",
            "Accept": "application/json",
        }

    def collect(
        self, config: SourceConfig, limit: int | None = None
    ) -> list[DiscoveredArticle]:
        """Gọi API theo cấu hình, xử lý phân trang và trích xuất danh sách DiscoveredArticle."""
        discovered: list[DiscoveredArticle] = []
        api_cfg = config.api
        if not api_cfg:
            logger.info("Nguồn %s không có cấu hình API.", config.source_name)
            return discovered

        seen_urls: set[str] = set()
        headers = {**self.default_headers, **api_cfg.headers}
        base_params = dict(api_cfg.params)

        pagination = api_cfg.pagination
        max_pages = pagination.max_pages if pagination else 1
        page_param = pagination.param_name if pagination else "page"
        page_size = pagination.page_size if pagination else 20
        paging_type = pagination.type if pagination else "page"

        consecutive_5xx = 0
        max_consecutive_5xx = 3
        max_page_retries = 3

        for page_idx in range(1, max_pages + 1):
            if limit and len(discovered) >= limit:
                break

            params = dict(base_params)
            if pagination:
                if paging_type == "offset":
                    params[page_param] = (page_idx - 1) * page_size
                else:
                    params[page_param] = page_idx

            data = None
            circuit_broken = False

            for attempt in range(max_page_retries):
                try:
                    # Tuân thủ rate limit delay trước khi gửi request
                    if api_cfg.rate_limit_delay > 0:
                        time.sleep(api_cfg.rate_limit_delay)

                    response = self.session.request(
                        method=api_cfg.method,
                        url=api_cfg.url,
                        headers=headers,
                        params=params,
                        timeout=20,
                    )

                    # Xử lý Rate Limit 429
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning("API %s bị 429 Rate Limit. Tạm dừng %d giây...", config.source_name, retry_after)
                        time.sleep(retry_after)
                        continue

                    # Circuit Breaker cho 5xx
                    if response.status_code >= 500:
                        consecutive_5xx += 1
                        logger.error("API %s lỗi 5xx (%d). Lần thứ %d.", config.source_name, response.status_code, consecutive_5xx)
                        if consecutive_5xx >= max_consecutive_5xx:
                            logger.critical("Kích hoạt Circuit Breaker: Tạm dừng cào nguồn API %s.", config.source_name)
                            circuit_broken = True
                            break
                        continue
                    else:
                        consecutive_5xx = 0

                    if not response.ok:
                        logger.error("API %s trả về mã lỗi %d: %s", config.source_name, response.status_code, response.text[:200])
                        circuit_broken = True
                        break

                    data = response.json()
                    break
                except Exception as exc:
                    logger.error("Lỗi khi thu thập API %s tại trang %d: %s", config.source_name, page_idx, exc)
                    circuit_broken = True
                    break

            if circuit_broken or data is None:
                break

            items: list[dict[str, object]] = []

            if api_cfg.data_path:
                nested = _get_nested_val(data, api_cfg.data_path)
                if isinstance(nested, list):
                    items = nested
            elif isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                # Thử tự nhận diện danh sách items nếu là dict
                for key in ("items", "articles", "data", "posts", "results"):
                    if isinstance(data.get(key), list):
                        items = data[key]
                        break

            if not items:
                logger.info("API %s không còn dữ liệu ở trang %d.", config.source_name, page_idx)
                break

            mapping = api_cfg.field_mapping
            for item in items:
                if limit and len(discovered) >= limit:
                    break
                if not isinstance(item, dict):
                    continue

                # Bóc tách URL với cơ chế alias fallback
                raw_url = (
                    _get_nested_val(item, mapping.get("url", "url"))
                    or item.get("url")
                    or item.get("link")
                    or item.get("canonical_url")
                )
                if not raw_url or not isinstance(raw_url, str):
                    continue

                url = normalize_url(raw_url)
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = clean_text(
                    str(
                        _get_nested_val(item, mapping.get("title", "title"))
                        or item.get("title")
                        or item.get("headline")
                        or ""
                    )
                )

                published_at = clean_text(
                    str(
                        _get_nested_val(item, mapping.get("published_at", "published_at"))
                        or item.get("published_at")
                        or item.get("created_at")
                        or ""
                    )
                )

                summary = clean_text(
                    str(
                        _get_nested_val(item, mapping.get("summary", "description"))
                        or item.get("summary")
                        or item.get("description")
                        or ""
                    )
                )

                author = clean_text(
                    str(
                        _get_nested_val(item, mapping.get("author", "author"))
                        or item.get("author")
                        or ""
                    )
                )

                thumbnail = clean_text(
                    str(
                        _get_nested_val(item, mapping.get("thumbnail_url", "thumbnail_url"))
                        or item.get("cover_image")
                        or item.get("image")
                        or ""
                    )
                )

                article = DiscoveredArticle(
                    url=url,
                    title=title,
                    published_at=published_at,
                    summary=summary,
                    author=author,
                    thumbnail_url=thumbnail,
                    source_name=config.source_name,
                    discovery_method="api",
                    raw_metadata=item,
                )
                discovered.append(article)

        return discovered

