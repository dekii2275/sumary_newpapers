"""Module nạp và xác thực cấu hình nguồn cào dữ liệu từ file YAML.

Sử dụng Pydantic models để định nghĩa schema và kiểm tra tính hợp lệ của cấu hình
cho từng trang báo (CSS selectors, loại fetcher, quy tắc làm sạch dữ liệu).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field

# Đường dẫn mặc định đến thư mục chứa các file cấu hình nguồn cào
DEFAULT_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "configs" / "sources"


class SelectorConfig(BaseModel):
    """Cấu hình các bộ chọn (CSS Selectors / Thuộc tính thẻ) để bóc tách thông tin."""
    title: list[str] = Field(
        default_factory=lambda: ["h1", "meta[property='og:title']@content"],
        description="Danh sách bộ chọn tiêu đề bài viết theo thứ tự ưu tiên"
    )
    author: list[str] = Field(
        default_factory=list,
        description="Danh sách bộ chọn tên tác giả"
    )
    published_at: list[str] = Field(
        default_factory=lambda: [
            "meta[property='article:published_time']@content",
            "time[datetime]@datetime",
        ],
        description="Danh sách bộ chọn thời gian xuất bản bài viết"
    )
    thumbnail_url: list[str] = Field(
        default_factory=lambda: ["meta[property='og:image']@content"],
        description="Danh sách bộ chọn ảnh đại diện (thumbnail)"
    )
    content_paragraphs: list[str] = Field(
        default_factory=lambda: [".fck_detail p", "article p", ".content p"],
        description="Danh sách bộ chọn các đoạn văn bản nội dung bài viết"
    )


class CleanRulesConfig(BaseModel):
    """Quy tắc loại bỏ các phần tử HTML rác trước khi trích xuất văn bản."""
    strip_elements: list[str] = Field(
        default_factory=lambda: ["script", "style", ".ads", ".banner"],
        description="Danh sách các selector phần tử cần xóa bỏ khỏi DOM (quảng cáo, script, style...)"
    )


class ParserConfig(BaseModel):
    """Cấu hình bộ bóc tách nội dung."""
    type: Literal["declarative", "custom"] = "declarative"
    custom_class: str | None = None
    selectors: SelectorConfig = Field(default_factory=SelectorConfig)
    clean_rules: CleanRulesConfig = Field(default_factory=CleanRulesConfig)


class FetcherConfig(BaseModel):
    """Cấu hình công cụ tải trang web (HTTP Requests hoặc Selenium Chrome Headless)."""
    type: Literal["http", "selenium"] = "http"
    timeout: int = 20
    headers: dict[str, str] = Field(default_factory=dict)


class SourceConfig(BaseModel):
    """Cấu hình tổng thể cho một nguồn báo cụ thể."""
    source_id: int
    source_name: str
    display_name: str | None = None
    domains: list[str] = Field(default_factory=list, description="Danh sách tên miền thuộc nguồn này")
    fetcher: FetcherConfig = Field(default_factory=FetcherConfig)
    parser: ParserConfig = Field(default_factory=ParserConfig)


def load_source_config(file_path: Path | str) -> SourceConfig:
    """Đọc và xác thực nội dung của một file cấu hình YAML nguồn báo đơn lẻ.
    
    Args:
        file_path: Đường dẫn đến file .yaml cấu hình.
        
    Returns:
        SourceConfig: Đối tượng cấu hình đã được xác thực qua Pydantic.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}

    return SourceConfig(**raw_data)


def load_all_configs(configs_dir: Path | str | None = None) -> dict[str, SourceConfig]:
    """Quét và tải toàn bộ các file cấu hình nguồn (*.yaml, *.yml) trong thư mục chỉ định.
    
    Args:
        configs_dir: Thư mục chứa cấu hình (mặc định lấy DEFAULT_CONFIGS_DIR).
        
    Returns:
        dict[str, SourceConfig]: Bản đồ ánh xạ từ tên nguồn (chữ thường) sang SourceConfig tương ứng.
    """
    dir_path = Path(configs_dir) if configs_dir else DEFAULT_CONFIGS_DIR
    configs: dict[str, SourceConfig] = {}

    if not dir_path.exists():
        return configs

    # Quét tất cả file định dạng .yaml
    for file_path in dir_path.glob("*.yaml"):
        try:
            cfg = load_source_config(file_path)
            configs[cfg.source_name.lower()] = cfg
        except Exception as e:
            print(f"Cảnh báo: Không thể nạp cấu hình từ {file_path}: {e}")

    # Quét thêm các file định dạng .yml (nếu chưa được nạp)
    for file_path in dir_path.glob("*.yml"):
        if file_path.stem.lower() not in configs:
            try:
                cfg = load_source_config(file_path)
                configs[cfg.source_name.lower()] = cfg
            except Exception as e:
                print(f"Cảnh báo: Không thể nạp cấu hình từ {file_path}: {e}")

    return configs

