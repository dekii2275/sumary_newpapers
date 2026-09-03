# Hướng Dẫn Toàn Diện Hệ Thống Thu Thập Tin Tức Đa Kênh (Data Ingestion & Crawler Engine)

> **Kiến trúc Thu thập Dữ liệu Hai Giai đoạn (Two-Stage Ingestion Pipeline)** kết hợp giữa **RSS/Atom Feed XML**, **REST API JSON** và **HTML Web Crawler**. Module này đóng vai trò là tầng tiếp nhận dữ liệu đầu vào (Stage 1: Data Ingestion & Lakehouse Storage) trong toàn bộ nền tảng AI Tech News Intelligence.

---

## 📑 Mục lục
1. [Triết lý Thiết kế: Mô hình Hai Giai đoạn (Two-Stage Ingestion)](#1-triết-lý-thiết-kế-mô-hình-hai-giai-đoạn-two-stage-ingestion)
2. [Cấu trúc Thư mục & Phân loại Nguồn (RSS / API / HTML)](#2-cấu-trúc-thư-mục--phân-loại-nguồn-rss--api--html)
3. [Luồng Xử lý Dữ liệu Chi tiết (End-to-End Workflow)](#3-luồng-xử-lý-dữ-liệu-chi-tiết-end-to-end-workflow)
4. [Hướng Dẫn Giải Quyết Các Tình Huống Lỗi Thực Tế](#4-hướng-dẫn-giải-quyết-các-tình-huống-lỗi-thực-tế)
   - 4.1. [Hướng giải quyết các lỗi HTML Web Scraping](#41-hướng-giải-quyết-các-lỗi-html-web-scraping)
   - 4.2. [Hướng giải quyết các lỗi XML / RSS Feeds](#42-hướng-giải-quyết-các-lỗi-xml--rss-feeds)
   - 4.3. [Hướng giải quyết các lỗi REST API JSON](#43-hướng-giải-quyết-các-lỗi-rest-api-json)
5. [Cấu trúc Dữ liệu Đầu ra Chuẩn trong `crawl_data/`](#5-cấu-trúc-dữ-liệu-đầu-ra-chuẩn-trong-crawl_data)
6. [Hướng dẫn Vận hành Dòng lệnh (CLI Entrypoints)](#6-hướng-dẫn-vận-hành-dòng-lệnh-cli-entrypoints)
7. [Hướng dẫn Thêm Nguồn Mới (RSS, API hoặc HTML Listing)](#7-hướng-dẫn-thêm-nguồn-mới-rss-api-hoặc-html-listing)



---

## 1. Triết lý Thiết kế: Mô hình Hai Giai đoạn (Two-Stage Ingestion)

Trong kỹ thuật dữ liệu hiện đại, việc cào tin tức bằng cách mở từng trang web thủ công là kém hiệu quả và dễ bị chặn. Hệ thống này phân tách quy trình thu thập thành hai giai đoạn độc lập nhưng phối hợp chặt chẽ:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  GIAI ĐOẠN 1: DISCOVERY ENGINE (Khám phá bài viết mới)                      │
│  - RSS / Atom XML: Cực nhẹ, lấy link bài mới sau 0.2s                      │
│  - REST API JSON: Tích hợp trực tiếp các cổng API tin tức / công nghệ       │
│  - Listing Scraper: Quét trang danh mục cho website không hỗ trợ RSS/API     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  BỘ LỌC KHỬ TRÙNG LẶP (Pre-crawl Deduplication)                            │
│  - Chuẩn hóa URL (bỏ query tracking: utm, fbclid, gclid)                    │
│  - Băm SHA-256 (16 ký tự). Nếu bài đã cào -> Bỏ qua, tiết kiệm 100% tài     │
│    nguyên mạng và CPU                                                       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (Chỉ cào bài mới)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  GIAI ĐOẠN 2: FULL-TEXT EXTRACTION (Bóc tách toàn văn & Lưu trữ)            │
│  - Adaptive Fetcher: Tải HTTP siêu tốc; tự động chuyển sang Chrome Headless │
│    (Selenium) nếu web yêu cầu JavaScript rendering hoặc chặn mã 403         │
│  - Cascade Parser: CSS Selectors -> Schema.org JSON-LD -> Trafilatura       │
│  - Storage Lakehouse: Nén .html.gz và lưu metadata .json đầy đủ             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Cấu trúc Thư mục & Phân loại Nguồn (RSS / API / HTML)

Thư mục `scripts/` được tổ chức dạng module hóa cao, tách bạch rõ ràng cấu hình theo từng kênh:

```text
scripts/
├── configs/
│   └── sources/                       # CẤU HÌNH NGUỒN PHÂN LOẠI THEO KÊNH
│       ├── rss/                       # Nguồn thu thập qua RSS / Atom Feed XML
│       │   ├── vnexpress.yaml         # VnExpress (tin mới, số hóa, công nghệ)
│       │   ├── cafef.yaml             # CafeF (tin mới, thị trường chứng khoán)
│       │   └── techcrunch.yaml        # TechCrunch (toàn cầu & AI)
│       ├── api/                       # Nguồn thu thập qua REST API (JSON)
│       │   └── devto.yaml             # DEV Community REST API (chủ đề AI)
│       └── html/                      # Nguồn trang web KHÔNG có RSS/API (cào Listing)
│           └── vietnamnet.yaml        # VietnamNet chuyên mục Công nghệ
│
├── crawler/                           # GÓI ĐỘNG CƠ CÀO CHÍNH
│   ├── collectors/                    # [Stage 1: Discovery]
│   │   ├── __init__.py                # Factory khởi tạo collector theo nguồn
│   │   ├── base.py                    # Định nghĩa DiscoveredArticle & BaseCollector
│   │   ├── rss_collector.py           # Đọc RSS/Atom XML (feedparser, namespace, date parse)
│   │   ├── api_collector.py           # Gọi REST API (JSON, Rate Limiting, Pagination)
│   │   └── listing_collector.py       # Quét trang chuyên mục tìm link bài mới
│   │
│   ├── fetchers/                      # CÔNG CỤ TẢI TRANG HTML
│   │   ├── base.py                    # BaseFetcher interface
│   │   ├── http_fetcher.py            # Tải HTTP có Retry Adapter, Exponential Backoff
│   │   └── selenium_fetcher.py        # Chrome Headless cho trang JS động
│   │
│   ├── parsers/                       # BỘ BÓC TÁCH TOÀN VĂN
│   │   ├── base.py                    # BaseParser interface
│   │   └── generic_parser.py          # Bóc tách đa tầng + Trafilatura + Data Quality Flags
│   │
│   ├── config_loader.py               # Quét đệ quy rglob nạp YAML qua Pydantic Models
│   ├── registry.py                    # SourceRegistry: Ánh xạ domain & quản lý cấu hình
│   ├── pipeline.py                    # Orchestrator: Quản lý luồng cào bài viết
│   └── utils.py                       # Chuẩn hóa URL, băm SHA-256, nén Gzip, lưu JSON
│
├── collect_news.py                    # CLI Entrypoint: Điều phối thu thập tự động theo lô
├── crawl_to_db.py                     # CLI Entrypoint: Cào 1 URL bài viết đơn lẻ
├── requirements.txt                   # Danh sách thư viện phụ thuộc
└── README.md                          # Tài liệu hướng dẫn này
```

---

## 3. Luồng Xử lý Dữ liệu Chi tiết (End-to-End Workflow)

1. **Khám phá (Discovery)**:
   - `collect_news.py` kích hoạt `get_collector_for_source(config)`.
   - Nếu là nguồn `rss`: `RssCollector` tải file XML, phân giải namespace (`dc:creator`, `content:encoded`, `media:content`), bóc tách danh sách link bài viết và ngày đăng chuẩn hóa UTC.
   - Nếu là nguồn `api`: `ApiCollector` gửi request HTTP GET/POST, xử lý phân trang và ánh xạ các trường JSON sang `DiscoveredArticle`.
   - Nếu là nguồn `html`: `ListingCollector` quét trang chuyên mục, lọc lấy các thẻ `<a>` có URL bài viết hợp lệ.
2. **Khử trùng lặp (Deduplication Check)**:
   - URL được lọc bỏ query tracking (`utm_...`, `fbclid`, `gclid`).
   - Tạo mã băm SHA-256 (`url_hash`).
   - Kiểm tra trong kho lưu trữ `crawl_data/metadata/`. Nếu đã tồn tại và không bật `--force`, bài viết được bỏ qua ngay lập tức.
3. **Bóc tách toàn văn (Full-Text Crawl)**:
   - `crawl_article` sử dụng `HttpFetcher` với Retry Adapter để tải mã HTML.
   - **Adaptive Fallback**: Nếu HTML tải về bị rỗng hoặc gặp lỗi 403 Forbidden, hệ thống tự động kích hoạt `SeleniumFetcher` (Chrome Headless) để cào trang sau khi JavaScript render xong.
   - `GenericParser` bóc tách tiêu đề, tác giả, ngày đăng, nội dung, thumbnail qua 4 tầng (YAML Selectors $\rightarrow$ JSON-LD Schema.org $\rightarrow$ Trafilatura NLP).
   - Nếu bài viết thiếu trường nào, hệ thống tự động bổ sung dữ liệu đã lấy được từ RSS/API ở Stage 1 (Graceful Fallback).
4. **Đánh giá chất lượng & Lưu trữ (Lakehouse Storage)**:
   - Ghi nhận `quality_flags` (ví dụ: `missing_author`, `short_content`).
   - Ghi nén mã nguồn HTML gốc thành `.html.gz`.
   - Ghi metadata có cấu trúc thành tệp `.json`.

---

## 4. Hướng Dẫn Giải Quyết Các Tình Huống Lỗi Thực Tế

Trong kỹ thuật thu thập dữ liệu (Web Scraping & Data Ingestion), hệ thống phải giải quyết hàng loạt bài toán về độ ổn định, sự biến động của website nguồn và các cơ chế phòng vệ bot. Dưới đây là kiến trúc và giải pháp kỹ thuật cụ thể đã được triển khai:

---

### 4.1. Hướng giải quyết các lỗi HTML Web Scraping

1. **Website thay đổi cấu trúc HTML / CSS Selectors**:
   - **Vấn đề**: Các trang báo định kỳ cập nhật giao diện, đổi tên class CSS hoặc cấu trúc DOM khiến selector cũ không tìm thấy nội dung (`CONTENT_NOT_FOUND`).
   - **Hướng giải quyết**: Áp dụng cơ chế **Cascade Extraction 4 tầng**:
     - *Tầng 1 (Cấu hình ưu tiên)*: Quét danh sách CSS selectors khai báo trong file YAML theo thứ tự từ trên xuống dưới.
     - *Tầng 2 (Chuẩn Schema quốc tế)*: Nếu selectors không khớp, tự động đọc thẻ `<script type="application/ld+json">` để trích xuất dữ liệu có cấu trúc chuẩn Schema.org (`NewsArticle`, `Article`).
     - *Tầng 3 (Heuristic NLP Fallback)*: Nếu không có JSON-LD hoặc layout bị xáo trộn hoàn toàn, hệ thống tự động kích hoạt mô hình Heuristic **Trafilatura**. Thuật toán này phân tích mật độ văn bản so với thẻ HTML (Text-to-Tag ratio) để tự động nhận diện và bóc tách khối văn bản bài viết chính xác mà không cần bất kỳ class CSS nào.
     - *Tầng 4 (Metadata Fallback)*: Kế thừa tiêu đề, ngày đăng, tác giả đã khám phá được từ RSS/API ở Stage 1 nếu HTML thiếu.

2. **Trang web JavaScript Rendering (SPA / React / Next.js / Vue)**:
   - **Vấn đề**: Khi gửi HTTP Request đơn thuần, mã HTML trả về chỉ là khung sườn rỗng (ví dụ: `<div id="root"></div>`) hoặc màn hình loading, nội dung bài viết chỉ được tải qua JavaScript.
   - **Hướng giải quyết**: Cơ chế **Adaptive Hybrid Fallback**:
     - Hệ thống luôn ưu tiên thử tải siêu tốc bằng `HttpFetcher` (tiết kiệm 90% RAM và CPU).
     - Nếu phát hiện mã HTML trả về rỗng, chỉ chứa khoảng trắng, hoặc gặp mã lỗi `403 Forbidden` $\rightarrow$ Pipeline tự động chuyển tiếp (fallback) sang `SeleniumFetcher` (Chrome Headless). Trình duyệt headless sẽ thực thi toàn bộ JavaScript, đợi trang render xong DOM hoàn chỉnh rồi mới chuyển sang parser.

3. **Bị chặn 403 Forbidden / 429 Too Many Requests (Anti-Bot & WAF)**:
   - **Vấn đề**: Các hệ thống bảo vệ (Cloudflare, Akamai, WAF) phát hiện bot qua chữ ký HTTP hoặc tần suất gửi request quá dày đặc.
   - **Hướng giải quyết**:
     - *Browser Fingerprint Emulation*: Trang bị bộ Header đầy đủ của trình duyệt người dùng thật: `User-Agent`, `Sec-Ch-Ua`, `Sec-Ch-Ua-Mobile`, `Sec-Ch-Ua-Platform`, `Sec-Fetch-Dest`, `Upgrade-Insecure-Requests`.
     - *Jitter Delay (Nghỉ ngẫu nhiên)*: Giữa các request cào HTML, hệ thống áp dụng khoảng trễ ngẫu nhiên: $\text{delay} = \text{base\_delay} + \text{random}(0.5, 1.5)\text{s}$. Điều này phá vỡ tính quy luật theo chu kỳ của bot.
     - *Exponential Backoff*: Khi gặp mã lỗi `429` hoặc `503`, hệ thống tự động tạm dừng với thời gian lũy tiến trước khi thử lại.

4. **Server phản hồi chậm, Timeout hoặc lỗi mạng chập chờn**:
   - **Vấn đề**: Server đích quá tải, kết nối mạng quốc tế gián đoạn khiến request bị treo vô thời hạn.
   - **Hướng giải quyết**:
     - Tách biệt rõ ràng 2 ngưỡng timeout: `connect_timeout = 10s` (kết nối socket) và `read_timeout = 30s` (nhận gói tin).
     - Cấu hình `HTTPAdapter` với `urllib3.util.Retry` tự động thử lại tối đa 3 lần cho các mã lỗi tạm thời (`500, 502, 503, 504`).
     - Khi hết số lần retry hoặc gặp `TimeoutException` của Selenium, pipeline ghi nhận trạng thái `crawl_status = "TIMEOUT"`, lưu thông báo lỗi và tiếp tục xử lý các bài viết tiếp theo mà không làm crash tiến trình.

5. **Quảng cáo, popup, thanh menu, liên kết ngoài bị lẫn vào nội dung**:
   - **Vấn đề**: Bóc tách nhầm các đoạn chữ quảng cáo, khuyến mãi, liên kết bài viết liên quan hoặc thanh điều hướng.
   - **Hướng giải quyết**:
     - *DOM Sanitization*: Trước khi trích xuất đoạn văn, bộ parser duyệt qua danh sách `clean_rules.strip_elements` (như `script`, `style`, `nav`, `.ads`, `.banner`, `.box-relate`, `.popup`) và gọi phương thức `decompose()` của BeautifulSoup để cắt bỏ vĩnh viễn khỏi cây DOM.
     - *Lựa chọn cụm đoạn văn tối ưu*: Parser tìm kiếm tất cả các container theo selector và chọn tập hợp các thẻ `<p>` có tổng số lượng đoạn văn hợp lệ dài nhất, loại bỏ các đoạn ngắn rác (< 10 ký tự).

6. **Trùng lặp URL và trùng lặp bài viết (Deduplication)**:
   - **Vấn đề**: Một bài viết có nhiều URL khác nhau do gắn tham số tracking (`?utm_source=...`, `fbclid=...`, `ref=...`), gây tốn băng thông và lưu trữ trùng lặp.
   - **Hướng giải quyết**:
     - *URL Normalization*: Loại bỏ triệt để toàn bộ query parameters thuộc danh mục tracking (`utm_*`, `fbclid`, `gclid`), đưa URL về dạng chuẩn tắc.
     - *Pre-crawl Hash Check*: Tính mã băm SHA-256 (16 ký tự đầu) từ URL chuẩn. Kiểm tra trong kho lưu trữ cục bộ `crawl_data/metadata/` trước khi gửi request qua mạng. Nếu bài đã tồn tại, hệ thống bỏ qua ngay lập tức (`Skipped`), tiết kiệm 100% tài nguyên tải.
     - Hỗ trợ cờ `--force` khi cần cố tình cào lại và cập nhật dữ liệu.

7. **Bài viết bị thiếu trường dữ liệu (Ẩn tác giả, không có ngày đăng)**:
   - **Vấn đề**: Một số trang báo không ghi rõ tác giả hoặc dùng định dạng ngày tháng phi chuẩn.
   - **Hướng giải quyết**:
     - Bóc tách theo chuỗi ưu tiên: Thẻ chuyên biệt $\rightarrow$ Thuộc tính OpenGraph (`article:published_time`, `article:author`) $\rightarrow$ Thẻ HTML5 Semantic (`<time datetime>`) $\rightarrow$ Dữ liệu ngày lấy được từ RSS/API ở Stage 1.
     - Gắn cờ kiểm soát chất lượng dữ liệu: Bổ sung trường `quality_flags` trong metadata (ví dụ: `["missing_author"]`, `["short_content"]`) để các tầng Data Pipeline xử lý sau (LLM Summarization, RAG) có thể lọc và xử lý phù hợp.

8. **Chuyển hướng liên kết (Redirect & Canonical URL)**:
   - **Vấn đề**: URL ban đầu từ mạng xã hội hoặc link rút gọn bị chuyển hướng sang URL mới, hoặc bài viết được tổng hợp từ báo khác.
   - **Hướng giải quyết**:
     - Luôn ghi nhận `response.url` (URL thực tế cuối cùng sau khi theo dõi chuỗi redirect).
     - Bóc tách thẻ `<link rel="canonical" href="...">` từ mã nguồn trang và lưu cả `url` ban đầu lẫn `canonical_url` vào metadata JSON để đảm bảo tính toàn vẹn và truy xuất nguồn gốc.

---

### 4.2. Hướng giải quyết các lỗi XML / RSS Feeds

1. **Schema không đồng nhất giữa RSS 0.9x, RSS 2.0, Atom 1.0 và RDF**:
   - **Vấn đề**: Mỗi chuẩn XML đặt tên thẻ khác nhau (ví dụ: ngày đăng trong RSS là `<pubDate>`, trong Atom là `<updated>` hoặc `<published>`; link trong RSS là text node, trong Atom là thuộc tính `<link href="...">`).
   - **Hướng giải quyết**: Sử dụng thư viện `feedparser`. Thư viện này đóng vai trò là một lớp trừu tượng hóa chuẩn (Universal Feed Abstraction Layer), tự động chuẩn hóa mọi biến thể XML về một cấu trúc Dict Python thống nhất (`entry.link`, `entry.title`, `entry.published_parsed`, `entry.summary`).

2. **File XML bị lỗi cú pháp / Malformed XML**:
   - **Vấn đề**: Server báo sinh XML cẩu thả, quên escape ký tự `&`, thiếu thẻ đóng `</item>` khiến các bộ parser XML chuẩn (như `xml.etree` hoặc `lxml`) bị văng lỗi cú pháp.
   - **Hướng giải quyết**: `feedparser` tích hợp bộ parser chịu lỗi (Forgiving SGML/HTML Parser). Khi gặp lỗi cú pháp, parser tự động đánh cờ `feed.bozo = 1`, ghi log debug cảnh báo mà vẫn phân tích và cứu được toàn bộ các bài viết có cấu trúc hợp lệ trong feed, không làm sập tiến trình thu thập.

3. **XML Namespaces mở rộng (`dc:creator`, `content:encoded`, `media:thumbnail`)**:
   - **Vấn đề**: Dữ liệu giá trị (tác giả, ảnh bìa, bài viết đầy đủ) thường được giấu trong các thẻ namespace mở rộng mà parser mặc định bỏ qua.
   - **Hướng giải quyết**: Xây dựng bộ ánh xạ namespace đa tầng trong `RssCollector`:
     - *Tác giả*: Quét `dc:creator` $\rightarrow$ `author_detail.name` $\rightarrow$ trường `author` mặc định.
     - *Ảnh đại diện*: Quét thẻ `media:content` $\rightarrow$ `media:thumbnail` $\rightarrow$ danh sách `enclosures` có kiểu mime là `image/*`.
     - *Tóm tắt*: Quét `content:encoded` $\rightarrow$ `summary` $\rightarrow$ `description`.

4. **Tóm tắt bị chèn mã HTML rác**:
   - **Vấn đề**: Trường tóm tắt trong RSS thường bị chèn các thẻ HTML quảng cáo hoặc thẻ ảnh như `<a href=...><img src=...></a>Tóm tắt bài...`.
   - **Hướng giải quyết**: Hàm `_extract_summary` trong `RssCollector` sử dụng BeautifulSoup để phân giải chuỗi và gọi `soup.get_text(" ", strip=True)`, loại bỏ hoàn toàn các thẻ HTML nhúng và chuẩn hóa thành một đoạn văn bản thuần sạch.

5. **Kênh RSS bị lỗi 403 / 429 hoặc lỗi mạng**:
   - **Vấn đề**: Một kênh RSS cụ thể của tờ báo bị chết link, chặn IP hoặc gặp sự cố server.
   - **Hướng giải quyết**: Toàn bộ vòng lặp duyệt `rss_feeds` được bọc trong khối try-catch độc lập. Nếu một feed bị lỗi HTTP 403/429 hoặc connection error, hệ thống ghi log cảnh báo và tự động chuyển sang đọc feed tiếp theo trong danh sách mà không làm gián đoạn các nguồn khác.

6. **RSS chỉ chứa tóm tắt ngắn (1-2 câu), thiếu nội dung chi tiết**:
   - **Vấn đề**: Hầu hết các tòa soạn báo không bao giờ phát toàn văn bài báo qua RSS để buộc độc giả phải truy cập website.
   - **Hướng giải quyết**: Kiến trúc **Two-Stage Ingestion chuẩn**:
     - Kênh RSS chỉ đảm nhiệm vai trò **Discovery Engine** (khám phá URL mới xuất bản trong 5-10 phút gần nhất).
     - Danh sách URL sau khi phát hiện sẽ tự động được chuyển tiếp sang **HTML Crawler** ở Stage 2 để cào toàn bộ các đoạn văn bản chi tiết, ảnh minh họa và lưu trữ file `.html.gz`.

7. **File Sitemap / RSS quá lớn (vài chục MB)**:
   - **Vấn đề**: Tải toàn bộ file XML nặng gây tiêu tốn RAM và nghẽn CPU.
   - **Hướng giải quyết**: Cung cấp tham số giới hạn `--limit <N>` trên CLI để chỉ lấy đúng N bài viết mới nhất trên đầu feed.

---

### 4.3. Hướng giải quyết các lỗi REST API JSON

1. **API Rate Limit / Quota (HTTP 429 Too Many Requests)**:
   - **Vấn đề**: Gọi liên tục vượt quá số lượng request cho phép trong một phút của nhà cung cấp API.
   - **Hướng giải quyết**:
     - *Tuân thủ tham số `rate_limit_delay`*: Mỗi nguồn API có thể cấu hình thời gian nghỉ tối thiểu giữa 2 request liên tiếp (mặc định: 1.0s).
     - *Tự động đọc Header `Retry-After`*: Khi nhận phản hồi HTTP 429, `ApiCollector` tự động bóc tách header `Retry-After` (hoặc mặc định 5s), đưa luồng vào trạng thái tạm dừng (`time.sleep`) đúng thời gian yêu cầu và tự động thử lại request trang đó tối đa 3 lần.

2. **Server API sập liên tục (HTTP 5xx Server Error)**:
   - **Vấn đề**: Cổng API nguồn bị sập cơ sở dữ liệu hoặc quá tải, liên tục trả về các mã lỗi 500, 502, 503, 504.
   - **Hướng giải quyết**: Cơ chế **Circuit Breaker (Ngắt mạch tự động)**:
     - Duy trì bộ đếm lỗi 5xx liên tiếp (`consecutive_5xx`).
     - Nếu nhận lỗi 5xx liên tiếp 3 lần (`max_consecutive_5xx = 3`), Circuit Breaker lập tức kích hoạt: Dừng toàn bộ các lượt gọi tiếp theo đến nguồn API đó trong phiên cào hiện tại để tránh lãng phí tài nguyên và bảo vệ hệ thống.
     - Nếu có một request thành công (HTTP 200), bộ đếm `consecutive_5xx` tự động reset về 0.

3. **API Key hết hạn / Lỗi xác thực 401 Unauthorized hoặc 404 Not Found**:
   - **Vấn đề**: Token xác thực API bị thu hồi, hết hạn hoặc endpoint bị nhà cung cấp đổi đường dẫn.
   - **Hướng giải quyết**: Khi gặp các mã lỗi client nghiêm trọng (401, 403, 404), `ApiCollector` ghi log cảnh báo mức `ERROR` và lập tức dừng tiến trình phân trang (Graceful Exit) để tránh bị khóa tài khoản hoặc lãng phí request.

4. **API thay đổi Schema / Khác tên trường giữa các phiên bản**:
   - **Vấn đề**: API nâng cấp phiên bản đổi trường `url` thành `link`, hoặc đổi `created_at` thành `published_at`.
   - **Hướng giải quyết**:
     - *Cấu hình Field Mapping linh hoạt*: Khai báo ánh xạ trường trong file YAML (`configs/sources/api/*.yaml`).
     - *Hỗ trợ ký hiệu dấu chấm (Dot Notation)*: Hàm `_get_nested_val` cho phép trích xuất các trường nằm sâu trong cấu trúc JSON lồng nhau (ví dụ: `user.profile.name`, `data.article.url`).
     - *Chuỗi Alias Fallback tự động*: Nếu trường trong mapping bị thiếu, hệ thống tự động tìm kiếm qua các alias phổ biến: `url` $\rightarrow$ `link` $\rightarrow$ `canonical_url` trước khi bỏ qua item.

5. **Phân trang đa hình (Multi-strategy Pagination)**:
   - **Vấn đề**: Mỗi API áp dụng một cơ chế phân trang khác nhau: một số dùng số trang `?page=1,2,3`, một số dùng độ lệch `?offset=0,20,40`.
   - **Hướng giải quyết**: Cấu trúc `PaginationConfig` trong Pydantic hỗ trợ cấu hình:
     - `type: "page"` $\rightarrow$ Tự động tăng param `page` theo từng vòng lặp.
     - `type: "offset"` $\rightarrow$ Tự động tính toán giá trị `offset = (page - 1) * page_size`.
     - *Điều kiện ngắt an toàn*: Tự động dừng phân trang khi API trả về danh sách rỗng, hoặc đạt giới hạn an toàn `max_pages`.



---

## 5. Cấu trúc Dữ liệu Đầu ra Chuẩn trong `crawl_data/`

Mỗi bài viết được cào sẽ tạo ra 2 tệp tin theo ngày xuất bản:

### 1. File Metadata JSON (`crawl_data/metadata/<source>/<YYYY>/<MM>/<DD>/<hash>_<timestamp>.json`)
```json
{
  "source": "vnexpress",
  "url": "https://vnexpress.net/alcaraz-thang-nguoc-o-my-mo-rong-2026-5116171.html",
  "final_url": "https://vnexpress.net/alcaraz-thang-nguoc-o-my-mo-rong-2026-5116171.html",
  "canonical_url": "https://vnexpress.net/alcaraz-thang-nguoc-o-my-mo-rong-2026-5116171.html",
  "title": "Alcaraz thắng ngược ở Mỹ Mở rộng 2026",
  "author": "Vy Anh",
  "published_at": "Thứ năm, 3/9/2026, 15:19 (GMT+7)",
  "content": "Mỹ ĐKVĐ Carlos Alcaraz hạ Jaime Faria 4-6, 6-0, 6-3, 6-2 ở vòng hai Mỹ Mở rộng...\n\nĐoạn văn tiếp theo...",
  "thumbnail_url": "https://i1-thethao.vnecdn.net/2026/09/03/ev5mmy2gjniczofjlphn3gfbja-178-1140-6361-1788423507.jpg",
  "raw_html_path": "crawl_data/raw/vnexpress/2026/09/03/4e6ae47b5ca3788f_085925_733558.html.gz",
  "http_status": 200,
  "crawl_status": "SUCCESS",
  "discovery_method": "rss",
  "discovery_metadata": {
    "feed_url": "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "guid": "https://vnexpress.net/alcaraz-thang-nguoc-o-my-mo-rong-2026-5116171.html"
  },
  "quality_flags": [],
  "fetched_at": "2026-09-03T08:59:25.733558+00:00",
  "error": null
}
```

### 2. File HTML Thô Nén (`crawl_data/raw/<source>/<YYYY>/<MM>/<DD>/<hash>_<timestamp>.html.gz`)
* Lưu giữ 100% mã HTML thô để phục vụ audit, kiểm tra lỗi hoặc chạy lại parser sau này.

---

## 6. Hướng dẫn Vận hành Dòng lệnh (CLI Entrypoints)

### 6.1. Thu thập hàng loạt bài mới qua RSS, API và Listing (`collect_news.py`)

```powershell
# 1. Chạy thử nghiệm chế độ Dry-Run (chỉ xem bài mới phát hiện, không tải HTML hay ghi đĩa)
python scripts/collect_news.py --source vnexpress --limit 5 --dry-run

# 2. Thu thập 10 bài mới nhất từ một nguồn RSS cụ thể (VnExpress)
python scripts/collect_news.py --source vnexpress --limit 10

# 3. Thu thập tin tức từ cổng REST API (DEV Community AI)
python scripts/collect_news.py --source devto --limit 10

# 4. Thu thập bài viết từ trang KHÔNG có RSS/API (quét qua Listing HTML)
python scripts/collect_news.py --source vietnamnet --limit 5

# 5. Thu thập toàn bộ các nguồn thuộc loại RSS
python scripts/collect_news.py --type rss --limit 5

# 6. Thu thập toàn bộ các nguồn thuộc loại API
python scripts/collect_news.py --type api --limit 10

# 7. Thu thập TẤT CẢ các nguồn đã đăng ký trong hệ thống
python scripts/collect_news.py --all --limit 10

# 8. Ép buộc cào lại các bài đã từng lưu trữ (--force)
python scripts/collect_news.py --source vnexpress --limit 5 --force
```

### 6.2. Cào một URL bài viết đơn lẻ (`crawl_to_db.py`)

Nếu bạn có sẵn một link bài viết cụ thể và muốn bóc tách ngay:

```powershell
# Cào bài viết trực tiếp (hệ thống tự nhận diện domain và nạp config tương ứng)
python scripts/crawl_to_db.py "https://vnexpress.net/link-bai-viet-5116171.html"

# Ép cào lại bài viết đơn lẻ
python scripts/crawl_to_db.py "https://vnexpress.net/link-bai-viet-5116171.html" --force
```

---

## 7. Hướng dẫn Thêm Nguồn Mới (RSS, API hoặc HTML Listing)

Để thêm nguồn tin mới, bạn chỉ cần tạo 1 file `.yaml` vào thư mục tương ứng trong `scripts/configs/sources/` mà **không cần sửa code Python**:

### Trường hợp 1: Thêm nguồn hỗ trợ RSS (Lưu vào `configs/sources/rss/<tên_nguồn>.yaml`)
```yaml
source_id: 10
source_name: "tuoitre"
display_name: "Tuổi Trẻ"
channel_type: "rss"
domains:
  - "tuoitre.vn"
rss_feeds:
  - "https://tuoitre.vn/rss/tin-moi-nhat.rss"
  - "https://tuoitre.vn/rss/khoa-hoc-cong-nghe.rss"
fetcher:
  type: "http"
  timeout: 15
parser:
  type: "declarative"
  selectors:
    title: ["h1.article-title", "h1"]
    content_paragraphs: [".detail-content p", "article p"]
```

### Trường hợp 2: Thêm nguồn hỗ trợ REST API JSON (Lưu vào `configs/sources/api/<tên_nguồn>.yaml`)
```yaml
source_id: 11
source_name: "hackernews"
display_name: "Hacker News Top"
channel_type: "api"
domains:
  - "news.ycombinator.com"
api:
  url: "https://hacker-news.firebaseio.com/v0/topstories.json"
  method: "GET"
  field_mapping:
    url: "url"
    title: "title"
```

### Trường hợp 3: Thêm nguồn KHÔNG có RSS/API (Lưu vào `configs/sources/html/<tên_nguồn>.yaml`)
```yaml
source_id: 12
source_name: "tinhte"
display_name: "Tinh Tế"
channel_type: "html"
domains:
  - "tinhte.vn"
listing_urls:
  - "https://tinhte.vn/categories/cong-nghe.11/"
fetcher:
  type: "http"
  timeout: 20
parser:
  type: "declarative"
  selectors:
    title: ["h1.thread-title", "h1"]
    content_paragraphs: [".message-body p", "article p"]
```
