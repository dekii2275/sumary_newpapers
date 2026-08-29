"""Bộ kiểm thử đơn vị (Unit Tests) cho toàn bộ động cơ Crawler hướng Cấu hình."""

import sys
from pathlib import Path

# Thêm thư mục scripts vào sys.path để import package crawler
sys.path.insert(0, str(Path(__file__).resolve().parent))

import unittest
from datetime import datetime, timezone
from crawler.config_loader import load_all_configs, SourceConfig
from crawler.registry import registry
from crawler.parsers.generic_parser import GenericParser
from crawler.fetchers.http_fetcher import HttpFetcher
from crawler.fetchers.selenium_fetcher import SeleniumFetcher
from crawler.utils import save_artifacts

# Dữ liệu HTML giả lập cho trang VnExpress
MOCK_VNEXPRESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta property="article:published_time" content="2026-08-28T08:30:00+07:00">
    <meta property="og:image" content="https://vcdn1-vnexpress.vnecdn.net/example.jpg">
</head>
<body>
    <h1 class="title-detail">Tiêu đề bài viết công nghệ AI</h1>
    <span class="author_mail">Nguyễn Văn A</span>
    <article class="fck_detail">
        <p class="Normal">Đoạn văn mở đầu về trí tuệ nhân tạo.</p>
        <div class="box-common-category">Bỏ qua box rác này</div>
        <p class="Normal">Đoạn văn thứ hai phân tích chi tiết mô hình học sâu.</p>
    </article>
</body>
</html>
"""

# Dữ liệu HTML giả lập cho trang CafeF
MOCK_CAFEF_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="CafeF - Báo cáo thị trường chứng khoán">
    <meta property="og:image" content="https://cafefcdn.com/thumb.jpg">
</head>
<body>
    <h1 class="title">Báo cáo thị trường chứng khoán công nghệ</h1>
    <span class="author">Ban Biên Tập</span>
    <span class="date-time">28/08/2026 14:00</span>
    <div class="detail-content">
        <p>Cổ phiếu công nghệ tăng trưởng mạnh mẽ trong quý 3.</p>
        <p>Các quỹ đầu tư lớn tiếp tục đổ vốn vào startup AI.</p>
        <div class="link-content-footer">Quảng cáo liên quan</div>
    </div>
</body>
</html>
"""

# Dữ liệu HTML giả lập chứa thẻ Schema.org JSON-LD
MOCK_JSONLD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": "Tiêu đề từ JSON-LD Schema",
        "datePublished": "2026-08-29T10:00:00Z",
        "image": "https://example.com/jsonld-thumb.jpg",
        "author": {
            "@type": "Person",
            "name": "Chuyên gia Dữ liệu"
        }
    }
    </script>
</head>
<body>
    <article>
        <p>Nội dung bài viết chuẩn Schema.org được bóc tách hoàn hảo.</p>
        <p>Dữ liệu metadata được tự động lấy từ thẻ JSON-LD.</p>
    </article>
</body>
</html>
"""


class TestCrawlerEngine(unittest.TestCase):
    """Lớp kiểm thử các chức năng chính của Crawler Engine."""

    def test_01_load_configs(self):
        """Kiểm tra việc quét và nạp các file YAML cấu hình nguồn."""
        configs = load_all_configs()
        self.assertIn("vnexpress", configs)
        self.assertIn("cafef", configs)
        self.assertIn("techcrunch", configs)
        self.assertEqual(configs["vnexpress"].source_id, 1)
        self.assertEqual(configs["cafef"].source_id, 2)
        self.assertEqual(configs["techcrunch"].source_id, 3)

    def test_02_registry_domain_matching(self):
        """Kiểm tra tính năng tự động nhận diện nguồn dựa trên tên miền URL."""
        vnexpress_cfg = registry.get_config_by_url("https://vnexpress.net/khoa-hoc/bai-viet-1.html")
        self.assertIsNotNone(vnexpress_cfg)
        self.assertEqual(vnexpress_cfg.source_name, "vnexpress")

        cafef_cfg = registry.get_config_by_url("https://cafef.vn/tai-chinh.chn")
        self.assertIsNotNone(cafef_cfg)
        self.assertEqual(cafef_cfg.source_name, "cafef")

    def test_03_create_fetcher_purely_from_config(self):
        """Kiểm tra khởi tạo Fetcher dựa 100% vào config YAML (không hardcode thủ công)."""
        vnexpress_cfg = registry.get_config_by_name("vnexpress")
        vnexpress_fetcher = registry.create_fetcher(vnexpress_cfg)
        self.assertIsInstance(vnexpress_fetcher, HttpFetcher)

        cafef_cfg = registry.get_config_by_name("cafef")
        cafef_fetcher = registry.create_fetcher(cafef_cfg)
        self.assertIsInstance(cafef_fetcher, HttpFetcher)


    def test_04_generic_parser_vnexpress(self):
        """Kiểm tra GenericParser trích xuất đúng nội dung bài viết VnExpress."""
        cfg = registry.get_config_by_name("vnexpress")
        parser = GenericParser(cfg)
        result = parser.parse(MOCK_VNEXPRESS_HTML)

        self.assertEqual(result["title"], "Tiêu đề bài viết công nghệ AI")
        self.assertEqual(result["author"], "Nguyễn Văn A")
        self.assertEqual(result["published_at"], "2026-08-28T08:30:00+07:00")
        self.assertEqual(result["thumbnail_url"], "https://vcdn1-vnexpress.vnecdn.net/example.jpg")
        self.assertIn("Đoạn văn mở đầu về trí tuệ nhân tạo.", result["content"])
        self.assertNotIn("Bỏ qua box rác này", result["content"])

    def test_05_generic_parser_cafef(self):
        """Kiểm tra GenericParser trích xuất đúng nội dung bài viết CafeF."""
        cfg = registry.get_config_by_name("cafef")
        parser = GenericParser(cfg)
        result = parser.parse(MOCK_CAFEF_HTML)

        self.assertEqual(result["title"], "Báo cáo thị trường chứng khoán công nghệ")
        self.assertEqual(result["author"], "Ban Biên Tập")
        self.assertEqual(result["published_at"], "28/08/2026 14:00")
        self.assertEqual(result["thumbnail_url"], "https://cafefcdn.com/thumb.jpg")
        self.assertIn("Cổ phiếu công nghệ tăng trưởng mạnh mẽ trong quý 3.", result["content"])

    def test_06_generic_parser_jsonld_fallback(self):
        """Kiểm tra tầng dự phòng trích xuất metadata từ Schema.org JSON-LD."""
        cfg = SourceConfig(
            source_id=99,
            source_name="jsonld_source",
            domains=["example.com"]
        )
        parser = GenericParser(cfg)
        result = parser.parse(MOCK_JSONLD_HTML)

        self.assertEqual(result["title"], "Tiêu đề từ JSON-LD Schema")
        self.assertEqual(result["author"], "Chuyên gia Dữ liệu")
        self.assertEqual(result["published_at"], "2026-08-29T10:00:00Z")
        self.assertEqual(result["thumbnail_url"], "https://example.com/jsonld-thumb.jpg")
        self.assertIn("Nội dung bài viết chuẩn Schema.org được bóc tách hoàn hảo.", result["content"])

    def test_07_save_artifacts_json_structure(self):
        """Kiểm tra cấu trúc file JSON metadata đầu ra lưu trong crawl_data/."""
        article = {
            "title": "Tiêu đề test",
            "author": "Tác giả test",
            "published_at": "2026-08-29T12:00:00Z",
            "content": "Nội dung bài viết test",
            "thumbnail_url": "https://example.com/thumb.jpg",
        }
        metadata = save_artifacts(
            html="<html>test</html>",
            source_name="test_source",
            url="https://test.com/article-1",
            final_url="https://test.com/article-1",
            fetched_at=datetime.now(timezone.utc),
            article=article,
            http_status=200,
            crawl_status="SUCCESS",
            error=None,
        )

        expected_keys = {
            "source",
            "url",
            "final_url",
            "title",
            "author",
            "published_at",
            "content",
            "thumbnail_url",
            "raw_html_path",
            "http_status",
            "crawl_status",
            "fetched_at",
            "error",
        }
        self.assertEqual(set(metadata.keys()), expected_keys)
    def test_08_deduplication_find_existing(self):
        """Kiểm tra cơ chế tìm kiếm và tái sử dụng bản ghi đã cào trước đó (tránh cào trùng)."""
        from crawler.utils import find_existing_artifact
        
        # URL đã cào ở test trước
        url = "https://test.com/article-1"
        existing = find_existing_artifact(url, "test_source")
        self.assertIsNotNone(existing)
        self.assertEqual(existing["title"], "Tiêu đề test")


if __name__ == "__main__":
    unittest.main()

