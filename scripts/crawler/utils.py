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
    """Chuẩn hóa chuỗi văn bản: thu gọn khoảng trắng thừa và cắt bỏ khoảng trắng ở 2 đầu.
    
    Args:
        value: Chuỗi văn bản thô hoặc None.
        
    Returns:
        str | None: Chuỗi văn bản sạch hoặc None nếu chuỗi rỗng.
    """
    if not value:
        return None
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
    article: dict[str, str | None],
    http_status: int | None = None,
    crawl_status: str = "SUCCESS",
    error: str | None = None,
) -> dict[str, object]:
    """Nén lưu mã nguồn HTML thô dạng Gzip (.html.gz) và lưu metadata JSON vào thư mục crawl_data/.
    
    Cấu trúc thư mục tạo ra:
    - crawl_data/raw/<source_name>/<YYYY>/<MM>/<DD>/<crawl_id>.html.gz
    - crawl_data/metadata/<source_name>/<YYYY>/<MM>/<DD>/<crawl_id>.json
    
    Args:
        html: Nội dung HTML thô của trang.
        source_name: Tên định danh nguồn báo.
        url: URL bài viết ban đầu.
        final_url: URL cuối cùng sau khi chuyển hướng.
        fetched_at: Thời điểm tải trang.
        article: Từ điển chứa các trường metadata đã bóc tách (title, author, content, published_at, thumbnail_url).
        http_status: Mã phản hồi HTTP (nếu có).
        crawl_status: Trạng thái cào ('SUCCESS', 'CONTENT_NOT_FOUND', 'EMPTY_HTML', 'TIMEOUT', 'BLOCKED', 'ERROR').
        error: Thông báo lỗi (nếu có).
        
    Returns:
        dict[str, object]: Dữ liệu metadata hoàn chỉnh đã được lưu trữ.
    """
    date_path = fetched_at.astimezone().strftime("%Y/%m/%d")
    crawl_id = f"{url_hash(url)}_{fetched_at.strftime('%H%M%S_%f')}"
    raw_path = OUTPUT_ROOT / "raw" / source_name / date_path / f"{crawl_id}.html.gz"
    metadata_path = (
        OUTPUT_ROOT / "metadata" / source_name / date_path / f"{crawl_id}.json"
    )

    # Đảm bảo các thư mục cha tồn tại
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    raw_html_path = None
    if html and html.strip():
        # Ghi nén file HTML thô (.html.gz)
        with gzip.open(raw_path, "wt", encoding="utf-8") as file:
            file.write(html)
        raw_html_path = raw_path.relative_to(PROJECT_ROOT).as_posix()

    # Tạo bản ghi metadata theo chuẩn định dạng JSON
    metadata = {
        "source": source_name,
        "url": url,
        "final_url": final_url or url,
        "title": article.get("title"),
        "author": article.get("author"),
        "published_at": article.get("published_at"),
        "content": article.get("content"),
        "thumbnail_url": article.get("thumbnail_url"),
        "raw_html_path": raw_html_path,
        "http_status": http_status,
        "crawl_status": crawl_status,
        "fetched_at": fetched_at.isoformat(),
        "error": error,
    }

    # Ghi file metadata JSON
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    return metadata


def find_existing_artifact(url: str, source_name: str | None = None) -> dict[str, object] | None:
    """Tìm kiếm xem bài viết với url_hash tương ứng đã từng được cào và lưu trữ hay chưa.
    
    Args:
        url: URL bài viết cần kiểm tra.
        source_name: Tên nguồn cào (nếu có để thu hẹp phạm vi tìm kiếm).
        
    Returns:
        dict[str, object] | None: Nội dung JSON metadata đã cào trước đó hoặc None nếu chưa cào.
    """
    key = url_hash(url)
    search_dir = OUTPUT_ROOT / "metadata"
    if source_name:
        specific_dir = search_dir / source_name
        if specific_dir.exists():
            search_dir = specific_dir

    if not search_dir.exists():
        return None

    # Tìm các file metadata có chứa mã url_hash
    matches = list(search_dir.glob(f"**/*{key}*.json"))
    if matches:
        # Lấy file mới nhất nếu có nhiều phiên bản
        latest_file = max(matches, key=lambda f: f.stat().st_mtime)
        try:
            return json.loads(latest_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    return None

