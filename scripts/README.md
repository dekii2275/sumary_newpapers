# Hướng Dẫn Toàn Diện Module Cào Dữ Liệu Bài Báo (Data Crawler Engine — Step 1)

> Module thu thập dữ liệu bài viết đa nguồn tự động, được thiết kế theo kiến trúc **Pure Config-Driven (100% hướng cấu hình)**. Module này đóng vai trò là tầng đầu tiên (Step 1: Data Collection Lakehouse) trong toàn bộ hệ thống AI Tech News Intelligence.

---

## 📑 Mục lục
1. [Tổng quan Triết lý Thiết kế](#1-tổng-quan-triết-lý-thiết-kế)
2. [Chi tiết Vai trò của Từng Thành phần trong `scripts/`](#2-chi-tiết-vai-trò-của-từng-thành-phần-trong-scripts)
3. [Luồng Xử lý Dữ liệu Chi tiết (End-to-End Workflow)](#3-luồng-xử-lý-dữ-liệu-chi-tiết-end-to-end-workflow)
4. [Cơ chế Bóc tách Đa tầng & Khử Trùng Lặp](#4-cơ-chế-bóc-tách-đa-tầng--khử-trùng-lặp)
5. [Cấu trúc Dữ liệu Đầu ra Chuẩn trong `crawl_data/`](#5-cấu-trúc-dữ-liệu-đầu-ra-chuẩn-trong-crawl_data)
6. [Hướng dẫn Chi tiết Cách Thêm Nguồn Báo Mới](#6-hướng-dẫn-chi-tiết-cách-thêm-nguồn-báo-mới)
7. [Hướng dẫn Vận hành Dòng lệnh (CLI) & Kiểm thử](#7-hướng-dẫn-vận-hành-dòng-lệnh-cli--kiểm-thử)
8. [Xử lý Tình huống Thực tế & Best Practices](#8-xử-lý-tình-huống-thực-tế--best-practices)

---

## 1. Tổng quan Triết lý Thiết kế

Trong các hệ thống cào dữ liệu truyền thống, mỗi khi muốn thêm một trang báo mới, lập trình viên thường phải:
- Viết thêm 1 file crawler Python mới.
- Viết thêm 1 file parser BeautifulSoup mới.
- Viết các câu lệnh `if/else` để chọn parser thủ công.

**Cách làm này gây phình mã nguồn, khó bảo trì và dễ sinh lỗi.**

### 🎯 Giải pháp của Module: Pure Config-Driven Engine
- **Tách rời Cấu hình (YAML) khỏi Động cơ (Engine):** Mọi quy tắc về nguồn báo (tên miền, loại fetcher, CSS selector, luật lọc rác) đều được khai báo 100% trong file cấu hình `.yaml`.
- **Chỉ duy nhất 1 bộ bóc tách tổng quát (`GenericParser`):** Nhận cấu hình YAML và tự động bóc tách dữ liệu cho mọi trang báo.
- **Tự động nhận diện (Zero Configuration CLI):** Chỉ cần truyền vào một URL bất kỳ, hệ thống sẽ tự nhận diện domain, nạp đúng config, chọn đúng công cụ tải (HTTP/Selenium) và bóc tách dữ liệu hoàn toàn tự động.

---

## 2. Chi tiết Vai trò của Từng Thành phần trong `scripts/`

```text
scripts/
├── configs/
│   └── sources/                       # THƯ MỤC CẤU HÌNH NGUỒN (YAML)
│       ├── vnexpress.yaml             # Cấu hình nguồn VnExpress
│       ├── cafef.yaml                 # Cấu hình nguồn CafeF
│       └── techcrunch.yaml            # Cấu hình nguồn TechCrunch
│
├── crawler/                           # GÓI ĐỘNG CƠ CÀO MODULAR CHÍNH
│   ├── __init__.py
│   ├── config_loader.py               # Module đọc & xác thực schema YAML qua Pydantic
│   ├── registry.py                    # Registry trung tâm: Ánh xạ domain URL -> YAML -> Fetcher & Parser
│   ├── utils.py                       # Module tiện ích: Chuẩn hóa URL, băm SHA-256, kiểm tra trùng lặp, nén Gzip & lưu JSON
│   ├── pipeline.py                    # Bộ điều phối (Orchestrator): Quản lý toàn bộ vòng đời cào 1 bài viết
│   │
│   ├── fetchers/                      # CÁC BỘ TẢI TRANG WEB
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseFetcher interface trừu tượng
│   │   ├── http_fetcher.py            # Tải trang tĩnh siêu tốc qua HTTP Requests (nhẹ, tiết kiệm RAM)
│   │   └── selenium_fetcher.py        # Tải trang JS động qua Chrome Headless tự động (hỗ trợ lazy init)
│   │
│   └── parsers/                       # BỘ BÓC TÁCH VẠN NĂNG
│       ├── __init__.py
│       ├── base.py                    # BaseParser interface trừu tượng
│       └── generic_parser.py          # Bộ bóc tách tổng quát (JSON-LD + YAML Selectors + Trafilatura)
│
├── crawl_to_db.py                     # CLI Entrypoint để cào bài viết từ terminal
├── requirements.txt                   # Danh sách dependencies
└── README.md                          # Tài liệu tổng quan này
```

### Bảng tóm tắt chức năng từng tệp:

| Tệp / Thư mục | Vai trò chính |
| :--- | :--- |
| `configs/sources/*.yaml` | Nơi khai báo luật bóc tách của từng tờ báo (không chứa mã code, chỉ chứa cấu hình). |
| `crawler/config_loader.py` | Đọc file `.yaml`, kiểm tra tính hợp lệ của cấu trúc bằng Pydantic models (`SourceConfig`, `SelectorConfig`, `CleanRulesConfig`). |
| `crawler/registry.py` | Quét thư mục `configs/sources/` khi khởi động, tạo bảng tra cứu `domain -> config`, và đóng vai trò là Factory tạo Fetcher / GenericParser tương ứng. |
| `crawler/pipeline.py` | Nhận URL $\rightarrow$ gọi `utils.normalize_url` $\rightarrow$ kiểm tra trùng lặp $\rightarrow$ gọi Fetcher tải HTML $\rightarrow$ gọi GenericParser bóc tách $\rightarrow$ gọi `utils.save_artifacts` lưu đĩa. |
| `crawler/utils.py` | Xử lý chuỗi (cắt query `utm_...`), băm `url_hash`, tìm file đã cào trước đó (`find_existing_artifact`), nén `.html.gz` và ghi file `.json`. |
| `crawler/fetchers/http_fetcher.py` | Sử dụng `requests` với browser headers đầy đủ để tải mã nguồn HTML của các trang tĩnh một cách nhanh nhất. |
| `crawler/fetchers/selenium_fetcher.py` | Điều khiển trình duyệt Chrome không giao diện (Headless Chrome) để cào các trang dựng bằng React/Vue/Angular hoặc yêu cầu chạy JavaScript. |
| `crawler/parsers/generic_parser.py` | Bóc tách bài viết theo cơ chế đa tầng (Cascade Extraction) dựa trên cấu hình YAML. |

---

## 3. Luồng Xử lý Dữ liệu Chi tiết (End-to-End Workflow)

![Sơ đồ Luồng Xử lý Dữ liệu Crawler](../docs/images/crawler_workflow.png)

---


## 4. Cơ chế Bóc tách Đa tầng & Khử Trùng Lặp

### 4.1. Cơ chế Bóc tách Đa tầng (Cascade Extraction) của `GenericParser`
`GenericParser` không phụ thuộc cứng vào bất kỳ class HTML nào mà xử lý theo 4 tầng bảo vệ:
1. **Tầng 1 (Chuẩn quốc tế):** Tìm thẻ `<script type="application/ld+json">` để lấy metadata chuẩn `NewsArticle` (tiêu đề, ngày đăng ISO, tác giả, thumbnail).
2. **Tầng 2 (CSS Selectors từ YAML):** Duyệt qua danh sách selector ưu tiên được khai báo trong YAML. Hỗ trợ lấy text hoặc lấy thuộc tính bằng cú pháp `@tên_thuộc_tính` (ví dụ: `meta[property='og:image']@content`, `img@src`).
3. **Tầng 3 (Làm sạch DOM):** Loại bỏ các phần tử banner, quảng cáo, box tương tác (`strip_elements`) trước khi ghép các đoạn văn bài viết.
4. **Tầng 4 (Heuristic Fallback):** Nếu toàn bộ CSS Selectors không khớp (do trang web đổi layout hoặc là trang web mới lạ), thuật toán **Trafilatura** sẽ tự động phân tích cấu trúc DOM để trích xuất nội dung bài viết chính xác.

### 4.2. Cơ chế Khử trùng lặp Thông minh (Pre-fetch Deduplication)
- Khi nhận URL, hệ thống tính mã băm `url_hash = sha256(normalize_url(url))[:16]`.
- Hệ thống kiểm tra xem file metadata có chứa mã `url_hash` này đã có trong thư mục `crawl_data/metadata/` chưa.
- **Nếu đã có:** Trả về kết quả ngay lập tức mà không cần gửi request qua mạng (tiết kiệm 100% băng thông).
- **Nếu muốn cào lại:** Chỉ cần thêm cờ `--force`.

---

## 5. Cấu trúc Dữ liệu Đầu ra Chuẩn trong `crawl_data/`

Mỗi bài viết cào thành công sẽ sinh ra 2 tệp tại Local Lakehouse:

### 1. Tệp Metadata JSON
Đường dẫn: `crawl_data/metadata/<source_name>/<YYYY>/<MM>/<DD>/<url_hash>_<timestamp>.json`

```json
{
  "source": "vnexpress",
  "url": "https://vnexpress.net/galaxy-s26-fe-smartphone-gia-tot-voi-ai-cao-cap-5114783.html",
  "final_url": "https://vnexpress.net/galaxy-s26-fe-smartphone-gia-tot-voi-ai-cao-cap-5114783.html",
  "title": "Galaxy S26 FE - smartphone giá tốt với AI cao cấp",
  "author": "Huy Đức",
  "published_at": "Thứ bảy, 29/8/2026, 11:00 (GMT+7)",
  "content": "Galaxy S26 FE thừa hưởng thiết kế cao cấp của dòng S26, màn hình đẹp, cấu hình mạnh cùng các tính năng Galaxy AI thế hệ mới...\n\nĐoạn văn tiếp theo...",
  "thumbnail_url": "https://i2-vnexpress.vnecdn.net/2026/08/29/DSC9539-1787937571.jpg?w=1200&h=675&q=100&dpr=1&fit=crop&s=VU9WCNLigyHFoykGc4656A",
  "raw_html_path": "crawl_data/raw/vnexpress/2026/08/29/c71851d9c7fa3d95_075525_991865.html.gz",
  "http_status": null,
  "crawl_status": "SUCCESS",
  "fetched_at": "2026-08-29T07:55:25.991865+00:00",
  "error": null
}
```

### 2. Tệp HTML Thô Nén (Raw HTML Gzip)
Đường dẫn: `crawl_data/raw/<source_name>/<YYYY>/<MM>/<DD>/<url_hash>_<timestamp>.html.gz`
- Lưu giữ nguyên vẹn 100% mã HTML của bài viết tại thời điểm cào để phục vụ audit hoặc trích xuất lại dữ liệu sau này mà không cần truy cập lại website gốc.

---

## 6. Hướng dẫn Chi tiết Cách Thêm Nguồn Báo Mới

Để thêm một trang báo mới vào hệ thống (ví dụ: Báo Dân Trí `dantri.com.vn`), bạn **KHÔNG CẦN VIẾT CODE PYTHON**, chỉ cần thực hiện 3 bước sau:

### Bước 1: Khảo sát nhanh trang web
Mở trình duyệt (F12 $\rightarrow$ Inspect Element) để xem:
- Thẻ tiêu đề: `h1.title-detail`
- Thẻ tác giả: `.author-name`
- Thẻ ngày đăng: `.author-time`
- Thẻ nội dung: `.singular-content p`

### Bước 2: Tạo file cấu hình `scripts/configs/sources/dantri.yaml`

```yaml
source_id: 4
source_name: "dantri"
display_name: "Dân Trí"
domains:
  - "dantri.com.vn"

fetcher:
  type: "http"             # "http" (trang tĩnh) hoặc "selenium" (trang JS động)
  timeout: 15

parser:
  type: "declarative"
  selectors:
    title:
      - "h1.title-detail"
      - "h1"
      - "meta[property='og:title']@content"
    author:
      - ".author-name"
      - ".author"
      - "span.name"
    published_at:
      - "meta[property='article:published_time']@content"
      - ".author-time"
      - "time[datetime]@datetime"
    thumbnail_url:
      - "meta[property='og:image']@content"
      - "article img@src"
    content_paragraphs:
      - ".singular-content p"
      - "article p"
      - ".content p"
  clean_rules:
    strip_elements:
      - ".banner"
      - ".related-news"
      - ".box-social"
      - "script"
      - "style"
```

### Bước 3: Quy tắc cú pháp Selector cần nhớ
- **Lấy văn bản thẻ:** Nhập chuỗi selector thông thường (ví dụ: `h1.title`, `span.author`).
- **Lấy giá trị thuộc tính:** Thêm ký tự `@tên_thuộc_tính` vào sau selector:
  - `meta[property='og:image']@content` $\rightarrow$ Lấy giá trị thuộc tính `content`.
  - `img.thumbnail@src` $\rightarrow$ Lấy giá trị thuộc tính `src`.
  - `time[datetime]@datetime` $\rightarrow$ Lấy giá trị thuộc tính `datetime`.
- **Danh sách ưu tiên:** Các selector được xếp từ trên xuống dưới; selector đầu tiên tìm thấy dữ liệu hợp lệ sẽ được sử dụng.

---

## 7. Hướng dẫn Vận hành Dòng lệnh (CLI) & Kiểm thử

### 7.1. Cài đặt môi trường

```powershell
# Kích hoạt môi trường ảo (Windows PowerShell)
.\.env\Scripts\Activate.ps1

# Cài đặt các thư viện cần thiết
pip install -r scripts/requirements.txt
```

### 7.2. Các câu lệnh cào bài viết

```powershell
# 1. Cào bài viết VnExpress (Tự động nhận diện nguồn từ URL)
python .\scripts\crawl_to_db.py "https://vnexpress.net/khoa-hoc/bai-viet-cong-nghe-5114812.html"

# 2. Cào bài viết CafeF
python .\scripts\crawl_to_db.py "https://cafef.vn/tai-chinh-ngan-hang.chn"

# 3. Cào một bài viết từ trang web LẠ chưa có file YAML (Tự động bóc tách qua Trafilatura)
python .\scripts\crawl_to_db.py "https://vietnamnet.vn/cong-nghe/bai-viet-ai.html"

# 4. Ép buộc cào lại bài viết bỏ qua bộ đệm trùng lặp (--force)
python .\scripts\crawl_to_db.py "https://vnexpress.net/galaxy-s26-fe-...html" --force
```

## 8. Xử lý Tình huống Thực tế & Best Practices

1. **Trang báo bất ngờ thay đổi class HTML:**
   - Bạn không cần sửa code Python. Chỉ cần mở file YAML tương ứng trong `configs/sources/` và bổ sung selector mới vào danh sách.
   - Ngay cả khi chưa kịp sửa YAML, hệ thống vẫn tự động trích xuất được bài viết nhờ tầng dự phòng **Trafilatura Heuristic Fallback**.
2. **Trang báo load dữ liệu bằng AJAX/JavaScript:**
   - Đổi `fetcher.type: "selenium"` trong file YAML của nguồn đó để hệ thống tự động khởi chạy Chrome Headless chờ trang render xong mới lấy HTML.
3. **Tiết kiệm tài nguyên và hiệu năng:**
   - Ưu tiên sử dụng `fetcher.type: "http"` cho tất cả các trang báo hỗ trợ Server-Side Rendering (SSR) như VnExpress, CafeF, TechCrunch để tốc độ cào đạt dưới 1 giây/bài và tiết kiệm RAM.
