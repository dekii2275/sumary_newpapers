"""Module bộ bóc tách dữ liệu vạn năng (GenericParser) dựa trên cấu hình khai báo YAML.

Hỗ trợ cơ chế bóc tách đa tầng (Cascade Extraction):
1. Tầng 1: Trích xuất metadata có cấu trúc Schema.org JSON-LD (NewsArticle, Article).
2. Tầng 2: Áp dụng tập luật CSS Selectors và trích xuất thuộc tính thẻ HTML (@attr).
3. Tầng 3: Tự động xóa các phần tử DOM rác (strip_elements) trước khi lấy nội dung văn bản.
4. Tầng 4: Dự phòng bóc tách tự động qua mô hình heuristic (Trafilatura) khi layout web bị thay đổi.
"""

from __future__ import annotations

import json
from bs4 import BeautifulSoup
from .base import BaseParser
from ..config_loader import SourceConfig
from ..utils import clean_text


class GenericParser(BaseParser):
    """Bộ bóc tách HTML đa năng, hoạt động dựa trên các quy tắc định nghĩa trong SourceConfig."""

    def __init__(self, config: SourceConfig):
        """Khởi tạo parser với cấu hình nguồn cụ thể."""
        self.config = config

    @staticmethod
    def _extract_by_selector_rule(soup: BeautifulSoup, rule: str) -> str | None:
        """Trích xuất chuỗi văn bản hoặc giá trị thuộc tính HTML theo cú pháp quy tắc.
        
        Các định dạng quy tắc hỗ trợ:
        - "h1.title-detail" -> Lấy nội dung text đã làm sạch của thẻ h1.title-detail.
        - "meta[property='og:image']@content" -> Lấy giá trị của thuộc tính 'content' trong thẻ meta.
        - "img.thumb@src" -> Lấy giá trị của thuộc tính 'src' trong thẻ img.
        """
        if "@" in rule:
            selector, attr_name = rule.split("@", 1)
            selector = selector.strip()
            attr_name = attr_name.strip()
            node = soup.select_one(selector)
            if node and node.has_attr(attr_name):
                return clean_text(node[attr_name])
            return None

        node = soup.select_one(rule.strip())
        if node:
            return clean_text(node.get_text(" ", strip=True))
        return None

    def _extract_first(self, soup: BeautifulSoup, rules: list[str]) -> str | None:
        """Duyệt danh sách các quy tắc theo thứ tự ưu tiên (fallback) cho đến khi tìm thấy giá trị hợp lệ."""
        for rule in rules:
            value = self._extract_by_selector_rule(soup, rule)
            if value:
                return value
        return None

    def _extract_jsonld(self, soup: BeautifulSoup) -> dict[str, str | None]:
        """Trích xuất thông tin bài viết từ các thẻ <script type='application/ld+json'> (Schema.org)."""
        extracted: dict[str, str | None] = {}
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string or "{}")
                # Chuẩn hóa nếu dữ liệu là mảng hoặc chứa cấu trúc @graph
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    if "@graph" in data and isinstance(data["@graph"], list):
                        items = data["@graph"]
                    else:
                        items = [data]

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    schema_type = str(item.get("@type", "")).lower()
                    if schema_type in ("newsarticle", "article", "reportagereport"):
                        if not extracted.get("title") and item.get("headline"):
                            extracted["title"] = clean_text(item["headline"])
                        if not extracted.get("published_at") and item.get("datePublished"):
                            extracted["published_at"] = clean_text(item["datePublished"])
                        if not extracted.get("thumbnail_url") and item.get("image"):
                            img = item["image"]
                            if isinstance(img, str):
                                extracted["thumbnail_url"] = clean_text(img)
                            elif isinstance(img, dict) and img.get("url"):
                                extracted["thumbnail_url"] = clean_text(img["url"])
                            elif isinstance(img, list) and len(img) > 0 and isinstance(img[0], str):
                                extracted["thumbnail_url"] = clean_text(img[0])
                        if not extracted.get("author") and item.get("author"):
                            auth = item["author"]
                            if isinstance(auth, str):
                                extracted["author"] = clean_text(auth)
                            elif isinstance(auth, dict) and auth.get("name"):
                                extracted["author"] = clean_text(auth["name"])
                            elif isinstance(auth, list) and len(auth) > 0:
                                first_auth = auth[0]
                                if isinstance(first_auth, str):
                                    extracted["author"] = clean_text(first_auth)
                                elif isinstance(first_auth, dict) and first_auth.get("name"):
                                    extracted["author"] = clean_text(first_auth["name"])
            except Exception:
                continue
        return extracted

    def parse(self, html: str) -> dict[str, str | None]:
        """Phân tích toàn bộ mã nguồn HTML bài viết dựa trên cấu hình nguồn và cơ chế trích xuất đa tầng."""
        soup = BeautifulSoup(html, "lxml")
        selectors = self.config.parser.selectors
        clean_rules = self.config.parser.clean_rules

        # 1. Tầng 1: Trích xuất metadata Schema.org JSON-LD để dự phòng (fallback)
        jsonld_data = self._extract_jsonld(soup)

        # 2. Tầng 2: Trích xuất các trường đơn giá trị qua danh sách selectors cấu hình
        title = self._extract_first(soup, selectors.title) or jsonld_data.get("title")
        author = self._extract_first(soup, selectors.author) or jsonld_data.get("author")
        published_at = (
            self._extract_first(soup, selectors.published_at)
            or jsonld_data.get("published_at")
        )
        thumbnail_url = (
            self._extract_first(soup, selectors.thumbnail_url)
            or jsonld_data.get("thumbnail_url")
        )

        # 3. Tầng 3: Xóa bỏ các thẻ rác (quảng cáo, script, liên kết ngoài) trước khi lấy đoạn văn
        for strip_sel in clean_rules.strip_elements:
            for elem in soup.select(strip_sel):
                elem.decompose()

        # 4. Trích xuất các đoạn văn bản nội dung bài viết
        paragraphs_by_selector = [
            soup.select(selector) for selector in selectors.content_paragraphs
        ]
        # Lựa chọn selector tìm thấy tập hợp đoạn văn bản nhiều nhất
        paragraphs = max(paragraphs_by_selector, key=len, default=[])
        content_parts = [
            text
            for paragraph in paragraphs
            if (text := clean_text(paragraph.get_text(" ", strip=True)))
        ]

        content = "\n\n".join(content_parts) or None

        # 5. Tầng 4: Heuristic Auto Fallback (Trafilatura) nếu không khớp CSS Selector nào
        if not content:
            try:
                import trafilatura
                extracted_text = trafilatura.extract(
                    html,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False,
                )
                if extracted_text and extracted_text.strip():
                    content = clean_text(extracted_text)
            except Exception:
                pass

        # 6. Trích xuất Canonical URL từ thẻ link
        canonical_url = None
        canonical_tag = soup.find("link", rel=lambda val: val and "canonical" in val.lower())
        if canonical_tag and canonical_tag.has_attr("href"):
            canonical_url = clean_text(canonical_tag["href"])

        # 7. Đánh giá chất lượng dữ liệu (Data Quality Flags)
        quality_flags: list[str] = []
        if not title:
            quality_flags.append("missing_title")
        if not author:
            quality_flags.append("missing_author")
        if not published_at:
            quality_flags.append("missing_published_at")
        if not content:
            quality_flags.append("missing_content")
        elif len(content) < 150:
            quality_flags.append("short_content")

        return {
            "title": title,
            "author": author,
            "published_at": published_at,
            "content": content,
            "thumbnail_url": thumbnail_url,
            "canonical_url": canonical_url,
            "quality_flags": quality_flags,
        }



