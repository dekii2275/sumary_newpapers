"""Module định nghĩa lớp cơ sở trừu tượng (Base Interface) cho tất cả các công cụ tải trang web (Fetchers)."""

from abc import ABC, abstractmethod


class BaseFetcher(ABC):
    """Lớp trừu tượng định nghĩa giao diện chung cho các fetcher tải nội dung web."""

    @abstractmethod
    def fetch(self, url: str) -> dict[str, str | None]:
        """Tải nội dung trang web từ URL và trả về từ điển chứa URL chuyển hướng cuối cùng cùng mã nguồn HTML.
        
        Args:
            url: Đường dẫn URL của trang web cần tải.
            
        Returns:
            dict[str, str | None]: Từ điển chứa:
            - 'final_url': Đường dẫn URL cuối cùng sau khi chuyển hướng (redirect).
            - 'html': Nội dung mã nguồn HTML thô của trang web.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Đóng phiên làm việc, giải phóng tài nguyên trình duyệt hoặc các kết nối mạng."""
        pass

