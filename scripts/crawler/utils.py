"""Module tiện ích hỗ trợ: chuẩn hóa URL, băm mã hash, làm sạch văn bản và nén lưu artifacts."""

import re
import gzip
import hashlib
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Thư mục gốc của dự án và thư mục lưu trữ dữ liệu cào
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "crawl_data"

# Danh sách các tham số truy vấn theo dõi (tracking params) cần lọc bỏ khỏi URL
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}


def normalize_url(url: str) -> str:
    """Chuẩn hóa URL bằng cách loại bỏ các tham số theo dõi và phân tích (UTM, Facebook click ID, Google click ID).
    
    Args:
        url: Chuỗi URL bài viết ban đầu.
        
    Returns:
        str: Chuỗi URL sạch, chuẩn hóa.
    """
    parts = urlsplit(url.strip())
    clean_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(clean_query), "")
    )


def clean_text(value: str | None) -> str | None:
    """Chuẩn hóa chuỗi văn bản: loại bỏ hoàn toàn các ký tự xuống dòng (\n, \r), thu gọn khoảng trắng thừa và cắt bỏ khoảng trắng ở 2 đầu.
    
    Args:
        value: Chuỗi văn bản thô hoặc None.
        
    Returns:
        str | None: Chuỗi văn bản sạch hoặc None nếu chuỗi rỗng.
    """
    if not value:
        return None
    # Loại bỏ ký tự xuống dòng (\n, \r) và chuẩn hóa khoảng trắng
    value = value.replace("\r", " ").replace("\n", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def url_hash(url: str) -> str:
    """Tạo chuỗi băm hex 16 ký tự duy nhất từ URL đã được chuẩn hóa (SHA-256).
    
    Args:
        url: Chuỗi URL.
        
    Returns:
        str: 16 ký tự đầu của chuỗi băm SHA-256.
    """
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16]


def save_artifacts(
    html: str,
    source_name: str,
    url: str,
    final_url: str | None,
    fetched_at: datetime,
    article: dict[str, object],
    http_status: int | None = None,
    crawl_status: str = "SUCCESS",
    error: str | None = None,
    discovery_method: str = "direct",
    discovery_metadata: dict[str, object] | None = None,
    save_local: bool = False,
) -> dict[str, object]:
    """Tạo đối tượng metadata bài viết đã bóc tách. Chỉ lưu file local nếu save_local=True (mặc định: False)."""
    raw_title = article.get("title") or article.get("title_raw")
    raw_content = article.get("content") or article.get("content_raw")

    metadata = {
        "source": source_name,
        "canonical_article_id": article.get("canonical_article_id"),
        "external_url": final_url or url,
        "title_raw": clean_text(raw_title if isinstance(raw_title, str) else None),
        "content_raw": clean_text(raw_content if isinstance(raw_content, str) else None),
        "author": clean_text(str(article["author"])) if article.get("author") else None,
        "published_at": article.get("published_at"),
        "collected_at": fetched_at.isoformat(),
        "crawl_status": crawl_status,
        "url": url,
    }

    if save_local:
        try:
            date_path = fetched_at.astimezone().strftime("%Y/%m/%d")
            crawl_id = f"{url_hash(url)}_{fetched_at.strftime('%H%M%S_%f')}"
            raw_path = OUTPUT_ROOT / "raw" / source_name / date_path / f"{crawl_id}.html.gz"
            metadata_path = OUTPUT_ROOT / "metadata" / source_name / date_path / f"{crawl_id}.json"

            raw_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)

            if html and html.strip():
                with gzip.open(raw_path, "wt", encoding="utf-8") as file:
                    file.write(html)

            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as err:
            print(f"   ⚠️ Cảnh báo save_local: Không thể ghi file local ({err}) - Tiếp tục luồng ghi DB.")

    return metadata


def find_existing_artifact(url: str, source_name: str | None = None) -> dict[str, object] | None:
    """Kiểm tra bài viết đã từng tồn tại trong Database hay chưa (không kiểm tra local file)."""
    try:
        from database.operations import check_url_exists
        if check_url_exists(url):
            return {"url": url, "crawl_status": "SUCCESS", "skipped": True}
    except Exception:
        pass
    return None

