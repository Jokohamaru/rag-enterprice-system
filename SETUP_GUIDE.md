# Hướng dẫn Cài đặt & Vận hành Hệ thống Enterprise RAG (NotebookLM Edition)

Tài liệu này hướng dẫn từng bước cách cài đặt môi trường, cấu hình AI Model API (Google Gemini / OpenAI / OpenRouter / Groq / Ollama), khởi chạy cơ sở dữ liệu MongoDB, chạy Backend + Frontend, kiểm thử và xử lý sự cố.

> **Lưu ý về đường dẫn:** Toàn bộ câu lệnh dưới đây sử dụng **đường dẫn tương đối** tính từ thư mục gốc của dự án (sau khi bạn clone hoặc giải nén mã nguồn về máy).

---

## 1. Yêu cầu tiên quyết (Prerequisites)

Trước khi bắt đầu, hãy đảm bảo máy tính của bạn đã cài đặt:

1. **Python 3.12** (khuyên dùng **Python 3.12.x**, cài trực tiếp từ [python.org](https://www.python.org/downloads/) hoặc tạo môi trường riêng qua Conda/pyenv).
   - *Lưu ý:* Tránh dùng Python 3.14 bản quá mới vì một số gói xử lý PDF/tính toán số học có thể thiếu wheel biên dịch sẵn trên Windows.
2. **Node.js 18+ (khuyên dùng 20 LTS)** kèm `npm` để chạy và build Frontend React + Vite.
3. **Docker Desktop** (để chạy MongoDB Community hoặc MongoDB Atlas Local).
4. **API Key cho mô hình AI** *(hoặc cài Ollama nếu chạy model nội bộ)*:
   - Google AI Studio API Key (`GEMINI_API_KEY`) nếu dùng Gemini, **hoặc**
   - OpenAI / OpenRouter / Groq / DeepSeek API Key (`LLM_API_KEY`) nếu dùng chuẩn OpenAI-Compatible.

---

## 2. Bước 1 — Khởi chạy Cơ sở dữ liệu MongoDB

Hệ thống sử dụng **MongoDB Dual-Mode** (`auto` tự nhận diện Community hay Atlas Search). Chọn **1 trong 2** cách dưới đây (chạy lệnh từ thư mục gốc dự án):

### Cách A: Dùng MongoDB Community (Mặc định, nhẹ, cổng `27017`)
Khởi chạy nhanh bằng file [backend/docker-compose.yml](backend/docker-compose.yml) đi kèm sẵn trong dự án:

```powershell
cd backend
docker compose up -d
```

Hoặc chạy trực tiếp một container MongoDB bằng Docker CLI:

```powershell
docker run -d --name mongodb-rag `
  -p 27017:27017 `
  -e MONGO_INITDB_ROOT_USERNAME=admin `
  -e MONGO_INITDB_ROOT_PASSWORD=password123 `
  mongo:latest
```

> *Lưu ý:* Nếu máy bạn đã cài đặt sẵn MongoDB cục bộ hoặc dùng MongoDB từ xa (MongoDB Atlas cloud / server riêng), bạn có thể bỏ qua bước Docker và điền trực tiếp chuỗi kết nối cá nhân vào `MONGODB_URI` trong `backend/.env`.

Chuỗi kết nối mặc định tương ứng:
```dotenv
MONGODB_URI=mongodb://admin:password123@localhost:27017/?authSource=admin
MONGODB_VECTOR_MODE=auto
```

### Cách B: Dùng MongoDB Atlas Local (HNSW Vector Search + Full-Text Search, cổng `27018`)
Khi lượng dữ liệu lớn (hàng chục nghìn đến hàng trăm nghìn đoạn văn bản), bạn có thể bật container Atlas Local đi kèm sẵn trong dự án tại [backend/docker-compose.atlas.yml](backend/docker-compose.atlas.yml):

```powershell
cd backend
docker compose -f docker-compose.atlas.yml up -d
```

Chuỗi kết nối tương ứng trong `backend/.env`:
```dotenv
MONGODB_URI=mongodb://admin:password123@localhost:27018/?authSource=admin&directConnection=true
MONGODB_VECTOR_MODE=auto
```

---

## 3. Bước 2 — Cài đặt & Cấu hình Backend (`backend/`)

### 3.1. Tạo Virtual Environment (`.venv`) và cài đặt thư viện

Mở terminal tại thư mục gốc dự án (ví dụ Windows PowerShell) và chạy lần lượt:

```powershell
cd backend

# Tạo môi trường ảo cô lập bằng Python 3.12 (Windows)
py -3.12 -m venv .venv
# (macOS/Linux: python3.12 -m venv .venv — hoặc thay bằng đường dẫn Python 3.12/Conda trên máy bạn)

# Cài đặt toàn bộ phụ thuộc trong requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# (macOS/Linux: ./.venv/bin/python -m pip install -r requirements.txt)
```

> Nếu máy bạn không dùng lệnh `py -3.12` (ví dụ dùng Conda hoặc cài Python ở thư mục tùy chọn), hãy thay `py -3.12` bằng đường dẫn tới `python.exe` (Python 3.12) trên máy bạn, hoặc tạo môi trường trực tiếp bằng `conda create -n rag-enterprise python=3.12 -y`.

### 3.2. Tạo tệp cấu hình `backend/.env`

Sao chép từ file mẫu [backend/.env.example](backend/.env.example) (chạy từ thư mục gốc dự án; nếu đang ở trong `backend/`, dùng `Copy-Item .\.env.example .\.env`):

```powershell
Copy-Item .\backend\.env.example .\backend\.env
# (macOS/Linux: cp backend/.env.example backend/.env)
```

> **Thứ tự nạp `.env`:** Backend đọc từ `./.env` ở thư mục gốc dự án làm nền, sau đó `backend/.env` sẽ **ghi đè** các biến tương ứng (xem `Settings.model_config` trong `backend/src/config/settings.py`).

### 3.3. Chọn cấu hình AI Model API phù hợp

Hệ thống tách độc lập **Model trả lời (`LLM_PROVIDER`)** và **Model tạo vector tìm kiếm (`EMBEDDING_PROVIDER`)**. Hãy mở `backend/.env` và dán **1 trong 4 preset** dưới đây:

#### Preset 1 — Dùng Google Gemini trọn bộ *(Khuyên dùng cho chất lượng tiếng Việt tốt nhất)*
```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...key_cua_ban...
GEMINI_GENERATION_MODEL=gemini-2.5-flash
GEMINI_CONTEXT_MODEL=gemini-2.5-flash-lite

EMBEDDING_PROVIDER=gemini
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_EMBEDDING_DIM=768
```

#### Preset 2 — Gemini trả lời + Mock Embedding *(Tiết kiệm quota embedding khi test/dev)*
```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...key_cua_ban...
GEMINI_GENERATION_MODEL=gemini-2.5-flash

EMBEDDING_PROVIDER=mock
GEMINI_EMBEDDING_DIM=768
```
> *Lưu ý:* Ở Preset 2, AI trả lời câu hỏi, tổng quan và Studio vẫn chạy qua Gemini API thật; chỉ phần tìm kiếm vector dùng `MockEmbedder` (kết hợp BM25 từ khóa).

#### Preset 3 — Dùng OpenAI / OpenRouter / Groq / DeepSeek (`openai_compatible`)
```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-...key_cua_ban...
LLM_MODEL=openai/gpt-4o-mini

# Có thể dùng chung OpenAI/OpenRouter để embed hoặc giữ Gemini/Mock
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...key_cua_ban...
```
*(Nếu dùng trực tiếp OpenAI: đặt `LLM_BASE_URL=https://api.openai.com/v1`, `LLM_MODEL=gpt-4o-mini`; nếu muốn embed bằng OpenAI: `EMBEDDING_PROVIDER=openai_compatible`, `EMBEDDING_MODEL=text-embedding-3-small`).*

#### Preset 4 — Chạy Model nội bộ (Local) qua Ollama *(Không cần API key, bảo mật dữ liệu nội bộ)*
```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=
LLM_MODEL=qwen2.5:14b

EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_MODEL=nomic-embed-text
GEMINI_EMBEDDING_DIM=768
```

### 3.4. Bảng giải thích các biến môi trường quan trọng

| Nhóm | Biến môi trường | Mặc định | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| **LLM** | `LLM_PROVIDER` | `gemini` | `gemini` \| `openai_compatible` \| `none` |
| **LLM** | `LLM_API_KEY` | `""` | API key cho LLM (nếu dùng `gemini` và để trống, tự lấy `GEMINI_API_KEY`) |
| **LLM** | `LLM_BASE_URL` | `https://api.openai.com/v1` | Endpoint gốc chuẩn OpenAI (OpenRouter, Groq, Ollama...) |
| **LLM** | `LLM_MODEL` | `""` | Ghi đè tên model LLM (để trống sẽ lấy `GEMINI_GENERATION_MODEL` hoặc `gpt-4o-mini`) |
| **LLM** | `LLM_TEMPERATURE` | `0.2` | Độ sáng tạo (giữ thấp `0.1–0.3` để AI bám sát nguồn tài liệu) |
| **LLM** | `LLM_MAX_TOKENS` | `2048` | Số token tối đa cho một câu trả lời |
| **LLM** | `LLM_TIMEOUT_SECONDS` | `45.0` | Timeout mỗi request gọi AI API |
| **Embed** | `EMBEDDING_PROVIDER` | `gemini` | `gemini` \| `openai_compatible` \| `mock` |
| **Embed** | `GEMINI_EMBEDDING_DIM` | `768` | Số chiều vector (`64`–`3072`) |
| **RAG** | `RETRIEVAL_DEFAULT_TOP_K` | `6` | Số đoạn trích mặc định cho mỗi câu hỏi |
| **RAG** | `RETRIEVAL_CANDIDATE_K` | `20` | Số ứng viên lấy từ Hybrid Search trước khi Rerank |
| **RAG** | `RERANKER_PROVIDER` | `lexical` | `lexical` (nhanh, miễn phí) \| `llm` (AI chấm điểm) \| `none` |
| **RAG** | `QUERY_REWRITE_ENABLED` | `true` | Tự viết lại câu hỏi nối tiếp nhiều lượt thành truy vấn độc lập |
| **RAG** | `CONTEXT_MAX_TOKENS` | `6000` | Ngân sách token ngữ cảnh tối đa đưa vào prompt |
| **Ingest** | `CHUNKING_STRATEGY` | `recursive` | `recursive` \| `parent_child` (Small-to-Big) \| `semantic` |
| **Ingest** | `CONTEXTUAL_MODE` | `header` | `header` (miễn phí) \| `llm` (tóm tắt ngữ cảnh từng chunk bằng Gemini) |

> **Cảnh báo quan trọng khi đổi Embedding:** Nếu bạn chuyển `EMBEDDING_PROVIDER` (ví dụ từ `mock` sang `gemini`) hoặc thay đổi `GEMINI_EMBEDDING_DIM`, **bắt buộc phải chạy re-index** để đồng bộ lại vector cho các tài liệu cũ trong MongoDB:
> ```powershell
> cd backend
> .\.venv\Scripts\python.exe -m src.ingestion.cli sync --force
> ```

---

## 4. Bước 3 — Cài đặt & Cấu hình Frontend (`frontend/`)

1. Tạo file `frontend/.env` từ mẫu [frontend/.env.example](frontend/.env.example) (chạy từ thư mục gốc dự án):

```powershell
Copy-Item .\frontend\.env.example .\frontend\.env
# (macOS/Linux: cp frontend/.env.example frontend/.env)
```

2. Đảm bảo nội dung `frontend/.env` trỏ đúng vào Backend thật (`VITE_USE_MOCK=false`):

```dotenv
VITE_USE_MOCK=false
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

*(Nếu chỉ muốn xem giao diện mẫu offline không cần bật Backend/MongoDB, đổi `VITE_USE_MOCK=true`.)*

3. Cài đặt gói npm:

```powershell
cd frontend
npm install
```

---

## 5. Bước 4 — Khởi chạy toàn bộ hệ thống & Kiểm tra

Mở **2 cửa sổ terminal riêng biệt** tại **thư mục gốc dự án**:

### Terminal 1 — Khởi chạy FastAPI Backend (Cổng `8000`)
```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
# (macOS/Linux: ./.venv/bin/python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000)
```

Kiểm tra nhanh Backend đã nhận đúng Model AI & MongoDB chưa:
- Mở trình duyệt tới Swagger UI: `http://localhost:8000/docs`
- Hoặc gọi kiểm tra health:
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -Method Get
  ```
  Đảm bảo kết quả trả về `"status": "ok"` và `"llm_configured": true`.

### Terminal 2 — Khởi chạy Vite Frontend (Cổng `5173`)
```powershell
cd frontend
npm run dev
```

Mở trình duyệt truy cập **`http://localhost:5173`**.

### Nạp tài liệu nhanh qua CLI (tùy chọn thay cho kéo-thả trên web)
```powershell
cd backend

# Nạp một hoặc nhiều file kèm danh mục (thay bằng đường dẫn tới file tài liệu của bạn)
.\.venv\Scripts\python.exe -m src.ingestion.cli ingest `
  "./path/to/tai_lieu_1.pdf" `
  "./path/to/tai_lieu_2.docx" `
  --category "Kỹ thuật & IT"

# Xem thống kê số lượng documents / chunks trong MongoDB
.\.venv\Scripts\python.exe -m src.ingestion.cli stats
```

---

## 6. Bước 5 — Chạy bộ Kiểm thử & Đánh giá chất lượng RAG

(Các lệnh bên dưới chạy từ thư mục gốc dự án.)

### 6.1. Kiểm thử Backend (`pytest`)
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -v
```
Bộ test gồm 7 file (19 test cases) chạy hoàn toàn cô lập bằng `InMemoryVectorStore` và mock HTTP transport.

### 6.2. Đánh giá độ chính xác truy xuất (`eval_rag.py`)
```powershell
cd backend
.\.venv\Scripts\python.exe scripts/eval_rag.py
```

### 6.3. Kiểm tra TypeScript & Production Build Frontend
```powershell
cd frontend
npm run build
```

---

## 7. Xử lý sự cố thường gặp (Troubleshooting)

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| Câu trả lời hiện badge **`Trích xuất dự phòng`** kèm banner vàng | Thiếu `GEMINI_API_KEY` / `LLM_API_KEY`, đặt `LLM_PROVIDER=none`, hoặc tên `LLM_MODEL` / `GEMINI_GENERATION_MODEL` không hợp lệ / hết quota | Kiểm tra `GET /api/v1/health` xem `llm_configured` và `llm_model`. Đảm bảo dùng model hợp lệ (vd `gemini-2.5-flash`) và key còn hiệu lực trong `backend/.env`, sau đó restart `uvicorn`. |
| Tìm kiếm ngữ nghĩa tiếng Việt kém chính xác | Đang để `EMBEDDING_PROVIDER=mock` hoặc chưa re-index sau khi đổi provider | Đổi `EMBEDDING_PROVIDER=gemini` (hoặc `openai_compatible`) trong `backend/.env` rồi chạy `.\.venv\Scripts\python.exe -m src.ingestion.cli sync --force`. |
| Lỗi `Embedding count mismatch` hoặc lỗi dimension khi tìm vector | Chunks cũ trong MongoDB được embed với số chiều khác `GEMINI_EMBEDDING_DIM` hiện tại | Chạy `sync --force` để re-embed toàn bộ tài liệu về cùng một chiều vector. |
| `ServerSelectionTimeoutError` / `Authentication failed` khi bật Backend | Docker MongoDB chưa chạy hoặc sai user/password/cổng trong `MONGODB_URI` | Chạy `docker ps` kiểm tra container đang chạy cổng `27017` (Community) hoặc `27018` (Atlas Local) và đối chiếu `MONGODB_URI`. |
| Tài liệu bị đẩy vào `storage/dlq/` khi chạy `sync` | Tự copy file thẳng vào `storage/knowledge_base/...` nên thiếu file `.metadata.json` sidecar | Luôn nạp tài liệu qua API `/documents/upload`, giao diện Thư viện trên web, hoặc CLI `ingest`. |
| Frontend báo `Mất kết nối Backend` dù `uvicorn` đang chạy | Khác cổng trong `frontend/.env` hoặc bị chặn `CORS_ORIGINS` | Kiểm tra `VITE_API_BASE_URL=http://localhost:8000/api/v1` và đảm bảo origin trình duyệt nằm trong `CORS_ORIGINS` của `backend/.env`. |
