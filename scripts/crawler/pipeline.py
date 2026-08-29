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
    **kwargs,
) -> dict[str, object]:
    """Thực thi toàn bộ luồng cào 1 bài viết: tải trang, trích xuất, lưu artifact cục bộ.
    
    Args:
        url: Đường dẫn URL của bài viết.
        source_name: Tên nguồn bài viết (nếu None sẽ tự động suy luận từ tên miền URL).
        timeout: Thời gian timeout tải trang (nếu None sẽ lấy từ cấu hình nguồn).
        fetcher: Thể hiện fetcher dùng lại (nếu có, ví dụ khi cào theo lô).
        force: Nếu True, ép buộc cào lại bài viết dù đã từng cào trước đó (mặc định: False).
        
    Returns:
        dict[str, object]: Từ điển metadata bài viết được lưu trữ trong crawl_data/metadata/.
    """
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


    response: dict[str, str | None] = {}
    html = ""
    article: dict[str, str | None] = {}
    owns_fetcher = fetcher is None
    crawl_status = "UNKNOWN_ERROR"
    error_message: str | None = None

    try:
        # 3. Tải nội dung trang web bằng Fetcher cấu hình trong YAML
        if fetcher is None:
            fetcher = registry.create_fetcher(config, timeout=effective_timeout)
            
        response = fetcher.fetch(normalized_url)
        html = response.get("html") or ""
        final_url = response.get("final_url") or normalized_url

        # Kiểm tra nếu trang trả về mã HTML rỗng
        if not html.strip():
            return save_artifacts(
                html="",
                source_name=effective_source_name,
                url=normalized_url,
                final_url=final_url,
                fetched_at=fetched_at,
                article={},
                crawl_status="EMPTY_HTML",
                error="Nội dung HTML trả về bị rỗng",
            )

        # 4. Phân tích và bóc tách dữ liệu bài báo qua GenericParser
        parser = registry.create_parser(config)
        article = parser.parse(html)
        
        crawl_status = "SUCCESS" if article.get("content") else "CONTENT_NOT_FOUND"
        error_message = None if crawl_status == "SUCCESS" else "Không tìm thấy nội dung bài viết phù hợp"
        
        # 5. Lưu trữ tệp thô nén .html.gz và tệp metadata .json trong crawl_data/
        metadata = save_artifacts(
            html=html,
            source_name=effective_source_name,
            url=normalized_url,
            final_url=final_url,
            fetched_at=fetched_at,
            article=article,
            crawl_status=crawl_status,
            error=error_message,
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
        final_url=response.get("final_url") if response else normalized_url,
        fetched_at=fetched_at,
        article={},
        crawl_status=crawl_status,
        error=error_message,
    )
