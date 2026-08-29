"""Module công cụ tải trang siêu nhẹ sử dụng HTTP Requests (requests / urllib)."""

from .base import BaseFetcher

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class HttpFetcher(BaseFetcher):
    """Công cụ tải trang web gọn nhẹ qua giao thức HTTP tiêu chuẩn.
    
    Rất lý tưởng cho các trang báo có nội dung tĩnh (Server-Side Rendered như VnExpress, CafeF, TechCrunch)
    giúp tăng tốc độ cào gấp 5-10 lần và tiết kiệm RAM so với việc mở trình duyệt Selenium.
    """

    def __init__(self, timeout: int = 20) -> None:
        """Khởi tạo HttpFetcher với thời gian timeout chỉ định (giây)."""
        self.timeout = timeout

    def fetch(self, url: str) -> dict[str, str | None]:
        """Tải mã nguồn HTML thô bằng requests hoặc urllib.
        
        Args:
            url: Đường dẫn URL bài viết.
            
        Returns:
            dict[str, str | None]: Từ điển chứa 'final_url' và 'html'.
        """
        try:
            import requests
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            resp.encoding = resp.apparent_encoding or "utf-8"
            return {
                "final_url": resp.url,
                "html": resp.text,
            }
        except ImportError:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                html = response.read().decode("utf-8", errors="replace")
                return {
                    "final_url": response.geturl(),
                    "html": html,
                }

    def close(self) -> None:
        """Không có tài nguyên tiến trình chạy nền cần đóng."""
        pass
