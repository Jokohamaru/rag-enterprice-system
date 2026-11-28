# Enterprise RAG System (NotebookLM Edition)

Hệ thống hỏi đáp tài liệu nội bộ doanh nghiệp theo phong cách **NotebookLM**: hỗ trợ nạp đa định dạng (`PDF`, `DOCX`, `MD`, `TXT`), tìm kiếm lai (**Hybrid Search**: Dense Vector + BM25 + RRF + Reranker), trả lời bằng **AI Model API** đa nhà cung cấp (Google Gemini, OpenAI, OpenRouter, Groq, Ollama local) với **SSE Streaming**, trích dẫn đối chiếu nguyên văn tương tác và không gian làm việc **Notebooks / Studio / Source Guide**.

## Tài liệu hướng dẫn

- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** — Hướng dẫn cài đặt chi tiết từ đầu (MongoDB, Python 3.12 Backend, cấu hình chuyển đổi AI Model API qua `.env`, Frontend React/Vite, kiểm thử và xử lý sự cố).
- **[TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md)** — Giải thích chi tiết kỹ thuật và từng bước luồng hoạt động thực tế của dự án (Khởi động → Ingestion Pipeline → Online RAG & Streaming → Notebooks & Studio).
- **[backend/backend.md](backend/backend.md)** — Tài liệu tham chiếu API endpoints, CLI và chi tiết nội bộ phân hệ Backend.
