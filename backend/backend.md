# Tài liệu Kỹ thuật & Vận hành Backend: Data Ingestion Pipeline & Vector Database

Tài liệu này mô tả chi tiết cách cài đặt, cấu hình, vận hành và kiến trúc mã nguồn của phân hệ **Backend** (`E:\A\rag-enterprice-system\backend`) cho giai đoạn:

**Knowledge Base / Source Documents -> Data Ingestion Pipeline -> Vector Database (MongoDB Dual-Mode)**

---

## Mục lục

1. [Tổng quan hệ thống & Kiến trúc](#1-tổng-quan-hệ-thống--kiến-trúc)
2. [Yêu cầu môi trường & Hướng dẫn Setup từng bước](#2-yêu-cầu-môi-trường--hướng-dẫn-setup-từng-bước)
3. [Hướng dẫn Chạy hệ thống & Sử dụng (Operations Guide)](#3-hướng-dẫn-chạy-hệ-thống--sử-dụng-operations-guide)
4. [Cây thư mục & Giải thích chi tiết từng thành phần và đoạn code](#4-cây-thư-mục--giải-thích-chi-tiết-từng-thành-phần-và-đoạn-code)
5. [Cơ chế Bảo mật & Cô lập dữ liệu theo phòng ban](#5-cơ-chế-bảo-mật--cô-lập-dữ-liệu-theo-phòng-ban)
6. [Giải thích Bộ kiểm thử (`backend/tests/`)](#6-giải-thích-bộ-kiểm-thử-backendtests)
7. [Xử lý sự cố thường gặp & Điểm nối giai đoạn tiếp theo](#7-xử-lý-sự-cố-thường-gặp--điểm-nối-giai-đoạn-tiếp-theo)

---

## 1. Tổng quan hệ thống & Kiến trúc

Phân hệ Backend chịu trách nhiệm tiếp nhận tài liệu doanh nghiệp (`PDF`, `DOCX`, `MD`, `TXT`), quản lý phân cấp lưu trữ kèm nhãn phân quyền (`.metadata.json` sidecar), làm sạch và cắt đoạn (chunking), làm giàu ngữ cảnh (Contextual Retrieval), tạo vector ngữ nghĩa (Google Gemini Embedding) cùng chỉ mục từ khóa BM25, và lưu trữ đồng bộ vào MongoDB.

### Sơ đồ luồng dữ liệu tổng thể

```mermaid
flowchart LR
    UP["Upload API / CLI / Sync"] --> P1["Phase 1: KnowledgeBaseStore\nLuu file + tinh SHA-256\n+ ghi .metadata.json sidecar"]
    P1 --> P2["Phase 2: Sidecar Safeguard\nKiem tra ton tai & schema\nKhong hop le -> Fail-Closed -> DLQ"]
    P2 --> LD["1. Load & Clean\nPDF / DOCX / MD / TXT\nUnicode NFC + khu header/footer"]
    LD --> CH["2. Chunking Engine\nRecursive mac dinh\nhoac Parent-Child / Semantic"]
    CH --> EN["3. Contextual Enrichment\nheader prefix hoac LLM summary\n+ gan tenant_id, department"]
    EN --> EM["4. Embedding & Sparse Index\nGemini Bi-Encoder L2-norm\n+ SparseBM25Index"]
    EM --> MDB[("MongoDB Dual-Mode\ncollections: documents,\nchunks, parent_chunks,\ningestion_jobs, dlq_events")]
```

### Ánh xạ nguyên lý thiết kế từ tài liệu tham khảo

| Tài liệu nguồn | Nguyên lý áp dụng | Thành phần thực thi trong `backend/src/` |
| :--- | :--- | :--- |
| **AWS Multi-Tenant RAG** (`Secure_multi_tenant_RAG_with_Amazon_Bedrock_and_Verified_Permissions.docx`) | Shared KB + Logical Isolation theo phòng ban; Two-phase ingestion với `.metadata.json` sidecar safeguard; Dead-Letter Queue (DLQ) | `storage/kb_store.py`, `schemas/document.py`, `ingestion/pipeline.py`, `vectordb/mongodb_store.py` |
| **AI VIET NAM RAG Tutorial** (`RAG_Tutorial_AI_VIET_NAM_114_pages.pdf`) | Document Loading + Metadata; Recursive / Semantic / Parent-Child (Small-to-Big); chuẩn bị sẵn BM25 cho Hybrid Search; cân chỉnh độ chính xác tìm kiếm | `ingestion/loaders/*`, `ingestion/chunkers/*`, `ingestion/sparse_indexer.py`, `vectordb/mongodb_store.py` |
| **RAG Architectures 2025** (`RAG_Architectures_A_Complete_Guide_for_2025.pdf`) | 4 bước Offline Indexing: Extract & Clean -> Chunking -> Dense Bi-Encoder -> Metadata & Contextual Retrieval; Vector DB lưu vector kèm full payload | `ingestion/cleaner.py`, `ingestion/enricher.py`, `ingestion/embedders/gemini_embedder.py`, `schemas/chunk.py` |

---

## 2. Yêu cầu môi trường & Hướng dẫn Setup từng bước

### 2.1. Yêu cầu tiên quyết

1. **Python 3.12** (khuyên dùng **Python 3.12.16** có sẵn trong Anaconda tại `D:\anaconda3\envs\hand_env\python.exe`).
   - *Lưu ý quan trọng:* Không dùng Python 3.14 (`D:\anaconda3\python.exe` bản base) vì một số thư viện xử lý PDF/AI thường thiếu wheel biên dịch sẵn hoặc gây lỗi tương thích với phiên bản mới.
2. **Docker Desktop & MongoDB** (đang chạy container `mongo:latest` tại cổng `27017` theo cấu hình `D:\MongoDB\docker-compose.yml`).
3. **Google Gemini API Key** (tạo tại Google AI Studio) nếu chạy embedding thật (`EMBEDDING_PROVIDER=gemini`). Nếu chỉ chạy test/demo offline có thể đổi sang `EMBEDDING_PROVIDER=mock`.

### 2.2. Cài đặt môi trường Python (Windows PowerShell)

#### Cách A: Dùng môi trường ảo `.venv` đã liên kết với Python 3.12 của Anaconda (Mặc định của dự án)

Nếu trên máy mới chưa có `backend\.venv`, chạy lần lượt các lệnh sau:

```powershell
# 1. Di chuyển vào thư mục backend
cd E:\A\rag-enterprice-system\backend

# 2. Tạo virtual environment cô lập từ Python 3.12 của Anaconda
D:\anaconda3\envs\hand_env\python.exe -m venv .venv

# 3. Cài đặt toàn bộ thư viện
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> Lưu ý: Tệp `backend\.venv\pyvenv.cfg` đặt `include-system-site-packages = false`, nghĩa là các gói cài trong `.venv` **tách biệt hoàn toàn**, không làm thay đổi môi trường `hand_env` hay `base` của Anaconda.

#### Cách B: Dùng Conda env riêng biệt (tùy chọn nếu triển khai trên máy khác)

```powershell
conda create -n rag-enterprise python=3.12 -y
conda activate rag-enterprise
cd E:\A\rag-enterprice-system\backend
pip install -r requirements.txt
```

### 2.3. Thiết lập tệp cấu hình `.env`

Hệ thống nạp biến môi trường theo thứ tự ưu tiên: `backend/.env` ghi đè `E:\A\rag-enterprice-system\.env` (nếu thiếu ở `backend/.env`, tự động đọc fallback từ thư mục gốc dự án).

```powershell
# Sao chép file mẫu vào backend/.env
Copy-Item E:\A\rag-enterprice-system\backend\.env.example E:\A\rag-enterprice-system\backend\.env
```

Sau đó mở `backend/.env` và điền `GEMINI_API_KEY`:

```dotenv
GEMINI_API_KEY=AIzaSy...key_cua_ban...
EMBEDDING_PROVIDER=gemini
```

### 2.4. Bảng giải thích toàn bộ biến môi trường (`backend/.env.example`)

| Biến môi trường | Mặc định | Ý nghĩa & lựa chọn |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | `""` | API key Google Gemini để tạo embedding và tóm tắt ngữ cảnh (khi bật `CONTEXTUAL_MODE=llm`). |
| `EMBEDDING_PROVIDER` | `gemini` | `gemini` (dùng Google Gemini API) hoặc `mock` (dùng `MockEmbedder` offline không tốn quota). |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Tên model embedding của Google Gemini. |
| `GEMINI_EMBEDDING_DIM` | `768` | Số chiều vector (`64`–`3072`). Mặc định `768` cân bằng tốt giữa độ chính xác và dung lượng RAM/DB. |
| `GEMINI_CONTEXT_MODEL` | `gemini-2.0-flash` | Model Gemini dùng để sinh câu tóm tắt ngữ cảnh khi `CONTEXTUAL_MODE=llm`. |
| `MONGODB_URI` | `mongodb://admin:password123@localhost:27017/?authSource=admin` | Chuỗi kết nối MongoDB. Mặc định khớp với container Docker tại `D:\MongoDB`. |
| `MONGODB_DB_NAME` | `rag_enterprise` | Tên database chứa 5 collections của hệ thống. |
| `MONGODB_VECTOR_MODE` | `auto` | `auto` (tự phát hiện Community hay Atlas), `community` (compound pre-filter + NumPy cosine), `atlas` (bắt buộc `$vectorSearch` HNSW). |
| `STORAGE_DIR` | `storage` | Thư mục lưu KB, DLQ, cache BM25 (tương đối theo `backend/` hoặc đường dẫn tuyệt đối). |
| `DEFAULT_TENANT_ID` | `default-org` | Mã tenant mặc định khi upload không truyền `tenant_id`. |
| `MAX_FILE_SIZE_MB` | `50` | Giới hạn kích thước mỗi file upload (`1`–`500` MB). |
| `CHUNKING_STRATEGY` | `recursive` | Chiến lược cắt văn bản: `recursive` \| `parent_child` \| `semantic`. |
| `CHUNK_SIZE_TOKENS` | `400` | Số token tối đa mỗi chunk (cho `recursive` và trần tối đa của `semantic`). |
| `CHUNK_OVERLAP_TOKENS` | `80` | Số token gối đầu giữa 2 chunk liên tiếp (~20% của `400`). |
| `PARENT_CHUNK_SIZE_TOKENS` | `1000` | Kích thước Parent chunk khi chọn `CHUNKING_STRATEGY=parent_child`. |
| `PARENT_CHUNK_OVERLAP_TOKENS` | `100` | Độ gối đầu giữa các Parent chunk. |
| `CHILD_CHUNK_SIZE_TOKENS` | `250` | Kích thước Child chunk dùng để embed & tìm kiếm khi chọn `parent_child`. |
| `CHILD_CHUNK_OVERLAP_TOKENS` | `50` | Độ gối đầu giữa các Child chunk. |
| `SEMANTIC_BREAKPOINT_PERCENTILE` | `20.0` | Phân vị ngưỡng similarity để tách đoạn khi chọn `CHUNKING_STRATEGY=semantic` (ví dụ 20% điểm tương đồng thấp nhất sẽ bị ngắt). |
| `CONTEXTUAL_MODE` | `header` | `header` (ghép tiền tố metadata miễn phí) hoặc `llm` (dùng Gemini tóm tắt ngữ cảnh trước khi embed). |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Danh sách origin được phép gọi API (phân cách bằng dấu phẩy). |

### 2.5. Thiết lập MongoDB (Chế độ hiện tại vs. Nâng cấp Atlas Local)

1. **Chế độ mặc định — Dùng container `D:\MongoDB` (`mongo:latest`, cổng `27017`):**
   - Đảm bảo container `mongodb-server` đang chạy:
     ```powershell
     cd D:\MongoDB
     docker compose up -d
     ```
   - Với `MONGODB_VECTOR_MODE=auto`, `MongoDBVectorStore` tự động phát hiện đây là MongoDB Community và chạy chế độ **`community`**: dùng MongoDB Compound Index để lọc trước theo `tenant_id` / `department` / `enabled`, sau đó tính Cosine Similarity bằng NumPy.

2. **Chế độ nâng cấp tương lai — Dùng MongoDB Atlas Local (`$vectorSearch` HNSW + `$search` BM25):**
   - Khi lượng dữ liệu lên hàng trăm nghìn chunks và muốn dùng native HNSW, khởi chạy tệp `backend/docker-compose.atlas.yml` (chạy cổng `27018:27017` để không xung đột cổng `27017` cũ):
     ```powershell
     cd E:\A\rag-enterprice-system\backend
     docker compose -f docker-compose.atlas.yml up -d
     ```
   - Sau đó cập nhật `MONGODB_URI` trong `backend/.env`:
     ```dotenv
     MONGODB_URI=mongodb://admin:password123@localhost:27018/?authSource=admin&directConnection=true
     MONGODB_VECTOR_MODE=auto
     ```

---

## 3. Hướng dẫn Chạy hệ thống & Sử dụng (Operations Guide)

### 3.1. Khởi chạy FastAPI Backend Server

```powershell
cd E:\A\rag-enterprice-system\backend
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

- Tài liệu API tương tác (Swagger UI): `http://localhost:8000/docs`
- Kiểm tra nhanh sức khỏe: `http://localhost:8000/api/v1/health`

### 3.2. Kết nối với Frontend (`frontend/`)

1. Mở `E:\A\rag-enterprice-system\frontend\.env.example` làm mẫu và tạo `E:\A\rag-enterprice-system\frontend\.env`:
   ```dotenv
   VITE_USE_MOCK=false
   VITE_API_BASE_URL=http://localhost:8000/api/v1
   ```
2. Chạy frontend:
   ```powershell
   cd E:\A\rag-enterprice-system\frontend
   npm install
   npm run dev
   ```
   *(Lưu ý: ở giai đoạn hiện tại, backend đã cung cấp đủ các API quản lý & nạp tài liệu `/documents`, `/documents/upload`, `/documents/{id}` khớp với `frontend/src/api/ragClient.ts`; endpoint `/api/v1/query` sẽ được bổ sung ở giai đoạn Retrieval & Generation tiếp theo).*

### 3.3. Danh sách REST API Endpoints

#### 1) `GET /api/v1/health` — Kiểm tra trạng thái hệ thống & MongoDB
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -Method Get
```
Kết quả mẫu:
```json
{
  "status": "ok",
  "embedding_provider": "gemini",
  "chunking_strategy": "recursive",
  "contextual_mode": "header",
  "vectordb": {
    "ok": true,
    "backend": "mongodb",
    "database": "rag_enterprise",
    "vector_mode": "community"
  },
  "stats": {
    "backend": "mongodb",
    "database": "rag_enterprise",
    "vector_mode": "community",
    "documents": 3,
    "chunks": 142,
    "parent_chunks": 0,
    "dlq_events": 0,
    "chunks_by_department": {
      "dept-it": 142
    }
  }
}
```

#### 2) `POST /api/v1/documents/upload` — Nạp tài liệu mới (Multipart FormData)
Các trường form:
- `file` *(bắt buộc)*: file `.pdf`, `.docx`, `.md`, hoặc `.txt`.
- `category` *(mặc định `"Kỹ thuật & IT"`)*: `"Nhân sự"`, `"Vận hành"`, `"Kỹ thuật & IT"`, hoặc tên tùy chỉnh.
- `tenant_id` *(tùy chọn)*: mặc định lấy `DEFAULT_TENANT_ID`.
- `department` *(tùy chọn)*: ghi đè mã phòng ban (nếu bỏ trống sẽ tự suy ra từ `category`).
- `access_groups` *(tùy chọn)*: danh sách nhóm quyền phân cách dấu phẩy, ví dụ `"dept-it,admin"`.

Ví dụ gọi bằng `curl.exe` trên Windows:
```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/upload" `
  -F "file=@E:\A\rag-enterprice-system\RAG_Architectures_A_Complete_Guide_for_2025.pdf" `
  -F "category=Kỹ thuật & IT"
```

#### 3) `GET /api/v1/documents` — Lấy danh sách tài liệu
Hỗ trợ query params tùy chọn `?tenant_id=...&department=...`.
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/documents" -Method Get
```
Response trả về mảng `DocumentItem` có các khóa camelCase (`sizeLabel`, `chunkCount`, `updatedAt`, `status`, `enabled`, ...) khớp với `frontend/src/types/rag.ts`.

#### 4) `GET /api/v1/documents/{document_id}` & `GET /api/v1/documents/{document_id}/chunks`
- Xem chi tiết một tài liệu hoặc kiểm tra toàn bộ các chunk, trang (`page`), mục (`section`), `contextual_content`, `highlight` đã được index của tài liệu đó (không trả kèm mảng vector `embedding` để nhẹ payload).

#### 5) `PATCH /api/v1/documents/{document_id}` — Bật/tắt tài liệu khỏi kết quả tìm kiếm
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/documents/doc-1234567890ab" `
  -Method Patch `
  -ContentType "application/json" `
  -Body '{"enabled": false}'
```
Thao tác này cập nhật đồng bộ cả collection `documents`, mọi chunk trong collection `chunks`, và chỉ mục `SparseBM25Index`.

#### 6) `DELETE /api/v1/documents/{document_id}` — Xóa hoàn toàn tài liệu
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/documents/doc-1234567890ab" -Method Delete
```
Xóa sạch: tệp gốc + `.metadata.json` trong `storage/knowledge_base/`, toàn bộ bản ghi trong `documents`, `chunks`, `parent_chunks` trên MongoDB, và xóa khỏi BM25 index.

#### 7) `POST /api/v1/ingestion/sync`, `GET /api/v1/ingestion/jobs`, `GET /api/v1/ingestion/dlq`
- `POST /api/v1/ingestion/sync?force=false`: quét toàn bộ thư mục `storage/knowledge_base/`, xác thực sidecar từng tệp (Phase 2 Safeguard) và chỉ index những tệp mới hoặc có `content_hash` thay đổi.
- `GET /api/v1/ingestion/jobs`: xem lịch sử các phiên batch sync.
- `GET /api/v1/ingestion/dlq`: xem các tệp bị chặn hoặc lỗi trong quá trình ingest.

### 3.4. Sử dụng công cụ dòng lệnh (CLI)

Chạy từ thư mục `E:\A\rag-enterprice-system\backend`:

```powershell
# 1. Nạp một hoặc nhiều file vào MongoDB (dùng cấu hình .env)
.\.venv\Scripts\python.exe -m src.ingestion.cli ingest `
  "..\RAG_Tutorial_AI_VIET_NAM_114_pages.pdf" `
  "..\RAG_Architectures_A_Complete_Guide_for_2025.pdf" `
  "..\Secure_multi_tenant_RAG_with_Amazon_Bedrock_and_Verified_Permissions.docx" `
  --category "Kỹ thuật & IT"

# 2. Chạy Phase 2 batch sync toàn bộ Knowledge Base (bỏ qua file không đổi)
.\.venv\Scripts\python.exe -m src.ingestion.cli sync

# 3. Ép re-ingest lại toàn bộ (hữu ích khi đổi CHUNKING_STRATEGY hoặc model embedding)
.\.venv\Scripts\python.exe -m src.ingestion.cli sync --force

# 4. Xem thống kê Vector DB
.\.venv\Scripts\python.exe -m src.ingestion.cli stats

# 5. Chạy thử hoàn toàn bằng RAM (InMemoryVectorStore, không chạm MongoDB)
.\.venv\Scripts\python.exe -m src.ingestion.cli --memory ingest "..\README.md" --category "Vận hành"
```

---

## 4. Cây thư mục & Giải thích chi tiết từng thành phần và đoạn code

```text
backend/
├── .env.example                        # Mẫu biến môi trường
├── docker-compose.atlas.yml            # Container MongoDB Atlas Local (nâng cấp tùy chọn)
├── pyproject.toml                      # Cấu hình project & pytest
├── requirements.txt                    # Danh sách thư viện Python 3.12
├── backend.md                          # Tài liệu hướng dẫn hiện tại
├── storage/                            # Dữ liệu runtime (đã thêm vào .gitignore)
│   ├── knowledge_base/                 # Kho tài liệu phân cấp {tenant}/{dept}/{doc_id}/
│   ├── dlq/                            # Bản ghi JSON các file lỗi safeguard/ingest
│   └── bm25/index.json                 # Chỉ mục từ khóa BM25 đồng bộ theo document_id
├── src/
│   ├── main.py                         # Khởi tạo FastAPI app, lifespan & CORS
│   ├── config/settings.py              # Pydantic Settings & hàm ánh xạ phòng ban
│   ├── schemas/
│   │   ├── document.py                 # DocumentItem, MetadataSidecar, MetadataAttributes
│   │   └── chunk.py                    # ChunkRecord, ParentChunk, SearchFilter, DLQRecord...
│   ├── storage/kb_store.py             # KnowledgeBaseStore (Phase 1 Staging + Phase 2 Safeguard)
│   ├── ingestion/
│   │   ├── loaders/                    # PdfLoader, DocxLoader, TextLoader
│   │   ├── cleaner.py                  # TextCleaner (NFC tiếng Việt + khử header/footer lặp)
│   │   ├── chunkers/                   # RecursiveChunker, ParentChildChunker, SemanticChunker
│   │   ├── enricher.py                 # ChunkEnricher (header / llm Contextual Retrieval)
│   │   ├── embedders/                  # GeminiEmbedder & MockEmbedder
│   │   ├── sparse_indexer.py           # SparseBM25Index
│   │   ├── pipeline.py                 # IngestionPipeline orchestrator
│   │   └── cli.py                      # CLI runner
│   ├── vectordb/
│   │   ├── base.py                     # VectorStore ABC & fail-closed is_filter_authorized()
│   │   ├── mongodb_store.py            # MongoDBVectorStore (Dual-Mode community / atlas)
│   │   └── memory_store.py             # InMemoryVectorStore dùng cho unit test
│   └── api/
│       ├── deps.py                     # Dependency injection (AppServices)
│       └── routes/                     # health.py, documents.py, ingestion.py
└── tests/                              # 5 file test (14 test cases)
```

---

### 4.1. Cấu hình & Ánh xạ phòng ban (`src/config/settings.py`)

**Chức năng:** Quản lý toàn bộ tham số chạy bằng Pydantic v2 `BaseSettings`, tự đọc `backend/.env` hoặc fallback về `.env` ở thư mục gốc. Đồng thời quy chuẩn hóa danh mục hiển thị tiếng Việt sang mã phòng ban ổn định để phân tách thư mục lưu trữ và lọc vector.

```python
CATEGORY_DEPARTMENT_MAP: dict[str, str] = {
    "Nhân sự": "dept-hr",
    "Vận hành": "dept-ops",
    "Kỹ thuật & IT": "dept-it",
}

def category_to_department(category: str) -> str:
    clean = unicodedata.normalize("NFC", category.strip())
    if clean in CATEGORY_DEPARTMENT_MAP:
        return CATEGORY_DEPARTMENT_MAP[clean]
    ascii_slug = (
        unicodedata.normalize("NFD", clean)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_slug).strip("-")
    return f"dept-{slug}" if slug else "dept-general"
```
- **Giải thích hoạt động:**
  - Nếu người dùng chọn 1 trong 3 danh mục chuẩn trên UI (`Nhân sự`, `Vận hành`, `Kỹ thuật & IT`), hệ thống ánh xạ thẳng sang `dept-hr`, `dept-ops`, `dept-it`.
  - Nếu có danh mục mới (ví dụ `"Pháp chế"`), hàm tự loại dấu tiếng Việt (NFD -> ASCII) và tạo slug an toàn `dept-phap-che` dùng làm tên thư mục và metadata tag mà không cần sửa code.

---

### 4.2. Schema dữ liệu (`src/schemas/document.py`, `src/schemas/chunk.py`)

**Chức năng:** Định nghĩa hợp đồng dữ liệu thống nhất giữa Frontend, Sidecar JSON, Ingestion Pipeline và MongoDB.

- **`DocumentItem` & `ChunkRecord`:** Sử dụng `alias` và `serialization_alias` của Pydantic v2 (`size_label` -> `sizeLabel`, `chunk_count` -> `chunkCount`, `updated_at` -> `updatedAt`, `document_id` -> `documentId`, `chunk_index` -> `chunkIndex`). Nhờ đó code Python dùng `snake_case` chuẩn PEP 8, còn API trả JSON `camelCase` khớp trực tiếp với TypeScript interface trong `frontend/src/types/rag.ts`.
- **`MetadataSidecar`:** Mô phỏng cấu trúc `.metadata.json` của Amazon Bedrock Knowledge Bases:
  ```json
  {
    "metadataAttributes": {
      "tenant_id": "default-org",
      "department": "dept-it",
      "category": "Kỹ thuật & IT",
      "access_groups": ["dept-it", "admin"],
      "document_id": "doc-a1b2c3d4e5f6",
      "title": "RAG Architectures 2025",
      "format": "PDF",
      "content_hash": "sha256...",
      "version": 1,
      "updated_at": "2026-11-24T11:30:00+00:00"
    }
  }
  ```

---

### 4.3. Knowledge Base Storage & Two-Phase Sidecar Safeguard (`src/storage/kb_store.py`)

**Chức năng:** Giải quyết rủi ro **ingestion race condition** được cảnh báo trong tài liệu AWS Multi-Tenant RAG: tuyệt đối không cho phép tài liệu nào được index vào Vector DB nếu chưa có tệp `.metadata.json` hợp lệ.

- **Phase 1 (`stage_document`):**
  1. Kiểm tra định dạng hợp lệ (`.pdf`, `.docx`, `.md`, `.markdown`, `.txt`) và giới hạn dung lượng.
  2. Tính `sha256` của byte nội dung (`compute_sha256`).
  3. Lưu tệp nguồn tại `storage/knowledge_base/{tenant_id}/{department}/{doc_id}/{safe_filename}`.
  4. Ghi tệp `<filename>.metadata.json` bằng kỹ thuật **atomic write** (ghi vào file `.tmp` rồi `replace()`) để tránh sidecar bị ghi dở dang nếu mất điện/crash.

- **Phase 2 (`validate_sidecar` — Fail-Closed Safeguard):**
  ```python
  if not sidecar_path.exists():
      raise SidecarValidationError(
          f"Missing required metadata sidecar '{sidecar_path.name}' for '{file_path.name}'."
      )
  ...
  if len(rel_parts) >= 4:
      folder_tenant, folder_dept = rel_parts[0], rel_parts[1]
      attrs = sidecar.metadataAttributes
      if folder_tenant != attrs.tenant_id:
          raise SidecarValidationError(...)
      if folder_dept != attrs.department:
          raise SidecarValidationError(...)
  ```
  - **Cơ chế hoạt động:** Dù tài liệu đến từ Upload API hay bị chép thủ công vào thư mục `knowledge_base/` rồi chạy `sync`, hàm `validate_sidecar()` luôn kiểm tra: (1) file sidecar tồn tại, (2) JSON đúng schema `MetadataSidecar`, (3) `tenant_id` và `department` trong sidecar khớp với đường dẫn thư mục chứa file. Nếu sai bất kỳ điều kiện nào, pipeline **chặn index ngay lập tức** và ghi bản ghi lỗi vào `storage/dlq/` + MongoDB `dlq_events`.

---

### 4.4. Document Loaders & Text Cleaner (`src/ingestion/loaders/`, `src/ingestion/cleaner.py`)

**Chức năng:** Chuyển đổi các định dạng tệp thô thành `ExtractedDocument` gồm danh sách `ExtractedPage(page_number, section, text)` sạch nhiễu trước khi chunk.

1. **`PdfLoader` (`pdf_loader.py`):**
   - Dùng `pymupdf` (cực nhanh, giữ tiếng Việt chuẩn) và fallback sang `pypdf` nếu thiếu.
   - Đọc từng trang (đánh số 1-based), dùng regex `HEADING_LINE_RE` nhận diện các dòng tiêu đề mục (`I.`, `1.2.`, `Chương`, `Step`, `Section`) để gán ngữ cảnh `section` cho các trang tiếp theo.
2. **`DocxLoader` (`docx_loader.py`):**
   - Duyệt trực tiếp con của `doc.element.body.iterchildren()` để phân biệt `CT_P` (đoạn văn / heading) và `CT_Tbl` (bảng biểu) **theo đúng thứ tự xuất hiện trong tài liệu** (thay vì đọc riêng `doc.paragraphs` và `doc.tables` làm mất vị trí bảng).
   - Các bảng biểu được hàm `_table_to_markdown()` chuyển thành bảng Markdown chuẩn (`| col1 | col2 |`), giữ trọn vẹn cấu trúc cột/hàng khi đưa vào chunk.
3. **`TextLoader` (`text_loader.py`):**
   - Đọc UTF-8; với file Markdown (`.md`), tách theo heading `#`..`######` (bỏ qua các dòng `#` nằm trong block code ```` ``` ````).
4. **`TextCleaner` (`cleaner.py`):**
   - Chuẩn hóa toàn bộ văn bản về **Unicode NFC** (`unicodedata.normalize("NFC", text)`): khắc phục lỗi dấu tiếng Việt tách rời (NFD) rất hay gặp khi trích xuất từ PDF.
   - Nối lại các từ bị gạch ngang ngắt dòng (`(\w)-\n(\w)`), loại bỏ ký tự điều khiển vô hình (`\u200b`, `\ufeff`).
   - `_strip_repeated_headers_footers()`: với PDF có từ 3 trang trở lên, đếm các dòng xuất hiện ở 2 dòng đầu/2 dòng cuối trang. Dòng nào lặp lại ở `>= 60%` số trang hoặc chỉ là số trang (`Page 3/10`, `Trang 5`) sẽ bị cắt bỏ để không làm nhiễu embedding.

---

### 4.5. Chunking Engine (`src/ingestion/chunkers/`)

**Chức năng:** Chia văn bản đã làm sạch thành các đoạn kích thước tối ưu dựa trên biến `CHUNKING_STRATEGY`.

1. **Bộ đếm token (`chunkers/base.py`):**
   - Dùng `tiktoken.get_encoding("cl100k_base")`, đồng thời có **offline regex fallback** (`FALLBACK_TOKEN_RE`) trong trường hợp môi trường chạy chưa có cache BPE của `tiktoken` và bị ngắt internet.
2. **`RecursiveChunker` (`recursive.py` — Mặc định):**
   - Tách phân cấp theo thứ tự ưu tiên giữ trọn vẹn ý nghĩa: `"\n\n"` -> `"\n"` -> `". "` -> `"? "` -> `"! "` -> `"; "` -> `", "` -> `" "`.
   - Khi ghép các mảnh vào chunk đạt ngưỡng `chunk_size=400` tokens, hàm `_merge_pieces_with_overlap()` tự lấy ngược các mảnh cuối sao cho tổng đạt xấp xỉ `chunk_overlap=80` tokens (20%) làm "cầu nối" sang chunk kế tiếp.
3. **`ParentChildChunker` (`parent_child.py` — Small-to-Big):**
   - Cắt mỗi trang thành các **ParentChunk** lớn (`1000` tokens, overlap `100`) lưu vào collection `parent_chunks`.
   - Cắt tiếp từng Parent thành nhiều **ChildChunk** nhỏ (`250` tokens, overlap `50`) gắn `parent_id` tương ứng để lưu vào `chunks` và embed.
   - Khi truy vấn sau này, hệ thống tìm chính xác trên ChildChunk nhỏ, rồi tra `parent_id` lấy ParentChunk giàu ngữ cảnh đưa cho LLM.
4. **`SemanticChunker` (`semantic.py` — Tùy chọn):**
   - Tách trang thành danh sách câu, gọi `embedder.embed_texts(sentences, task_type="SEMANTIC_SIMILARITY")` theo batch, tính tích vô hướng (cosine similarity vì vector đã L2-normalize) giữa từng cặp câu liên tiếp.
   - Tìm ngưỡng phân vị `np.percentile(sims, 20.0)`: nơi nào độ tương đồng tụt xuống dưới ngưỡng hoặc vượt `max_chunk_tokens` thì ngắt sang chunk mới, kèm cầu nối 1 câu ở ranh giới.

---

### 4.6. Metadata Enrichment & Contextual Retrieval (`src/ingestion/enricher.py`)

**Chức năng:** Làm giàu từng chunk trước khi đưa qua model embedding để một đoạn văn khi đứng tách rời vẫn giữ được bối cảnh tài liệu.

- **Tạo `chunk_id` xác định:** `uuid5(NAMESPACE_URL, f"{document_id}:{content_hash}:{chunk_index}")`, giúp quá trình upsert/re-ingest luôn an toàn, không sinh ID ngẫu nhiên trùng lặp.
- **2 chế độ Contextual Retrieval:**
  - `CONTEXTUAL_MODE=header` *(mặc định)*: ghép tiền tố cấu trúc vào trường `contextual_content` (dùng để embed), trong khi giữ nguyên `content` sạch để hiển thị trích dẫn:
    ```text
    [Tài liệu: Chính sách bảo mật | Danh mục: Kỹ thuật & IT | Phòng ban: dept-it | Mục: Mục 2 | Trang: 3]
    <Nội dung gốc của chunk>
    ```
  - `CONTEXTUAL_MODE=llm`: gọi model Gemini (`GEMINI_CONTEXT_MODEL`, mặc định `gemini-2.0-flash`) sinh 1–2 câu tóm tắt vai trò của đoạn trích trong toàn bộ tài liệu (Anthropic Contextual Retrieval). Nếu API key trống hoặc gọi LLM lỗi, tự động fallback an toàn về chế độ `header`.

---

### 4.7. Embedding & Sparse BM25 Index (`src/ingestion/embedders/`, `src/ingestion/sparse_indexer.py`)

1. **`GeminiEmbedder` (`gemini_embedder.py`):**
   - Sử dụng SDK `google-genai` (`google.genai.Client`), gọi `models.embed_content` theo từng batch 50 chunks với `task_type="RETRIEVAL_DOCUMENT"` lúc ingest (và `"RETRIEVAL_QUERY"` lúc tìm kiếm) cùng `output_dimensionality=768`.
   - Có cơ chế retry với **exponential backoff** (`1s -> 2s -> 4s`) nếu gặp rate limit tạm thời, và luôn gọi `l2_normalize()` để mọi vector có chuẩn độ dài bằng `1.0` (tích vô hướng = Cosine Similarity).
2. **`MockEmbedder` (`embedders/base.py`):**
   - Băm unigram + character trigram bằng `blake2b` thành vector L2-normalized có chiều tùy chỉnh — giúp toàn bộ test chạy tức thì offline mà vẫn giữ được độ tương đồng từ khóa cơ bản.
3. **`SparseBM25Index` (`sparse_indexer.py`):**
   - Hàm `tokenize_for_bm25()` giữ nguyên các mã kỹ thuật (`sev-1`, `error`, `503`) và lưu song song cả token tiếng Việt có dấu lẫn không dấu để hỗ trợ tìm kiếm chính xác từ khóa (chuẩn bị cho Hybrid Search + RRF ở giai đoạn tiếp theo).
   - Đồng bộ tự động theo `document_id` (khi cập nhật, bật/tắt `enabled`, hoặc xóa tài liệu) và lưu xuống `storage/bm25/index.json` bằng atomic write.

---

### 4.8. MongoDB Dual-Mode Vector Store (`src/vectordb/mongodb_store.py`)

**Chức năng:** Lưu trữ hợp nhất cả Metadata, Parent Chunks, Dense Vectors và Job/DLQ Audit Logs trong cùng database `rag_enterprise`.

#### Thiết kế 5 Collections trong MongoDB

| Collection | Mục đích | Indexes được tạo tự động |
| :--- | :--- | :--- |
| `documents` | Lưu `DocumentItem` (trạng thái, `chunkCount`, `content_hash`, `tenant_id`, `department`, `enabled`) | Unique `id`; Compound `(tenant_id, department, updated_at)` |
| `parent_chunks` | Lưu `ParentChunk` cho chế độ `parent_child` | Unique `parent_id`; Compound `(document_id, chunk_index)` |
| `chunks` | Lưu `ChunkRecord` kèm mảng `embedding` (`float[768]`) và metadata phân quyền | Unique `id`; Compound `idx_isolation_prefilter(tenant_id, department, enabled, document_id)`; `idx_access_groups`; `idx_doc_chunk`; Text index `idx_chunks_text(content, section, document_title)` |
| `ingestion_jobs` | Lưu lịch sử các lần chạy `sync` / `cli` | Unique `job_id`; `started_at` |
| `dlq_events` | Lưu sự cố sidecar / parse / embed (Dead-Letter Queue) | Unique `dlq_id`; `created_at` |

#### Cơ chế Dual-Mode (`auto` | `community` | `atlas`)
- Trong `ensure_indexes()`, nếu `MONGODB_VECTOR_MODE` là `auto` hoặc `atlas`, hệ thống gọi `chunks_col.list_search_indexes()` và tạo `chunks_vector_index` (`type="vectorSearch"`, `similarity="cosine"`, kèm 6 trường filter: `tenant_id`, `department`, `category`, `document_id`, `enabled`, `access_groups`) và `chunks_atlas_text_index`.
- Khi kết nối vào container `mongo:latest` ở `D:\MongoDB`, MongoDB trả `OperationFailure` vì không có `mongot`. Chế độ `auto` bắt lỗi này một cách êm ái và chuyển `active_vector_mode = "community"`:
  - **`community` mode (`_community_vector_search`):** Thực thi `chunks_col.find(mongo_filter)` sử dụng compound index `idx_isolation_prefilter` để lọc trước toàn bộ chunk hợp lệ ở tầng DB, rồi nhân ma trận NumPy `mat @ q` tính Cosine Similarity cực nhanh.
  - **`atlas` mode (`_atlas_vector_search`):** Chạy aggregation pipeline `$vectorSearch` với `filter`, `numCandidates` và `limit` ngay trong HNSW engine.

---

### 4.9. Pipeline Orchestrator, API & CLI (`pipeline.py`, `main.py`, `api/`, `cli.py`)

**Chức năng:** Kết nối mọi thành phần thành một vòng đời đồng bộ và an toàn dữ liệu (`IngestionPipeline`):

1. **Chuyển trạng thái minh bạch:** Khi bắt đầu xử lý, lưu `status="chunking"` -> trước khi gọi Gemini Embedder cập nhật `status="embedding"` -> hoàn tất ghi `status="ready"` kèm `chunk_count` và `summary`. Nếu lỗi ở bất kỳ bước nào, cập nhật `status="error"`, lưu `error_message` và đẩy vào DLQ.
2. **Idempotent Re-ingest & Tránh Chunk mồ côi:**
   - Khi chạy `sync`, nếu `document_id` đã ở trạng thái `ready` và `content_hash` (SHA-256) không đổi, pipeline bỏ qua ngay để không tốn chi phí embed lại.
   - Khi cần cập nhật hoặc re-ingest (`force=True`), `replace_document_chunks()` xóa sạch toàn bộ `chunks` và `parent_chunks` cũ của `document_id` đó trước khi chèn bộ chunk mới.
3. **FastAPI Lifespan (`src/main.py`):** Tự động khởi tạo `KnowledgeBaseStore`, `MongoDBVectorStore` (gọi `ensure_indexes()`), `EmbeddingProvider`, `SparseBM25Index` và `IngestionPipeline` vào `app.state.services` ngay khi server khởi động.

---

## 5. Cơ chế Bảo mật & Cô lập dữ liệu theo phòng ban

Áp dụng mô hình **Filter-Level Logical Isolation (Fail-Closed)** từ tài liệu AWS Multi-Tenant RAG, hàm `is_filter_authorized()` trong `src/vectordb/base.py` bắt buộc mọi truy vấn tìm kiếm phải có danh tính hợp lệ:

```mermaid
sequenceDiagram
    participant Caller as Caller / Retrieval Layer
    participant VS as VectorStore (MongoDB / Memory)
    participant DB as MongoDB Collection chunks

    Caller->>VS: vector_search(query_vec, SearchFilter)
    VS->>VS: is_filter_authorized(SearchFilter)
    alt Thieu tenant_id hoac rong ca departments va access_groups
        VS-->>Caller: Tra ve [] ngay lap tuc (Fail-Closed)
    else Filter hop le (vd: tenant=corp-1, departments=[dept-hr])
        VS->>DB: Pre-filter voi idx_isolation_prefilter + enabled=True
        DB-->>VS: Chi cac chunk thuoc corp-1 & dept-hr (loai bo dept-it)
        VS-->>Caller: Top-K ket qua da tinh Cosine Similarity
    end
```

- **Nguyên tắc Fail-Closed:** Nếu middleware hoặc caller truyền `SearchFilter` rỗng (thiếu `tenant_id` hoặc không có `departments`/`access_groups`), hệ thống từ chối truy vấn và trả về `[]` thay vì rò rỉ toàn bộ tài liệu (fail-open).
- **Phạm vi sử dụng:** Thiết kế này tối ưu cho bài toán **phân quyền nhiều phòng ban/nhóm bên trong một tổ chức** (intra-tenant) trên một Vector DB dùng chung để tiết kiệm chi phí hạ tầng. Nếu triển khai SaaS đa khách hàng có yêu cầu tách biệt vật lý tuyệt đối theo luật định giữa các công ty khác nhau, nên tách riêng database/cluster theo từng tenant.

---

## 6. Giải thích Bộ kiểm thử (`backend/tests/`)

Bộ test `pytest` gồm **5 tệp / 14 test cases**, sử dụng `MockEmbedder` và `InMemoryVectorStore` để chạy nhanh, không cần mạng và không tốn quota API:

| Tệp kiểm thử | Số test | Nội dung xác minh |
| :--- | :---: | :--- |
| `tests/test_kb_sidecar_safeguard.py` | 4 | Phase 1 tạo sidecar + Phase 2 thành công; file thiếu `.metadata.json` bị chặn & ghi DLQ; lệch `department` giữa thư mục và sidecar bị chặn; `sync` bỏ qua file không đổi `content_hash`. |
| `tests/test_loaders_and_cleaner.py` | 4 | Chuẩn hóa Unicode NFD -> NFC tiếng Việt + xóa header/footer lặp trên PDF; load `.md`/`.txt`; `DocxLoader` chuyển bảng thành Markdown; đọc thực tế các file PDF/DOCX lớn trong workspace. |
| `tests/test_chunkers.py` | 3 | `RecursiveChunker` giữ ngưỡng token & metadata; `ParentChildChunker` liên kết đúng `parent_id`; `SemanticChunker` tách đoạn theo chuyển dịch ngữ nghĩa. |
| `tests/test_enricher_and_isolation.py` | 2 | Cô lập dữ liệu `dept-hr` vs `dept-it`, fail-closed khi filter rỗng, ẩn tài liệu khi `enabled=False`, xóa sạch khi `DELETE`, và kiểm tra tiền tố ngữ cảnh `header`. |
| `tests/test_api_and_e2e.py` | 1 | Kiểm thử toàn vòng đời FastAPI qua `TestClient`: `/health`, `/documents/upload` (kiểm tra khóa JSON camelCase khớp frontend), `/documents`, `/documents/{id}/chunks`, `PATCH`, `/ingestion/sync`, `DELETE`. |

**Lệnh chạy toàn bộ bộ test:**

```powershell
cd E:\A\rag-enterprice-system\backend
.\.venv\Scripts\python.exe -m pytest tests -v
```

---

## 7. Xử lý sự cố thường gặp & Điểm nối giai đoạn tiếp theo

### 7.1. Xử lý sự cố thường gặp (Troubleshooting)

| Triệu chứng / Lỗi | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| `GEMINI_API_KEY is missing` | Chưa tạo `.env` hoặc chưa điền key khi `EMBEDDING_PROVIDER=gemini` | Điền `GEMINI_API_KEY=...` vào `backend/.env` hoặc đổi `EMBEDDING_PROVIDER=mock` để test offline. |
| `ServerSelectionTimeoutError` / `Authentication failed` khi kết nối MongoDB | Container MongoDB Docker chưa chạy hoặc sai URI/mật khẩu | Kiểm tra `docker ps`, chạy `docker compose up -d` tại `D:\MongoDB`, đối chiếu `MONGODB_URI` trong `backend/.env`. |
| `MONGODB_VECTOR_MODE=atlas requested, but server does not support Atlas Search` | Đang bật ép `atlas` nhưng trỏ vào container `mongo:latest` (Community) | Đổi về `MONGODB_VECTOR_MODE=auto` (hoặc `community`), hoặc chạy `docker-compose.atlas.yml` ở cổng `27018`. |
| Tài liệu bị đẩy vào `storage/dlq/` khi chạy `sync` | Chép thẳng file vào `storage/knowledge_base/...` mà không qua upload/staging nên thiếu `.metadata.json` | Luôn nạp file qua API `/documents/upload` hoặc CLI `ingest` để Phase 1 sinh sidecar hợp lệ trước khi `sync`. |
| Lỗi cài thư viện (`onnxruntime`, `pymupdf`) khi tự tạo lại env | Dùng nhầm Python 3.14 thay vì Python 3.12 | Xóa `.venv` tạo lại bằng `D:\anaconda3\envs\hand_env\python.exe -m venv .venv`. |

### 7.2. Điểm nối sang giai đoạn tiếp theo (Retrieval & Generation)

Hệ thống hiện tại đã chuẩn bị sẵn đầy đủ dữ liệu nền cho giai đoạn truy xuất & sinh câu trả lời:
1. **Hybrid Search + RRF:** Kết hợp `vector_store.vector_search(...)` (Dense Vector) và `bm25_index.search(...)` / `vector_store.keyword_search(...)` (Sparse Keyword), trộn kết quả bằng thuật toán **Reciprocal Rank Fusion (RRF)**.
2. **Small-to-Big Context Expansion:** Nếu ingest với `CHUNKING_STRATEGY=parent_child`, tầng Retrieval dùng `chunk.parent_id` gọi `vector_store.get_parent_chunk(parent_id)` để lấy toàn bộ Parent Chunk đầy đủ ngữ cảnh đưa vào LLM.
3. **API `/api/v1/query`:** Triển khai endpoint `POST /api/v1/query` (nhận `question`, `documentIds`, `topK` theo `frontend/src/types/rag.ts`) với `SearchFilter` bắt buộc theo phòng ban người dùng, sau đó gọi Gemini để sinh câu trả lời kèm danh sách `citations`.
