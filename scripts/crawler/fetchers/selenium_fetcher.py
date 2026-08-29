"""Module công cụ tải trang web động qua trình duyệt tự động Chrome Headless (Selenium)."""

from .base import BaseFetcher

PAGE_TIMEOUT_SECONDS = 20
USER_AGENT = "AI-Tech-News-Research-Crawler/0.1"


class SeleniumFetcher(BaseFetcher):
    """Công cụ tải trang sử dụng trình duyệt Chrome ẩn (Headless Chrome) qua Selenium.
    
    Phù hợp cho các trang web yêu cầu thực thi JavaScript động (như VnExpress interactive, SPA)
    hoặc cần đợi các thành phần web được render đầy đủ trước khi trích xuất DOM.
    """

    def __init__(self, timeout: int = PAGE_TIMEOUT_SECONDS) -> None:
        """Khởi tạo cấu hình SeleniumFetcher với thời gian timeout."""
        self.timeout = timeout
        self._driver = None

    def _get_driver(self):
        """Khởi tạo lười (Lazy init) phiên làm việc Chrome WebDriver khi có yêu cầu fetch đầu tiên."""
        if self._driver is None:
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
            except ImportError as e:
                raise ImportError(
                    "Thư viện Selenium chưa được cài đặt. Hãy chạy 'pip install selenium' để sử dụng SeleniumFetcher."
                ) from e

            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument(f"--user-agent={USER_AGENT}")

            self._driver = webdriver.Chrome(options=options)
            self._driver.set_page_load_timeout(self.timeout)

        return self._driver

    @property
    def driver(self):
        return self._get_driver()

    def fetch(self, url: str) -> dict[str, str | None]:
        """Điều hướng trình duyệt tới URL và đợi DOM tải hoàn tất (document.readyState == 'complete').
        
        Args:
            url: Đường dẫn URL bài viết.
            
        Returns:
            dict[str, str | None]: Từ điển chứa 'final_url' và 'html' đã render.
        """
        from selenium.webdriver.support.ui import WebDriverWait

        driver = self._get_driver()
        driver.get(url)
        WebDriverWait(driver, self.timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        return {
            "final_url": driver.current_url,
            "html": driver.page_source,
        }

    def close(self) -> None:
        """Đóng hoàn toàn tiến trình trình duyệt Chrome và giải phóng bộ nhớ RAM."""
        if self._driver is not None:
            self._driver.quit()
            self._driver = None
