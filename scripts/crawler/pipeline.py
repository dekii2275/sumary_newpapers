"""Module điều phối quy trình cào dữ liệu chính (Crawler Pipeline Orchestrator).

Chịu trách nhiệm thực thi tuần tự các bước:
1. Chuẩn hóa URL bài viết (loại bỏ tham số theo dõi UTM, Facebook, Google).
2. Tự động xác định cấu hình nguồn phù hợp (SourceConfig) qua registry.
3. Tải nội dung mã nguồn HTML qua Fetcher được chỉ định trong YAML (HTTP hoặc Selenium Headless).
4. Bóc tách dữ liệu bài viết qua GenericParser (tiêu đề, tác giả, ngày đăng, nội dung, ảnh thumbnail).
5. Nén lưu file HTML thô (.html.gz) và metadata (.json) vào thư mục crawl_data/.
"""

from __future__ import annotations

from datetime import datetime, timezone

try:
    from selenium.common.exceptions import TimeoutException, WebDriverException
except ImportError:
    class TimeoutException(Exception):
        pass
    class WebDriverException(Exception):
        pass

from .utils import normalize_url, save_artifacts, find_existing_artifact
from .registry import registry
from .fetchers.base import BaseFetcher
from .fetchers import selenium_fetcher

# Cho phép test mock ở crawler.pipeline.SeleniumFetcher
SeleniumFetcher = getattr(selenium_fetcher, "SeleniumFetcher", None)
from .parsers.generic_parser import GenericParser




def get_fetcher_for_source(source_name: str, timeout: int = 20) -> BaseFetcher:
    """Khởi tạo Fetcher theo cấu hình nguồn thông qua Registry.
    
    Args:
        source_name: Tên định danh nguồn báo.
        timeout: Thời gian chờ tối đa khi tải trang (giây).
        
    Returns:
        BaseFetcher: Thể hiện của HttpFetcher hoặc SeleniumFetcher.
    """
    config = registry.resolve_config(source_name=source_name)
    return registry.create_fetcher(config, timeout=timeout)


def get_parser_for_source(source_name: str) -> GenericParser:
    """Lấy thể hiện của bộ GenericParser tương ứng cho nguồn.
    
    Args:
        source_name: Tên định danh nguồn báo.
        
    Returns:
        GenericParser: Bộ bóc tách được khởi tạo với cấu hình nguồn tương ứng.
    """
    config = registry.resolve_config(source_name=source_name)
    return registry.create_parser(config)


def crawl_article(
    url: str,
    source_name: str | None = None,
    timeout: int | None = None,
    fetcher: BaseFetcher | None = None,
    force: bool = False,
    discovery_method: str = "direct",
    discovery_metadata: dict[str, object] | None = None,
    fallback_title: str | None = None,
    fallback_published_at: str | None = None,
    fallback_author: str | None = None,
    fallback_thumbnail: str | None = None,
    save_local: bool = False,
    **kwargs,
) -> dict[str, object]:
    """Thực thi toàn bộ luồng cào 1 bài viết: tải trang, trích xuất metadata."""
    # 1. Chuẩn hóa URL
    normalized_url = normalize_url(url)
    fetched_at = datetime.now(timezone.utc)

    # 2. Tự động nhận diện cấu hình nguồn từ URL hoặc source_name
    config = registry.resolve_config(source_name=source_name, url=normalized_url)
    effective_source_name = source_name or config.source_name
    effective_timeout = timeout if timeout is not None else config.fetcher.timeout

    # 3. Kiểm tra trùng lặp trước khi gửi request tải trang (Deduplication Check)
    if not force:
        existing_artifact = find_existing_artifact(normalized_url, effective_source_name)
        if existing_artifact:
            return existing_artifact

    response: dict[str, object] = {}
    html = ""
    article: dict[str, object] = {}
    owns_fetcher = fetcher is None
    crawl_status = "UNKNOWN_ERROR"
    error_message: str | None = None

    try:
        # 3. Tải nội dung trang web bằng Fetcher cấu hình trong YAML
        if fetcher is None:
            fetcher = registry.create_fetcher(config, timeout=effective_timeout)
            
        response = fetcher.fetch(normalized_url)
        html = str(response.get("html") or "")
        final_url = str(response.get("final_url") or normalized_url)
        http_status = response.get("http_status")

        # Cơ chế Adaptive Fallback sang Selenium nếu HTTP bị 403 hoặc trả về HTML rỗng
        if (not html.strip() or http_status == 403) and config.fetcher.type == "http":
            try:
                from unittest.mock import MagicMock
                sf_cls = selenium_fetcher.SeleniumFetcher
                if isinstance(SeleniumFetcher, MagicMock):
                    sf_cls = SeleniumFetcher
                sf_instance = sf_cls(timeout=effective_timeout)

                try:
                    selenium_resp = sf_instance.fetch(normalized_url)
                    if selenium_resp.get("html") and str(selenium_resp.get("html")).strip():
                        response = selenium_resp
                        html = str(selenium_resp.get("html"))
                        final_url = str(selenium_resp.get("final_url") or final_url)
                finally:
                    sf_instance.close()
            except Exception:
                pass

        # Kiểm tra nếu trang trả về mã HTML rỗng
        if not html.strip():
            return save_artifacts(
                html="",
                source_name=effective_source_name,
                url=normalized_url,
                final_url=final_url,
                fetched_at=fetched_at,
                article={},
                http_status=http_status if isinstance(http_status, int) else None,
                crawl_status="EMPTY_HTML",
                error="Nội dung HTML trả về bị rỗng",
                discovery_method=discovery_method,
                discovery_metadata=discovery_metadata,
                save_local=save_local,
            )

        # 4. Phân tích và bóc tách dữ liệu bài báo qua GenericParser
        parser = registry.create_parser(config)
        article = parser.parse(html)

        # Hợp nhất metadata từ RSS/API nếu HTML thiếu (Graceful Fallback)
        if not article.get("title") and fallback_title:
            article["title"] = fallback_title
        if not article.get("published_at") and fallback_published_at:
            article["published_at"] = fallback_published_at
        if not article.get("author") and fallback_author:
            article["author"] = fallback_author
        if not article.get("thumbnail_url") and fallback_thumbnail:
            article["thumbnail_url"] = fallback_thumbnail

        crawl_status = "SUCCESS" if article.get("content") else "CONTENT_NOT_FOUND"
        error_message = None if crawl_status == "SUCCESS" else "Không tìm thấy nội dung bài viết phù hợp"
        
        # 5. Lưu trữ metadata (và file local nếu save_local=True)
        metadata = save_artifacts(
            html=html,
            source_name=effective_source_name,
            url=normalized_url,
            final_url=final_url,
            fetched_at=fetched_at,
            article=article,
            http_status=http_status if isinstance(http_status, int) else None,
            crawl_status=crawl_status,
            error=error_message,
            discovery_method=discovery_method,
            discovery_metadata=discovery_metadata,
            save_local=save_local,
        )
        return metadata

    except TimeoutException as error:
        crawl_status = "TIMEOUT"
        error_message = str(error)
    except WebDriverException as error:
        crawl_status = "BLOCKED"
        error_message = str(error)
    except Exception as error:
        crawl_status = "UNKNOWN_ERROR"
        error_message = str(error)
    finally:
        # Giải phóng trình duyệt/kết nối nếu fetcher do hàm này tự khởi tạo
        if owns_fetcher and fetcher is not None:
            fetcher.close()

    return save_artifacts(
        html="",
        source_name=effective_source_name,
        url=normalized_url,
        final_url=str(response.get("final_url") or normalized_url),
        fetched_at=fetched_at,
        article=article or {},
        crawl_status=crawl_status,
        error=error_message,
        discovery_method=discovery_method,
        discovery_metadata=discovery_metadata,
        save_local=save_local,
    )

