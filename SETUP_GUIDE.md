# Hướng dẫn Cài đặt & Vận hành Hệ thống Enterprise RAG (NotebookLM Edition)

Tài liệu này hướng dẫn từng bước cách cài đặt môi trường, cấu hình AI Model API (Google Gemini / OpenAI / OpenRouter / Groq / Ollama), khởi chạy cơ sở dữ liệu MongoDB, chạy Backend + Frontend, kiểm thử và xử lý sự cố.

---

## 1. Yêu cầu tiên quyết (Prerequisites)

Trước khi bắt đầu, hãy đảm bảo máy tính của bạn đã cài đặt:

1. **Python 3.12** (khuyên dùng **Python 3.12.16** hoặc tạo môi trường riêng từ Anaconda tại `D:\anaconda3\envs\hand_env\python.exe`).
   - *Lưu ý:* Tránh dùng Python 3.14 bản quá mới vì một số gói xử lý PDF/tính toán số học có thể thiếu wheel biên dịch sẵn trên Windows.
2. **Node.js 18+ (khuyên dùng 20 LTS)** kèm `npm` để chạy và build Frontend React + Vite.
3. **Docker Desktop** (để chạy MongoDB Community hoặc MongoDB Atlas Local).
4. **API Key cho mô hình AI** *(hoặc cài Ollama nếu chạy model nội bộ)*:
   - Google AI Studio API Key (`GEMINI_API_KEY`) nếu dùng Gemini, **hoặc**
   - OpenAI / OpenRouter / Groq / DeepSeek API Key (`LLM_API_KEY`) nếu dùng chuẩn OpenAI-Compatible.

---

## 2. Bước 1 — Khởi chạy Cơ sở dữ liệu MongoDB

Hệ thống sử dụng **MongoDB Dual-Mode** (`auto` tự nhận diện Community hay Atlas Search). Chọn **1 trong 2** cách dưới đây:

### Cách A: Dùng MongoDB Community (Mặc định, nhẹ, cổng `27017`)
Nếu bạn đã có container MongoDB tại `D:\MongoDB`:

```powershell
cd D:\MongoDB
docker compose up -d
```

Hoặc chạy nhanh một container MongoDB mới bằng Docker:

```powershell
docker run -d --name mongodb-rag `
  -p 27017:27017 `
  -e MONGO_INITDB_ROOT_USERNAME=admin `
  -e MONGO_INITDB_ROOT_PASSWORD=password123 `
  mongo:latest
```

Chuỗi kết nối tương ứng:
```dotenv
MONGODB_URI=mongodb://admin:password123@localhost:27017/?authSource=admin
MONGODB_VECTOR_MODE=auto
```

### Cách B: Dùng MongoDB Atlas Local (HNSW Vector Search + Full-Text Search, cổng `27018`)
Khi lượng dữ liệu lớn (hàng chục nghìn đến hàng trăm nghìn đoạn văn bản), bạn có thể bật container Atlas Local đi kèm sẵn trong dự án tại [backend/docker-compose.atlas.yml](backend/docker-compose.atlas.yml):

```powershell
cd E:\A\rag-enterprice-system\backend
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

Mở Windows PowerShell và chạy lần lượt:

```powershell
cd E:\A\rag-enterprice-system\backend

# Tạo môi trường ảo cô lập bằng Python 3.12
D:\anaconda3\envs\hand_env\python.exe -m venv .venv

# Cài đặt toàn bộ phụ thuộc trong requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> Nếu máy bạn không dùng đường dẫn Anaconda trên, thay `D:\anaconda3\envs\hand_env\python.exe` bằng đường dẫn tới Python 3.12 trên máy bạn (`py -3.12 -m venv .venv`).

### 3.2. Tạo tệp cấu hình `backend/.env`

Sao chép từ file mẫu [backend/.env.example](backend/.env.example):

```powershell
Copy-Item E:\A\rag-enterprice-system\backend\.env.example E:\A\rag-enterprice-system\backend\.env
```

> **Thứ tự nạp `.env`:** Backend đọc từ `E:\A\rag-enterprice-system\.env` làm nền, sau đó `backend/.env` sẽ **ghi đè** các biến tương ứng (xem `Settings.model_config` trong `backend/src/config/settings.py`).

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
> cd E:\A\rag-enterprice-system\backend
> .\.venv\Scripts\python.exe -m src.ingestion.cli sync --force
> ```

---

## 4. Bước 3 — Cài đặt & Cấu hình Frontend (`frontend/`)

1. Tạo file `frontend/.env` từ mẫu [frontend/.env.example](frontend/.env.example):

```powershell
Copy-Item E:\A\rag-enterprice-system\frontend\.env.example E:\A\rag-enterprice-system\frontend\.env
```

2. Đảm bảo nội dung `frontend/.env` trỏ đúng vào Backend thật (`VITE_USE_MOCK=false`):

```dotenv
VITE_USE_MOCK=false
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

*(Nếu chỉ muốn xem giao diện mẫu offline không cần bật Backend/MongoDB, đổi `VITE_USE_MOCK=true`.)*

3. Cài đặt gói npm:

```powershell
cd E:\A\rag-enterprice-system\frontend
npm install
```

---

## 5. Bước 4 — Khởi chạy toàn bộ hệ thống & Kiểm tra

Mở **2 cửa sổ PowerShell riêng biệt**:

### Terminal 1 — Khởi chạy FastAPI Backend (Cổng `8000`)
```powershell
cd E:\A\rag-enterprice-system\backend
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
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
cd E:\A\rag-enterprice-system\frontend
npm run dev
```

Mở trình duyệt truy cập **`http://localhost:5173`**.

### Nạp tài liệu nhanh qua CLI (tùy chọn thay cho kéo-thả trên web)
```powershell
cd E:\A\rag-enterprice-system\backend

# Nạp một hoặc nhiều file kèm danh mục
.\.venv\Scripts\python.exe -m src.ingestion.cli ingest `
  "..\RAG_Architectures_A_Complete_Guide_for_2025.pdf" `
  "..\RAG_Tutorial_AI_VIET_NAM_114_pages.pdf" `
  --category "Kỹ thuật & IT"

# Xem thống kê số lượng documents / chunks trong MongoDB
.\.venv\Scripts\python.exe -m src.ingestion.cli stats
```

---

## 6. Bước 5 — Chạy bộ Kiểm thử & Đánh giá chất lượng RAG

### 6.1. Kiểm thử Backend (`pytest`)
```powershell
cd E:\A\rag-enterprice-system\backend
.\.venv\Scripts\python.exe -m pytest tests -v
```
Bộ test gồm 7 file (19 test cases) chạy hoàn toàn cô lập bằng `InMemoryVectorStore` và mock HTTP transport.

### 6.2. Đánh giá độ chính xác truy xuất (`eval_rag.py`)
```powershell
cd E:\A\rag-enterprice-system\backend
.\.venv\Scripts\python.exe scripts/eval_rag.py
```

### 6.3. Kiểm tra TypeScript & Production Build Frontend
```powershell
cd E:\A\rag-enterprice-system\frontend
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
