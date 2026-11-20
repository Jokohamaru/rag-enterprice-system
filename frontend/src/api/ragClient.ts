import { INITIAL_CHUNKS, INITIAL_DOCUMENTS } from '../data/mockData';
import type {
  CitationItem,
  DocumentCategory,
  DocumentChunk,
  DocumentFormat,
  DocumentItem,
  QueryRequest,
  QueryResponse,
} from '../types/rag';

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000/api/v1';

export const isMockMode = USE_MOCK;
export const apiBaseUrl = API_BASE_URL;

// In-memory store for mock mode so uploaded documents become immediately searchable
let mockDocuments: DocumentItem[] = [...INITIAL_DOCUMENTS];
let mockChunks: DocumentChunk[] = [...INITIAL_CHUNKS];

function normalizeText(input: string): string {
  return input
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function scoreChunk(queryNorm: string, chunk: DocumentChunk): number {
  const tokens = queryNorm.split(' ').filter((t) => t.length > 1);
  if (tokens.length === 0) return 0;

  const haystack = normalizeText(`${chunk.documentTitle} ${chunk.section} ${chunk.content}`);
  let hits = 0;
  let exactPhraseBonus = 0;

  for (const token of tokens) {
    if (haystack.includes(token)) {
      hits += 1;
    }
  }

  // Domain keyword boosters for Vietnamese enterprise queries
  const boosters: Array<[string[], string]> = [
    [['phep', 'nghi', 'hybrid', 'remote', 'tu xa'], 'doc-hr-leave'],
    [['thu viec', 'onboarding', 'hoi nhap', 'okr'], 'doc-hr-onboarding'],
    [['hoan ung', 'cong tac', 'khach san', 'vat', 'hoa don', 'phu cap'], 'doc-ops-expense'],
    [['bao mat', 'ro ri', 'du lieu', 'khach hang', 'secops'], 'doc-ops-security'],
    [['vpn', 'wireguard', 'sso', 'laptop', 'that lac', 'mdm', 'mat may'], 'doc-it-vpn'],
    [['sev', 'oncall', 'on call', 'su co', 'post mortem', 'sla'], 'doc-it-oncall'],
  ];

  for (const [keywords, docId] of boosters) {
    if (chunk.documentId === docId && keywords.some((kw) => queryNorm.includes(kw))) {
      exactPhraseBonus += 0.28;
    }
  }

  const ratio = hits / Math.max(tokens.length, 4);
  return Math.min(0.98, ratio * 0.82 + exactPhraseBonus);
}

function buildMockAnswer(question: string, citations: CitationItem[]): string {
  if (citations.length === 0) {
    return 'Không tìm thấy đoạn tài liệu phù hợp trong phạm vi đang chọn. Hãy thử mở rộng danh mục tài liệu ở thanh bên trái hoặc tải thêm tài liệu liên quan vào Thư viện.';
  }

  const q = normalizeText(question);

  if (q.includes('phep') && (q.includes('tu xa') || q.includes('hybrid') || q.includes('remote'))) {
    const c1 = citations.find((c) => c.id === 'chk-hr-1')?.citationNumber ?? 1;
    const c2 = citations.find((c) => c.id === 'chk-hr-2')?.citationNumber ?? Math.min(2, citations.length);
    return `Theo chính sách hiện hành, nhân viên chính thức sau thử việc được hưởng **15 ngày phép năm có lương** (cộng thêm 1 ngày cho mỗi 3 năm thâm niên) và được chuyển tối đa 5 ngày chưa dùng sang quý I năm sau, sử dụng trước ngày 31/03 [${c1}].\n\nVề chế độ làm việc linh hoạt, bạn có thể đăng ký làm việc từ xa **tối đa 2 ngày mỗi tuần** (không áp dụng vào thứ Hai họp toàn phòng). Yêu cầu cần gửi trên hệ thống HRM trước 17:00 ngày làm việc liền trước để trưởng bộ phận phê duyệt [${c2}].`;
  }

  if (q.includes('hoan ung') || q.includes('cong tac') || q.includes('khach san')) {
    const c1 = citations.find((c) => c.id === 'chk-ops-1')?.citationNumber ?? 1;
    const c2 = citations.find((c) => c.id === 'chk-ops-2')?.citationNumber ?? Math.min(2, citations.length);
    return `Hồ sơ hoàn ứng công tác phí cần nộp trong vòng **7 ngày làm việc** sau khi kết thúc chuyến đi, kèm hóa đơn điện tử VAT đúng mã số thuế công ty. Phòng Tài chính tổng hợp chứng từ vào thứ Tư và chuyển khoản giải ngân vào thứ Sáu hàng tuần [${c1}].\n\nĐịnh mức lưu trú tại Hà Nội và TP. Hồ Chí Minh là **1.800.000 VNĐ/đêm** (đã gồm thuế), kèm phụ cấp ăn uống cố định **350.000 VNĐ/ngày** không yêu cầu hóa đơn lẻ cho chuyến công tác từ 1 ngày trở lên [${c2}].`;
  }

  if (q.includes('vpn') || q.includes('that lac') || q.includes('laptop') || q.includes('mat may')) {
    const c1 = citations.find((c) => c.id === 'chk-it-1')?.citationNumber ?? 1;
    const c2 = citations.find((c) => c.id === 'chk-it-2')?.citationNumber ?? Math.min(2, citations.length);
    return `Để xin cấp quyền VPN nội bộ, bạn tạo phiếu yêu cầu trên cổng **IT Service Desk** (mục Truy cập mạng) có phê duyệt của trưởng nhóm. Tài khoản WireGuard VPN được cấp trong vòng **4 giờ làm việc** và bắt buộc bật xác thực 2 lớp (SSO + TOTP) [${c1}].\n\nTrong trường hợp thất lạc laptop hoặc điện thoại có đăng nhập email công ty, cần gọi ngay đường dây nóng IT (**máy lẻ 1199**) để kích hoạt khóa từ xa qua MDM và thu hồi toàn bộ phiên đăng nhập SSO trong vòng **15 phút** [${c2}].`;
  }

  if (q.includes('sev') || q.includes('su co') || q.includes('ro ri') || q.includes('bao mat')) {
    const c1 = citations.find((c) => c.id === 'chk-it-3')?.citationNumber ?? 1;
    const c2 = citations.find((c) => c.id === 'chk-ops-3')?.citationNumber ?? Math.min(2, citations.length);
    return `Đối với sự cố hạ tầng mức **Sev-1**, kỹ sư trực on-call phải xác nhận cảnh báo trong vòng **10 phút**, mở kênh điều phối ngay lập tức và hoàn thiện báo cáo phân tích nguyên nhân gốc (Post-mortem) trong vòng **48 giờ** sau khi hệ thống ổn định [${c1}].\n\nNếu phát hiện dấu hiệu rò rỉ hoặc gửi nhầm dữ liệu khách hàng (Cấp độ 3 - Mật), cần báo ngay cho đội An toàn thông tin qua kênh **#security-incident** hoặc email **secops@company.vn** trong vòng tối đa **2 giờ** [${c2}].`;
  }

  // Generic grounded synthesis from top retrieved chunks
  const paragraphs = citations.slice(0, 2).map((c) => {
    return `Theo tài liệu **${c.documentTitle}** (${c.section}), ${c.content.charAt(0).toLowerCase()}${c.content.slice(1)} [${c.citationNumber}]`;
  });

  return `${paragraphs.join('\n\n')}\n\nBạn có thể nhấn trực tiếp vào từng số trích dẫn để đối chiếu nguyên văn đoạn tài liệu ở khung bên phải.`;
}

function detectFormat(filename: string): DocumentFormat {
  const ext = filename.split('.').pop()?.toUpperCase();
  if (ext === 'PDF' || ext === 'DOCX' || ext === 'MD' || ext === 'TXT') {
    return ext;
  }
  return 'PDF';
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export async function fetchDocuments(): Promise<DocumentItem[]> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/documents`);
    if (!res.ok) throw new Error(`Không thể tải danh sách tài liệu (${res.status}).`);
    return res.json();
  }

  await new Promise((r) => setTimeout(r, 120));
  return [...mockDocuments];
}

export async function queryRag(req: QueryRequest): Promise<QueryResponse> {
  const startedAt = performance.now();

  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(`Truy vấn thất bại (${res.status}). Kiểm tra lại kết nối backend.`);
    return res.json();
  }

  await new Promise((r) => setTimeout(r, 420));

  const allowedIds = new Set(req.documentIds);
  const queryNorm = normalizeText(req.question);
  const topK = req.topK ?? 3;

  const ranked = mockChunks
    .filter((chunk) => allowedIds.has(chunk.documentId))
    .map((chunk) => ({
      chunk,
      score: scoreChunk(queryNorm, chunk),
    }))
    .filter((item) => item.score > 0.14)
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);

  // Fallback to top chunks in allowed scope if query is very broad
  const selected =
    ranked.length > 0
      ? ranked
      : mockChunks
          .filter((chunk) => allowedIds.has(chunk.documentId))
          .slice(0, 2)
          .map((chunk, idx) => ({ chunk, score: 0.68 - idx * 0.09 }));

  const citations: CitationItem[] = selected.map((item, idx) => ({
    ...item.chunk,
    citationNumber: idx + 1,
    score: Number(Math.max(0.55, Math.min(0.97, item.score + 0.12)).toFixed(2)),
  }));

  const answer = buildMockAnswer(req.question, citations);
  const latencyMs = Math.round(performance.now() - startedAt + 310);

  return { answer, citations, latencyMs };
}

export async function uploadDocument(
  file: File,
  category: DocumentCategory,
  onStatusChange?: (doc: DocumentItem) => void
): Promise<DocumentItem> {
  if (!USE_MOCK) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);
    const res = await fetch(`${API_BASE_URL}/documents/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error(`Tải tài liệu thất bại (${res.status}).`);
    return res.json();
  }

  const now = new Date();
  const dateLabel = `${String(now.getDate()).padStart(2, '0')}/${String(now.getMonth() + 1).padStart(2, '0')}/${now.getFullYear()}`;
  const cleanTitle = file.name.replace(/\.[^/.]+$/, '').replace(/[-_]+/g, ' ');
  const docId = `doc-custom-${Date.now()}`;

  const draftDoc: DocumentItem = {
    id: docId,
    title: cleanTitle.charAt(0).toUpperCase() + cleanTitle.slice(1),
    filename: file.name,
    format: detectFormat(file.name),
    category,
    sizeLabel: formatFileSize(file.size),
    chunkCount: Math.max(4, Math.min(48, Math.ceil(file.size / 18000))),
    updatedAt: dateLabel,
    status: 'chunking',
    enabled: true,
    summary: `Tài liệu tải lên mới thuộc nhóm ${category}, đã sẵn sàng phục vụ truy xuất ngữ nghĩa.`,
  };

  mockDocuments = [draftDoc, ...mockDocuments];
  onStatusChange?.(draftDoc);

  // Read plain text preview if MD/TXT
  let textPreview = '';
  if (file.name.endsWith('.md') || file.name.endsWith('.txt')) {
    try {
      const raw = await file.text();
      textPreview = raw.trim().slice(0, 420);
    } catch {
      textPreview = '';
    }
  }

  await new Promise((r) => setTimeout(r, 650));
  const embeddingDoc: DocumentItem = { ...draftDoc, status: 'embedding' };
  mockDocuments = mockDocuments.map((d) => (d.id === docId ? embeddingDoc : d));
  onStatusChange?.(embeddingDoc);

  await new Promise((r) => setTimeout(r, 750));
  const readyDoc: DocumentItem = { ...embeddingDoc, status: 'ready' };
  mockDocuments = mockDocuments.map((d) => (d.id === docId ? readyDoc : d));

  mockChunks = [
    {
      id: `chk-${docId}-1`,
      documentId: docId,
      documentTitle: readyDoc.title,
      category,
      section: 'Mục 1 — Nội dung vừa lập chỉ mục',
      page: 1,
      chunkIndex: 1,
      content:
        textPreview ||
        `Nội dung trích xuất từ tệp ${file.name} thuộc danh mục ${category}. Tài liệu đã được tách thành ${readyDoc.chunkCount} đoạn (chunks) và lưu vào kho vector để trả lời câu hỏi nội bộ.`,
      highlight: textPreview ? textPreview.slice(0, 90) : file.name,
    },
    ...mockChunks,
  ];

  onStatusChange?.(readyDoc);
  return readyDoc;
}

export async function deleteDocument(documentId: string): Promise<void> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/documents/${documentId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(`Không thể xóa tài liệu (${res.status}).`);
    return;
  }

  await new Promise((r) => setTimeout(r, 150));
  mockDocuments = mockDocuments.filter((d) => d.id !== documentId);
  mockChunks = mockChunks.filter((c) => c.documentId !== documentId);
}
