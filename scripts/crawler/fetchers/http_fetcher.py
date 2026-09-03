"""Module công cụ tải trang siêu nhẹ sử dụng HTTP Requests (requests / urllib)."""

from .base import BaseFetcher

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"



class HttpFetcher(BaseFetcher):
    """Công cụ tải trang web gọn nhẹ qua giao thức HTTP tiêu chuẩn.
    
    Tích hợp HTTPAdapter với cơ chế Retry tự động (Exponential Backoff) và hỗ trợ
    theo dõi mã phản hồi HTTP cũng như URL chuyển hướng (Canonical Redirect).
    """

    def __init__(self, timeout: int = 20) -> None:
        """Khởi tạo HttpFetcher với thời gian timeout chỉ định (giây)."""
        self.timeout = timeout
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests
            from urllib3.util import Retry
            from requests.adapters import HTTPAdapter

            session = requests.Session()
            retries = Retry(
                total=3,
                backoff_factor=1.5,
                status_forcelist=[500, 502, 503, 504],
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retries)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self._session = session
        return self._session

    def fetch(self, url: str) -> dict[str, object]:
        """Tải mã nguồn HTML thô bằng requests với Retry Policy.
        
        Args:
            url: Đường dẫn URL bài viết.
            
        Returns:
            dict[str, object]: Từ điển chứa 'final_url', 'html', 'http_status'.
        """
        try:
            session = self._get_session()
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
            resp = session.get(url, headers=headers, timeout=self.timeout)
            resp.encoding = resp.apparent_encoding or "utf-8"
            return {
                "final_url": resp.url,
                "html": resp.text,
                "http_status": resp.status_code,
            }
        except Exception as exc:
            return {
                "final_url": url,
                "html": "",
                "http_status": None,
                "error": str(exc),
            }

    def close(self) -> None:
        """Đóng session khi hoàn tất."""
        if self._session is not None:
            self._session.close()
            self._session = None

