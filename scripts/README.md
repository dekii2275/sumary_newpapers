# Hướng Dẫn Toàn Diện Hệ Thống Thu Thập Tin Tức Đa Kênh (Data Ingestion & Crawler Engine)

> **Kiến trúc Thu thập Dữ liệu Hai Giai đoạn (Two-Stage Ingestion Pipeline)** kết hợp giữa **RSS/Atom Feed XML**, **REST API JSON** và **HTML Web Crawler**, tự động đẩy dữ liệu thô đã làm sạch trực tiếp vào cơ sở dữ liệu PostgreSQL (bảng `raw_articles`).

---

## 📑 Mục lục
1. [Triết lý Thiết kế: Mô hình Hai Giai đoạn (Two-Stage Ingestion)](#1-triết-lý-thiết-kế-mô-hình-hai-giai-đoạn-two-stage-ingestion)
2. [Cấu trúc Thư mục & Phân loại Nguồn](#2-cấu-trúc-thư-mục--phân-loại-nguồn)
3. [Luồng Xử lý Dữ liệu Chi tiết (End-to-End Workflow)](#3-luồng-xử-lý-dữ-liệu-chi-tiết-end-to-end-workflow)
4. [Các Tính Năng & Kỹ Thuật Đã Hoàn Thiện](#4-các-tính-năng--kỹ-thuật-đã-hoàn-thiện)
5. [Hướng Dẫn Vận Hành & Sử Dụng (`collect_news.py`)](#5-hướng-dẫn-vận-hành--sử-dụng-collect_newspy)
6. [Tích hợp Tự Động Hóa với Airflow](#6-tích-hợp-tự-động-hóa-với-airflow)
7. [Hướng Dẫn Thêm Nguồn Mới qua YAML](#7-hướng-dẫn-thêm-nguồn-mới-qua-yaml)

---

## 1. Triết lý Thiết kế: Mô hình Hai Giai đoạn (Two-Stage Ingestion)

Hệ thống phân tách quy trình thu thập thành hai giai đoạn độc lập nhưng phối hợp chặt chẽ:

```text
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
│  - Kiểm tra xem URL đã tồn tại trong cơ sở dữ liệu (raw_articles) hay chưa  │
│  - Nếu bài đã tồn tại -> Bỏ qua, tiết kiệm 100% tài nguyên mạng và CPU       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (Chỉ cào bài mới)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  GIAI ĐOẠN 2: FULL-TEXT EXTRACTION & POSTGRESQL PERSISTENCE                 │
│  - Adaptive Fetcher: HTTP Fetcher ép mã hóa UTF-8 (chống lỗi phông chữ);    │
│    tự động chuyển sang Chrome Headless (Selenium) khi gặp trang JS động    │
│  - Cascade Parser: YAML CSS Selectors -> JSON-LD Schema.org -> Trafilatura  │
│  - DOM Cleaning: Tự động lọc bỏ bình luận, quảng cáo, footer, popup rác    │
│  - PostgreSQL Ingestion: Đẩy dữ liệu chuẩn trực tiếp vào bảng raw_articles  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Cấu trúc Thư mục & Phân loại Nguồn

Thư mục `scripts/` được tổ chức dạng module hóa cao:

```text
scripts/
├── configs/
│   └── sources/                       # CẤU HÌNH NGUỒN PHÂN LOẠI THEO KÊNH (YAML)
│       ├── rss/                       # Nguồn RSS / Atom Feed (VnExpress, Tuổi Trẻ, CafeF, TechCrunch)
│       ├── api/                       # Nguồn REST API JSON (DEV Community AI)
│       └── html/                      # Nguồn cào Listing HTML (VietnamNet)
│
├── crawler/                           # GÓI ĐỘNG CƠ CÀO CHÍNH
│   ├── collectors/                    # [Stage 1: Discovery] RSS, API, Listing Collectors
│   ├── fetchers/                      # [Fetchers] HttpFetcher (UTF-8) & SeleniumFetcher
│   ├── parsers/                       # [Parsers] GenericParser (Cascade Extraction 4 tầng)
│   ├── config_loader.py               # Quét đệ quy nạp file YAML cấu hình nguồn
│   ├── registry.py                    # Quản lý đăng ký nguồn & nạp từ PostgreSQL DB
│   ├── pipeline.py                    # Điều phối luồng cào 1 bài viết
│   └── utils.py                       # Chuẩn hóa URL, băm SHA-256, làm sạch văn bản
│
├── collect_news.py                    # ENTRYPOINT CHÍNH: Thu thập tin tức & lưu PostgreSQL DB
├── requirements.txt                   # Danh sách thư viện phụ thuộc
└── README.md                          # Tài liệu hướng dẫn này
```

---

## 3. Luồng Xử lý Dữ liệu Chi tiết (End-to-End Workflow)

1. **Khám phá (Discovery Stage)**:
   - `collect_news.py` gọi `get_collector_for_source(config)`.
   - `RssCollector`, `ApiCollector` hoặc `ListingCollector` phát hiện các liên kết bài báo xuất bản mới nhất.
2. **Khử trùng lặp (Deduplication Check Stage)**:
   - URL được làm sạch (bỏ query parameters `utm_*`, `fbclid`, `gclid`).
   - Kiểm tra trực tiếp với cơ sở dữ liệu PostgreSQL (bảng `raw_articles`). Nếu bài viết đã tồn tại và không có cờ `--force`, bài viết lập tức được bỏ qua.
3. **Bóc tách nội dung (Extraction Stage)**:
   - `HttpFetcher` tải trang HTML với cơ chế ưu tiên mã hóa **UTF-8** (giải quyết triệt để lỗi phông chữ tiếng Việt trên Tuổi Trẻ, VnExpress...).
   - Nếu gặp trang JavaScript động hoặc lỗi 403, tự động chuyển sang `SeleniumFetcher` (Chrome Headless).
   - `GenericParser` trích xuất nội dung qua 4 tầng: *YAML Selectors $\rightarrow$ Schema.org JSON-LD $\rightarrow$ Trafilatura NLP $\rightarrow$ Discovery Metadata Fallback*.
   - **Làm sạch DOM (DOM Sanitization)**: Tự động decomposed (xóa vĩnh viễn) các khung bình luận, form nhập email, nút chia sẻ social, quảng cáo... theo quy tắc `strip_elements`.
4. **Lưu trữ vào Cơ sở dữ liệu (Database Ingestion Stage)**:
   - Hàm `save_crawl_result_to_db` tự động tra cứu `source_id` tương ứng từ bảng `sources` và chèn bản ghi mới vào bảng `raw_articles`.

---

## 4. Các Tính Năng & Kỹ Thuật Đã Hoàn Thiện

| Tính năng | Mô tả kỹ thuật |
| :--- | :--- |
| **Hỗ trợ Đa Kênh** | Tự động xử lý cả 3 loại kênh thu thập: RSS Feed XML, REST API JSON và Web Listing HTML. |
| **Xử lý Mã Hóa UTF-8** | Tự động định dạng mã hóa `utf-8` cho response HTTP, khắc phục hiện tượng lỗi font tiếng Việt (Mojibake). |
| **Bóc Tách Sạch Nội Dung** | Loại bỏ hoàn toàn bình luận rác, iframe quảng cáo, form email nhờ danh sách `strip_elements` mở rộng. |
| **Nạp Cấu Hình Tự Động** | Hỗ trợ nạp cấu hình nguồn từ các file local `.yaml` hoặc nạp trực tiếp danh sách nguồn active từ PostgreSQL DB (`sources`). |
| **Lưu Trực Tiếp PostgreSQL** | Lưu kết quả trực tiếp vào bảng `raw_articles` với đầy đủ thông tin metadata (`title_raw`, `content_raw`, `author`, `published_at`, `external_url`). |

---

## 5. Hướng Dẫn Vận Hành & Sử Dụng (`collect_news.py`)

### 5.1. Chạy trong Code Python (Zero-Config API)
Bạn có thể import hàm `run_news_collector` và gọi trực tiếp để thực thi pipeline chuẩn tự động (mặc định lưu 100% vào DB, không lưu local file):

```python
from collect_news import run_news_collector

# Chạy pipeline chuẩn: Tự động nạp nguồn active từ DB -> Kiểm tra trùng lặp -> Cào bài mới -> Lưu raw_articles (save_local=False)
stats = run_news_collector()
print(stats)

# Nếu muốn lưu thêm một bản sao file thô (.html.gz và .json) ở local:
stats = run_news_collector(save_local=True)
```

### 5.2. Chạy từ Dòng lệnh (CLI Options)

```bash
# 1. Chạy mặc định (quét toàn bộ các nguồn active trong DB và lưu trực tiếp vào PostgreSQL)
python scripts/collect_news.py

# 2. Thu thập một nguồn báo cụ thể (ví dụ: Tuổi Trẻ) với giới hạn 5 bài
python scripts/collect_news.py --source tuoitre --limit 5

# 3. Thu thập tin tức từ cổng REST API (DEV Community AI)
python scripts/collect_news.py --source devto --limit 10

# 4. Ép buộc cào lại bài viết dù đã tồn tại trong DB (--force)
python scripts/collect_news.py --source vnexpress --limit 5 --force

# 5. Lưu thêm bản sao file thô (.html.gz và .json) vào thư mục local crawl_data/ (--save-local)
python scripts/collect_news.py --source tuoitre --save-local

# 6. Chạy thử nghiệm chế độ Dry-Run (chỉ xem bài mới phát hiện, không tải HTML hay lưu DB)
python scripts/collect_news.py --source tuoitre --dry-run
```

---

## 6. Tích hợp Tự Động Hóa với Airflow

Pipeline cào tin tức đã được tự động hóa hoàn toàn thông qua DAG Airflow `auto_collect_news_dag.py` (`dags/auto_collect_news_dag.py`).

DAG gọi trực tiếp `run_news_collector()` theo chu kỳ **2 tiếng/lần**, tự động quét và cập nhật tin tức mới từ tất cả các nguồn báo đã đăng ký vào cơ sở dữ liệu `tech_news_db`.

---

## 7. Hướng Dẫn Thêm Nguồn Mới qua YAML

Để thêm một nguồn tin tức mới vào hệ thống, chỉ cần tạo 1 tệp cấu hình `.yaml` trong thư mục `scripts/configs/sources/<loại_kênh>/` mà **không cần chỉnh sửa code Python**:

### Cấu hình mẫu cho nguồn RSS (`scripts/configs/sources/rss/tuoitre.yaml`):
```yaml
source_id: 4
source_name: "tuoitre"
display_name: "Tuổi Trẻ Online"
channel_type: "rss"
domains:
  - "tuoitre.vn"
rss_feeds:
  - "https://tuoitre.vn/rss/tin-moi-nhat.rss"
  - "https://tuoitre.vn/rss/cong-nghe.rss"
fetcher:
  type: "http"
  timeout: 15
parser:
  type: "declarative"
  selectors:
    title: ["h1.article-title", "h1.detail-title", "h1"]
    content_paragraphs: [".detail-content p", "#main-detail-body p", "article p"]
```
