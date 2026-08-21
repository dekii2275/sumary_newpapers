# Step 1 — Xây dựng công cụ cào dữ liệu bài báo bằng Selenium + BeautifulSoup

## 1. Mục tiêu

Step đầu tiên của hệ thống là xây dựng một công cụ có khả năng **thu thập dữ liệu bài báo từ website tin tức**, ví dụ như `https://vnexpress.net/`.

Trong giai đoạn này, mục tiêu chưa phải xử lý AI, tóm tắt hay phân loại nội dung. Công cụ chỉ cần thực hiện tốt các nhiệm vụ:

1. Nhận một URL bài báo.
2. Truy cập trang bằng Selenium.
3. Lấy HTML sau khi trang đã tải.
4. Parse HTML bằng BeautifulSoup.
5. Trích xuất các trường thông tin cơ bản của bài báo.
6. Lưu lại dữ liệu thô để phục vụ bước xử lý tiếp theo.

Đây là phiên bản MVP của module **Data Collection** trong pipeline tổng thể.

---

## 2. Phạm vi của Step 1

### Có thực hiện

- Crawl một bài báo từ URL cụ thể.
- Thu thập HTML của trang.
- Trích xuất một số thông tin cơ bản:
  - tiêu đề;
  - nội dung;
  - tác giả;
  - thời gian xuất bản;
  - URL gốc;
  - ảnh đại diện nếu có.
- Lưu lại HTML thô.
- Lưu metadata của lần crawl.
- Xuất dữ liệu về một format thống nhất.

### Chưa thực hiện

Các chức năng dưới đây sẽ để cho các step sau:

- Khử trùng lặp nâng cao.
- Phân loại category.
- Entity Extraction.
- Topic Linking.
- Summarization.
- Key Point Extraction.
- Impact Analysis.
- Importance Scoring.
- Embedding.
- Vector Database.
- RAG.
- Tự động sinh video.

---

# 3. Luồng xử lý

Pipeline đơn giản:

```text
Article URL
    │
    ▼
Selenium
    │
    │ load website
    │ execute JavaScript
    ▼
Rendered HTML
    │
    ▼
BeautifulSoup
    │
    ├── Title
    ├── Author
    ├── Published time
    ├── Content
    └── Image
    │
    ▼
Raw Article Object
    │
    ├── metadata → JSON/PostgreSQL
    │
    └── raw HTML → local storage / MinIO
```

Trong phiên bản đầu tiên, có thể lưu toàn bộ dữ liệu ra thư mục local để kiểm thử.

Khi pipeline ổn định, chuyển metadata sang PostgreSQL và raw HTML sang MinIO/S3.

---

# 4. Công nghệ sử dụng

## Selenium

Selenium chịu trách nhiệm mở website bằng browser thật.

Vai trò:

- Load HTML.
- Chạy JavaScript.
- Chờ DOM render.
- Xử lý các website không trả đủ nội dung khi gọi HTTP request thông thường.

Cài đặt:

```bash
pip install selenium
```

---

## BeautifulSoup

BeautifulSoup dùng để parse HTML mà Selenium thu được.

Vai trò:

- Tìm các HTML element.
- Lấy title.
- Lấy author.
- Lấy thời gian.
- Lấy nội dung bài viết.
- Lấy ảnh.

Cài đặt:

```bash
pip install beautifulsoup4 lxml
```

---

# 5. Cấu trúc project đề xuất

```text
news-crawler/
│
├── app/
│   ├── __init__.py
│   │
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── selenium_fetcher.py
│   │   └── article_parser.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── raw_article.py
│   │
│   └── storage/
│       ├── __init__.py
│       └── local_storage.py
│
├── data/
│   ├── raw/
│   └── metadata/
│
├── scripts/
│   └── crawl_article.py
│
├── requirements.txt
│
└── README.md
```

---

# 6. Data model cho bài báo thô

Ở bước đầu tiên, dữ liệu crawler trả về nên có một format thống nhất.

Ví dụ:

```json
{
  "source": "vnexpress",
  "url": "https://vnexpress.net/example.html",
  "final_url": "https://vnexpress.net/example.html",
  "title": "Tiêu đề bài báo",
  "author": "Tên tác giả",
  "published_at": "2026-08-21T10:30:00+07:00",
  "content": "Nội dung bài báo...",
  "thumbnail_url": "https://...",
  "raw_html_path": "data/raw/abc123.html",
  "http_status": 200,
  "crawl_status": "SUCCESS",
  "fetched_at": "2026-08-21T20:00:00+07:00"
}
```

Ở giai đoạn này:

- `content` có thể chưa hoàn toàn sạch.
- `published_at` có thể chưa parse được ở một số website.
- Một số field có thể `null`.

Điều quan trọng là crawler phải trả về cùng một cấu trúc.

---

# 7. Raw Article model

Có thể sử dụng Python `dataclass`.

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RawArticle:
    source: str

    url: str
    final_url: Optional[str]

    title: Optional[str]
    author: Optional[str]
    published_at: Optional[str]

    content: Optional[str]

    thumbnail_url: Optional[str]

    raw_html_path: Optional[str]

    http_status: Optional[int]

    crawl_status: str

    fetched_at: datetime
```

Sau này có thể thay bằng Pydantic model nếu tích hợp FastAPI.

---

# 8. Selenium Fetcher

Tạo file:

```text
app/crawler/selenium_fetcher.py
```

Ví dụ:

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


class SeleniumFetcher:

    def __init__(self):
        options = Options()

        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Chrome(options=options)

    def fetch(self, url: str) -> dict:

        self.driver.get(url)

        WebDriverWait(
            self.driver,
            timeout=15
        ).until(
            lambda driver: driver.execute_script(
                "return document.readyState"
            ) == "complete"
        )

        return {
            "url": url,
            "final_url": self.driver.current_url,
            "html": self.driver.page_source
        }

    def close(self):
        self.driver.quit()
```

Flow:

```text
URL
 │
 ▼
driver.get()
 │
 ▼
wait page ready
 │
 ▼
driver.page_source
 │
 ▼
HTML
```

---

# 9. Parse bài báo bằng BeautifulSoup

Tạo file:

```text
app/crawler/article_parser.py
```

Ví dụ:

```python
from bs4 import BeautifulSoup


class ArticleParser:

    def parse(self, html: str) -> dict:

        soup = BeautifulSoup(
            html,
            "lxml"
        )

        title = self.extract_title(soup)

        author = self.extract_author(soup)

        published_at = self.extract_published_at(soup)

        content = self.extract_content(soup)

        thumbnail = self.extract_thumbnail(soup)

        return {
            "title": title,
            "author": author,
            "published_at": published_at,
            "content": content,
            "thumbnail_url": thumbnail
        }

    def extract_title(self, soup):

        title = soup.find("h1")

        if title:
            return title.get_text(
                " ",
                strip=True
            )

        return None

    def extract_author(self, soup):

        author = soup.select_one(
            ".author"
        )

        if author:
            return author.get_text(
                " ",
                strip=True
            )

        return None

    def extract_published_at(self, soup):

        time = soup.find("time")

        if time:
            return time.get(
                "datetime"
            ) or time.get_text(
                " ",
                strip=True
            )

        return None

    def extract_content(self, soup):

        paragraphs = soup.select(
            "article p"
        )

        if not paragraphs:
            paragraphs = soup.select(
                ".fck_detail p"
            )

        content = []

        for paragraph in paragraphs:

            text = paragraph.get_text(
                " ",
                strip=True
            )

            if text:
                content.append(text)

        return "\n\n".join(content)

    def extract_thumbnail(self, soup):

        image = soup.find(
            "meta",
            property="og:image"
        )

        if image:
            return image.get(
                "content"
            )

        return None
```

> Lưu ý: CSS selector của từng website có thể thay đổi theo thời gian. Các selector ở trên chỉ nên được xem là điểm khởi đầu. Khi crawl VnExpress thực tế, cần inspect DOM của trang và điều chỉnh parser phù hợp.

---

# 10. Không nên gộp Selenium và BeautifulSoup vào một class

Nên tách:

```text
SeleniumFetcher
      │
      │ HTML
      ▼
ArticleParser
```

thay vì:

```text
VnExpressCrawler
 ├── Selenium
 ├── BeautifulSoup
 ├── save database
 ├── normalize
 ├── deduplicate
 └── ...
```

Lý do là sau này có thể thay Selenium bằng HTTP client mà không phải sửa parser:

```text
SeleniumFetcher ──┐
                  │
HttpFetcher ──────┼──► ArticleParser
                  │
PlaywrightFetcher ┘
```

---

# 11. Lưu raw HTML

HTML vừa crawl được nên giữ lại.

Ví dụ:

```text
data/
└── raw/
    └── vnexpress/
        └── 2026/
            └── 08/
                └── 21/
                    ├── article_001.html
                    ├── article_002.html
                    └── article_003.html
```

Function đơn giản:

```python
from pathlib import Path


def save_raw_html(
    html: str,
    path: str
):

    output_path = Path(path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        html,
        encoding="utf-8"
    )
```

Trong production có thể chuyển phần này sang MinIO.

---

# 12. Có thể nén HTML

HTML có khả năng nén rất tốt.

Có thể lưu:

```text
.html.gz
```

thay vì:

```text
.html
```

Ví dụ:

```python
import gzip


def save_raw_html_gzip(
    html: str,
    path: str
):

    with gzip.open(
        path,
        "wt",
        encoding="utf-8"
    ) as file:

        file.write(html)
```

Ví dụ file:

```text
data/raw/vnexpress/2026/08/21/article_001.html.gz
```

Khi chuyển sang MinIO/S3, có thể giữ nguyên format này.

---

# 13. Script chạy crawler

Tạo:

```text
scripts/crawl_article.py
```

Ví dụ:

```python
from datetime import datetime, timezone

from app.crawler.selenium_fetcher import SeleniumFetcher
from app.crawler.article_parser import ArticleParser


def crawl_article(url: str):

    fetcher = SeleniumFetcher()

    parser = ArticleParser()

    try:

        response = fetcher.fetch(url)

        article = parser.parse(
            response["html"]
        )

        result = {
            "source": "vnexpress",

            "url": url,

            "final_url":
                response["final_url"],

            **article,

            "crawl_status":
                "SUCCESS",

            "fetched_at":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }

        return result

    except Exception as error:

        return {
            "source": "vnexpress",

            "url": url,

            "crawl_status":
                "FAILED",

            "error":
                str(error),

            "fetched_at":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }

    finally:

        fetcher.close()
```

---

# 14. Chạy thử

Ví dụ:

```python
url = "https://vnexpress.net/..."

article = crawl_article(url)

print(article)
```

Kết quả mong muốn:

```json
{
  "source": "vnexpress",
  "url": "https://vnexpress.net/...",
  "final_url": "https://vnexpress.net/...",
  "title": "...",
  "author": "...",
  "published_at": "...",
  "content": "...",
  "thumbnail_url": "...",
  "crawl_status": "SUCCESS",
  "fetched_at": "..."
}
```

---

# 15. Crawl nhiều URL

Sau khi crawl một bài thành công, có thể mở rộng:

```python
urls = [
    "...",
    "...",
    "..."
]

for url in urls:

    article = crawl_article(url)

    print(
        article["crawl_status"],
        article.get("title")
    )
```

Chưa nên chạy hàng trăm browser instance song song.

Với Selenium MVP, có thể dùng một browser và lần lượt load nhiều URL.

---

# 16. Discovery URL

Sau khi crawler một URL hoạt động ổn, bước tiếp theo là tự động lấy danh sách bài viết.

Ví dụ:

```text
Trang category
https://vnexpress.net/cong-nghe
        │
        ▼
Selenium / HTTP
        │
        ▼
BeautifulSoup
        │
        ▼
extract <a href="...">
        │
        ▼
Article URLs
        │
        ▼
crawl_article(url)
```

Có thể xây function:

```python
def discover_article_urls(
    category_url
):
    ...
```

Output:

```python
[
    "https://vnexpress.net/article-a.html",
    "https://vnexpress.net/article-b.html",
    "https://vnexpress.net/article-c.html"
]
```

---

# 17. Chuẩn hóa URL cơ bản

Trước khi crawl nên loại các tracking parameter như:

```text
utm_source
utm_medium
utm_campaign
fbclid
gclid
```

Ví dụ:

```text
https://example.com/article?id=10&utm_source=facebook
```

thành:

```text
https://example.com/article?id=10
```

Điều này giúp giảm crawl trùng.

---

# 18. Hash URL

Có thể tạo hash để nhận diện nhanh:

```python
import hashlib


def hash_url(url: str):

    return hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()
```

Hash này có thể dùng:

- làm tên file HTML;
- kiểm tra URL đã crawl;
- làm key cache.

Ví dụ:

```text
data/raw/vnexpress/
    7fc7812f....html.gz
```

---

# 19. Lưu metadata dạng JSON trong phiên bản MVP

Trước khi tích hợp PostgreSQL, có thể lưu metadata thành file `.json`.

Ví dụ:

```text
data/
├── raw/
│   └── vnexpress/
│       └── xxx.html.gz
│
└── metadata/
    └── vnexpress/
        └── xxx.json
```

File metadata:

```json
{
  "source": "vnexpress",
  "url": "...",
  "title": "...",
  "author": "...",
  "published_at": "...",
  "raw_html_path": "...",
  "crawl_status": "SUCCESS"
}
```

Cách này giúp debug rất nhanh trong giai đoạn thử nghiệm.

---

# 20. Khi nào chuyển sang PostgreSQL?

Sau khi crawler chạy ổn với khoảng:

```text
20–50 bài
```

thì chuyển metadata vào PostgreSQL.

Có thể ánh xạ sang:

```text
sources
     │
     ▼
raw_documents
     │
     ▼
articles
```

Trong đó:

### raw_documents

Lưu thông tin của lần crawl:

```text
id
source_id
url
final_url
raw_object_key
http_status
status
fetched_at
```

### articles

Lưu bài sau khi đã extract và normalize:

```text
id
source_id
title
content
author
published_at
language
original_url
```

Không nên đưa ngay:

```text
summary
key_points
why_it_matters
impact_score
importance_score
```

vào Step 1 vì các field này thuộc AI processing.

---

# 21. Error handling

Crawler phải chấp nhận việc một số bài crawl thất bại.

Các trạng thái cơ bản:

```text
SUCCESS

TIMEOUT

PAGE_NOT_FOUND

BLOCKED

EMPTY_HTML

PARSE_FAILED

CONTENT_NOT_FOUND

UNKNOWN_ERROR
```

Ví dụ:

```python
try:
    ...

except TimeoutException:

    status = "TIMEOUT"

except Exception:

    status = "UNKNOWN_ERROR"
```

Không nên để một URL lỗi làm dừng toàn bộ crawler.

---

# 22. Logging

Mỗi lần crawl nên log:

```text
timestamp

source

url

crawl_status

duration

html_size

content_length

error
```

Ví dụ:

```text
2026-08-21 20:10:03
SOURCE=vnexpress
STATUS=SUCCESS
CONTENT_LENGTH=4321
DURATION=2.18s
```

Các log này sẽ rất hữu ích khi crawler chạy định kỳ.

---

# 23. Rate limiting

Không nên gửi request liên tục với tốc độ quá cao.

MVP có thể đơn giản:

```python
import time


for url in urls:

    crawl_article(url)

    time.sleep(2)
```

Sau này có thể xây rate limiter theo từng source.

Ví dụ:

```text
vnexpress
    1 request / 2 seconds

source_B
    1 request / second
```

Crawler cũng cần tuân thủ điều khoản sử dụng, robots.txt và giới hạn truy cập phù hợp của từng website.

---

# 24. Selenium configuration

Có thể dùng browser headless:

```python
options.add_argument(
    "--headless=new"
)
```

Một số option thường dùng:

```python
options.add_argument(
    "--disable-gpu"
)

options.add_argument(
    "--no-sandbox"
)

options.add_argument(
    "--disable-dev-shm-usage"
)

options.add_argument(
    "--window-size=1920,1080"
)
```

Trong production có thể chạy Selenium/Chrome trong Docker.

---

# 25. User-Agent

Có thể cấu hình User-Agent rõ ràng thay vì cố tình giả mạo người dùng.

Ví dụ:

```python
options.add_argument(
    "--user-agent=NewsResearchCrawler/1.0"
)
```

Nếu website cung cấp API hoặc RSS chính thức thì nên ưu tiên các interface đó thay vì browser scraping.

---

# 26. Test cần thực hiện

## Test 1 — Fetch HTML

Input:

```text
URL bài VnExpress
```

Expected:

```text
HTML != empty
```

---

## Test 2 — Extract title

Expected:

```text
title != None
```

---

## Test 3 — Extract content

Expected:

```text
len(content) > 500
```

Con số này chỉ là heuristic ban đầu, không phải quy tắc tuyệt đối.

---

## Test 4 — Save HTML

Expected:

```text
file exists
```

---

## Test 5 — Invalid URL

Input:

```text
URL không tồn tại
```

Expected:

```text
crawler không crash
crawl_status != SUCCESS
```

---

# 27. Bộ dữ liệu kiểm thử

Ban đầu nên chọn khoảng:

```text
10 bài
```

thuộc nhiều loại:

```text
Tin công nghệ

AI

Startup

Khoa học

Bài có nhiều ảnh

Bài ngắn

Bài dài
```

Sau đó tăng lên:

```text
50 bài
```

để đánh giá độ ổn định.

---

# 28. Metrics cho MVP

Một số metric nên theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Crawl success rate | Tỷ lệ URL load thành công |
| Parse success rate | Tỷ lệ lấy được bài |
| Average crawl time | Thời gian trung bình mỗi URL |
| Empty content rate | Tỷ lệ content rỗng |
| Average content length | Độ dài bài |
| Error rate | Tỷ lệ lỗi |

Ví dụ mục tiêu thử nghiệm:

```text
Crawl success > 90%

Parse success > 85%

Crawler không crash khi một URL lỗi
```

Đây là các mục tiêu kỹ thuật cho MVP và có thể điều chỉnh sau khi thử nghiệm thực tế.

---

# 29. Definition of Done

Step 1 được xem là hoàn thành khi:

- [ ] Có thể truyền một URL bài báo vào crawler.
- [ ] Selenium load được trang.
- [ ] BeautifulSoup parse được HTML.
- [ ] Lấy được title.
- [ ] Lấy được content.
- [ ] Lấy được author nếu website cung cấp.
- [ ] Lấy được published time nếu website cung cấp.
- [ ] Lấy được thumbnail nếu có.
- [ ] Lưu được raw HTML.
- [ ] Lưu được metadata.
- [ ] Có xử lý exception.
- [ ] Một bài lỗi không làm crawler dừng.
- [ ] Crawl thử thành công ít nhất 20–50 bài.
- [ ] Output tuân theo một Raw Article schema thống nhất.

---

# 30. Hướng phát triển tiếp theo

Sau khi Step 1 hoạt động ổn định, có thể phát triển theo thứ tự:

```text
Step 1
Single Article Crawler
        │
        ▼
Step 2
Article URL Discovery
        │
        ▼
Step 3
Multi-source Collectors
        │
        ▼
Step 4
Raw Storage
PostgreSQL + MinIO
        │
        ▼
Step 5
Cleaning + Normalize
        │
        ▼
Step 6
Duplicate Detection
        │
        ▼
Step 7
Canonical Article
        │
        ▼
Step 8
AI News Understanding
```

---

# 31. Kết luận

Trong Step 1, mục tiêu không phải xây một crawler phức tạp ngay lập tức.

Kiến trúc tối thiểu nên là:

```text
Selenium
    │
    ▼
HTML
    │
    ▼
BeautifulSoup
    │
    ▼
Raw Article
    │
    ├── raw HTML
    └── metadata
```

Điều quan trọng nhất là:

1. Tách **fetching** khỏi **parsing**.
2. Giữ lại **raw HTML**.
3. Chuẩn hóa output thành một **Raw Article schema**.
4. Có logging và xử lý lỗi.
5. Chỉ sau khi crawler đơn nguồn chạy ổn mới mở rộng sang multi-source, database và pipeline AI.

Đây sẽ là nền tảng cho toàn bộ hệ thống thu thập và xử lý tin tức phía sau.
