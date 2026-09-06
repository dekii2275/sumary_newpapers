# AI Tech News Intelligence & Automated Video

> Nền tảng tự động thu thập, hiểu, tổng hợp tin tức AI/công nghệ và chuyển hóa chúng thành nội dung đa nền tảng, bao gồm video ngắn.

## Tổng quan

Hệ thống tập hợp tin tức từ nhiều nguồn về AI, công nghệ, startup, sản phẩm mới, nghiên cứu và Big Tech. Dữ liệu sau đó được làm sạch, khử trùng lặp và xử lý bằng NLP/LLM để tạo thành một kho tri thức có cấu trúc.

Một nguồn dữ liệu đầu vào phục vụ đồng thời hai nhóm nhu cầu:

- **Độc giả:** đọc tin, xem tóm tắt, tìm kiếm ngữ nghĩa và hỏi đáp với kho tin tức.
- **Người sáng tạo nội dung:** tạo bài đăng, newsletter, kịch bản và video ngắn cho các nền tảng khác nhau.

Mục tiêu của dự án là giảm thời gian phải theo dõi hàng chục website, đồng thời biến tin tức thô thành thông tin có thể tìm kiếm, phân tích và tái sử dụng.

## Luồng xử lý

```text
Nguồn tin đa dạng
        │
        ▼
Thu thập & chuẩn hóa dữ liệu
        │
        ▼
Làm sạch & khử trùng lặp
        │
        ▼
NLP/LLM: phân loại, trích xuất, tóm tắt, phân tích
        │
        ▼
Kho tin tức + Vector DB + Object Storage
        ├──────────────────────┐
        ▼                      ▼
Website & News Chatbot   Content & Video Pipeline
```

## Chức năng chính

### 1. Thu thập tin tức đa nguồn

Hệ thống dự kiến hỗ trợ các nhóm nguồn sau:

- Báo chí và website thông qua RSS, News API và web crawler.
- Mạng xã hội như YouTube, X và Reddit.
- Nền tảng kỹ thuật/học thuật như arXiv và GitHub.

Các Collector Service trích xuất và chuẩn hóa dữ liệu thô về một cấu trúc thống nhất, gồm tiêu đề, nội dung, tác giả, thời gian xuất bản, URL và media.

### 2. Làm sạch và khử trùng lặp

Pipeline xử lý dữ liệu web gồm:

- Loại bỏ HTML rác, quảng cáo và boilerplate.
- Trích xuất phần nội dung chính của bài viết.
- Nhận diện ngôn ngữ và chuẩn hóa văn bản.
- So khớp URL và nội dung để phát hiện các bài viết trùng hoặc tương đồng.
- Gom các bản tin tương đồng thành một **Canonical Article**.

### 3. News Intelligence

Hệ thống biến bài viết đã chuẩn hóa thành tri thức có cấu trúc thông qua:

- Phân loại chủ đề và chuyên mục.
- Trích xuất thực thể tên riêng.
- Tạo bản tóm tắt và các luận điểm cốt lõi.
- Phân tích mức độ ảnh hưởng và chấm điểm độ quan trọng.
- Liên kết bài viết với các chủ đề, sự kiện và thực thể liên quan.
- Tạo embedding ở cấp bài viết, bản tóm tắt và từng đoạn nội dung.

### 4. Website tin tức

- **Trang chủ:** hiển thị tin mới nhất, tin nổi bật và các chuyên mục như AI, Robotics, Research, Startup, Big Tech và Hardware.
- **Trang bài viết:** hiển thị tóm tắt AI, key takeaways, phân tích “Why It Matters”, nội dung gốc và nguồn trích dẫn.
- **TL;DR tùy biến:** cho phép chọn thời lượng đọc khoảng 30 giây, 1 phút, 3 phút hoặc toàn bài.
- **Ask AI:** hỏi đáp trực tiếp dựa trên bài viết hiện tại và các bài liên quan.

### 5. AI News Chatbot

Hệ thống có hai chế độ hội thoại:

- **Article Chat:** chỉ sử dụng bài viết đang đọc và một số ngữ cảnh liên quan, giúp phản hồi nhanh và tiết kiệm token.
- **Global News Chat:** tìm kiếm, tổng hợp và phân tích trên toàn bộ kho tin tức.

Global News Chat sử dụng quy trình RAG gồm:

1. Nhận diện ý định và viết lại truy vấn, bao gồm xử lý mốc thời gian.
2. Kết hợp tìm kiếm từ khóa BM25 với tìm kiếm vector.
3. Rerank các đoạn nội dung liên quan nhất.
4. Dùng LLM tạo câu trả lời kèm trích dẫn nguồn.

Kiến trúc được thiết kế để có thể mở rộng lên Agentic RAG với khả năng suy luận nhiều bước, tra cứu lặp và tự đánh giá kết quả.

### 6. Tạo nội dung đa nền tảng

Content Strategy Agent phân tích bài viết và lựa chọn góc tiếp cận phù hợp, chẳng hạn:

- Breaking News.
- Why It Matters.
- 3 Things You Should Know.
- Developer Perspective.
- Comparison.

Từ góc tiếp cận đó, hệ thống có thể sinh nội dung cho LinkedIn, Facebook, Twitter/X Thread và Newsletter.

### 7. Tự động tạo video ngắn

Pipeline video chuyển kịch bản thành video dọc cho TikTok, YouTube Shorts và Reels:

1. **Scene Splitter:** chia kịch bản thành hook, bối cảnh, thông tin chính, ý nghĩa, kết luận và CTA.
2. **Multi-modal Asset Generation:** tạo hoặc truy xuất hình ảnh, sinh giọng đọc TTS, phụ đề theo từng từ và lựa chọn nhạc nền.
3. **Composition & Rendering:** ghép hình ảnh, âm thanh, hiệu ứng, chuyển cảnh và phụ đề để xuất video MP4.

## Kiến trúc dữ liệu

Hệ thống sử dụng mô hình lưu trữ đa dạng (**Polyglot Persistence**) để phù hợp với từng loại dữ liệu:

- **PostgreSQL:** bài viết, nguồn tin, người dùng, thực thể, chủ đề, sự kiện và quan hệ giữa chúng.
- **Qdrant hoặc pgvector:** embeddings cho semantic search và RAG.
- **MinIO hoặc S3:** hình ảnh, audio TTS, video render và thumbnails.
- **Redis:** cache và message broker.
- **Celery:** xử lý các tác vụ nền như crawling, embedding, tóm tắt và render video.

## Tech stack đề xuất

| Tầng | Công nghệ | Vai trò |
| --- | --- | --- |
| Frontend | Next.js, TypeScript | Website tin tức và Admin Dashboard |
| UI | Tailwind CSS, shadcn/ui | Xây dựng giao diện |
| Backend API | Python, FastAPI | API chính |
| ORM & Migration | SQLAlchemy, Alembic | Truy cập và version hóa database |
| Main Database | PostgreSQL | Dữ liệu quan hệ và dữ liệu nghiệp vụ |
| Vector Database | Qdrant | Semantic search và RAG |
| Cache / Queue | Redis, Celery | Cache, message broker và background jobs |
| Agent Workflow | LangGraph | Chatbot và content agents |
| Crawling | Playwright, BeautifulSoup/Trafilatura | Thu thập và trích xuất bài viết |
| LLM | OpenAI, Gemini, Claude | Tóm tắt, trích xuất và sinh nội dung |
| Embedding | OpenAI, Gemini, BGE | Vector hóa tin tức |
| Reranking | BGE Reranker, Cohere | Tối ưu kết quả RAG |
| Video | Remotion, FFmpeg hoặc MoviePy | Sinh và render video ngắn |
| TTS | OpenAI TTS, ElevenLabs hoặc Google | Voice-over |
| Object Storage | MinIO hoặc S3 | Lưu trữ media |
| Monitoring | Prometheus, Grafana | Metrics hệ thống |
| LLM Monitoring | LangSmith, OpenTelemetry | Theo dõi agent và RAG |
| Container | Docker, Docker Compose | Phát triển và triển khai |
| Reverse Proxy | Nginx hoặc Traefik | Routing |
| CI/CD | GitHub Actions | Kiểm thử và deploy |

## Triển khai dự kiến

Các thành phần backend, worker, database, vector database, Redis và object storage được đóng gói bằng Docker. Reverse proxy đảm nhiệm routing và có thể được kết hợp với GitHub Actions để tự động kiểm thử, build và triển khai.

Các secret như API key của LLM, thông tin database, object storage và dịch vụ TTS cần được cung cấp qua biến môi trường hoặc secret manager; không commit trực tiếp vào repository.

## Chạy local bằng Docker

### 1. Chuẩn bị biến môi trường
Trước khi chạy, bạn có thể tạo file `.env` từ file mẫu:
```bash
cp .env.example .env
```
*(Nếu không tạo file `.env`, Docker Compose đã được cấu hình sẵn các giá trị mặc định an toàn cho môi trường phát triển local).*

### 2. Danh sách các service và cổng kết nối

| Service | Container Name | Cổng host | Cổng container | Mô tả |
| --- | --- | ---: | ---: | --- |
| Frontend | `tech-news-frontend` | `13000` | `3000` | Giao diện Next.js |
| Backend | `tech-news-backend` | `18080` | `8000` | FastAPI chính |
| PostgreSQL | `tech-news-postgres` | `15432` | `5432` | Cơ sở dữ liệu tin tức nghiệp vụ |
| Airflow Webserver | `tech-news-airflow-webserver` | `18088` | `8080` | UI quản lý pipeline crawler |
| Airflow Scheduler | `tech-news-airflow-scheduler` | - | - | Bộ lập lịch thu thập tin tức |
| Airflow Postgres | `tech-news-airflow-postgres` | - | `5432` | DB metadata nội bộ của Airflow |

### 3. Lệnh khởi động

Khởi động toàn bộ stack (Frontend, Backend, DB & Airflow):

```bash
docker compose up --build -d
```

Hoặc chỉ khởi động cụm ứng dụng chính (không kèm Airflow):

```bash
docker compose up --build -d postgres backend frontend
```

Truy cập các service:

- Frontend: <http://localhost:13000>
- Backend: <http://localhost:18080>
- Backend health check: <http://localhost:18080/health>
- Kiểm tra kết nối PostgreSQL: <http://localhost:18080/db-check>

Xem log hoặc dừng stack:

```bash
docker compose logs -f
docker compose down
```

Các cổng host có thể đổi qua biến môi trường, ví dụ:

```bash
BACKEND_PORT=18081 FRONTEND_PORT=13001 POSTGRES_PORT=15433 docker compose up --build -d
```

> PostgreSQL sử dụng volume `postgres_data` để giữ dữ liệu khi container được recreate. Mật khẩu mặc định trong compose chỉ dành cho môi trường local.

## Trạng thái dự án

Hiện repository đang ở giai đoạn khởi tạo và định hình kiến trúc. Đã có Docker scaffold cho frontend, backend và PostgreSQL cùng các endpoint kiểm tra cơ bản; các module nghiệp vụ như collector, NLP/LLM pipeline, RAG và video generation sẽ được phát triển tiếp theo.

## Lộ trình phát triển đề xuất

- [ ] Khởi tạo monorepo và cấu trúc service.
- [ ] Xây dựng Collector Service cho RSS, News API và crawler.
- [ ] Hoàn thiện pipeline làm sạch, canonicalization và duplicate detection.
- [ ] Xây dựng mô hình dữ liệu PostgreSQL và lớp vector search.
- [ ] Tích hợp summarization, entity extraction, classification và embeddings.
- [ ] Phát triển website tin tức và Article Chat.
- [ ] Phát triển Global News Chat với hybrid search và citations.
- [ ] Xây dựng Content Strategy Agent và bộ sinh nội dung đa nền tảng.
- [ ] Xây dựng pipeline TTS, subtitle và video rendering.
- [ ] Bổ sung monitoring, tracing, test và CI/CD.

## Airflow scheduler

Hướng dẫn cấu hình và chạy Airflow cho crawler Step 1 nằm tại
[`docs/airflow.md`](docs/airflow.md).

## License

Dự án được phát hành theo [MIT License](LICENSE).
