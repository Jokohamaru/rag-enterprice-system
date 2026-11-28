import { INITIAL_CHUNKS, INITIAL_DOCUMENTS } from '../data/mockData';
import type {
  CitationItem,
  ConversationItem,
  ConversationSummary,
  DocumentCategory,
  DocumentChunk,
  DocumentFormat,
  DocumentItem,
  HealthResponse,
  IngestionJobResult,
  NotebookItem,
  NotebookOverviewResponse,
  NoteItem,
  NoteType,
  QueryRequest,
  QueryResponse,
  SourceGuideResponse,
  StudioGenerateResponse,
  StudioGenerateType,
} from '../types/rag';

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';
const RAW_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000/api/v1';
const API_BASE_URL = RAW_BASE_URL.replace(/\/+$/, '');

export const isMockMode = USE_MOCK;
export const apiBaseUrl = API_BASE_URL;

// In-memory store for mock mode so uploaded documents & workspace items work offline
let mockDocuments: DocumentItem[] = [...INITIAL_DOCUMENTS];
let mockChunks: DocumentChunk[] = [...INITIAL_CHUNKS];
let mockNotebooks: NotebookItem[] = [];
let mockConversations: ConversationItem[] = [];
let mockNotes: NoteItem[] = [];

async function parseApiError(res: Response, fallback: string): Promise<string> {
  try {
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const data = (await res.json()) as { detail?: unknown; message?: unknown };
      if (typeof data.detail === 'string' && data.detail.trim()) {
        return data.detail;
      }
      if (Array.isArray(data.detail) && data.detail.length > 0) {
        const first = data.detail[0] as { msg?: string };
        if (first?.msg) return first.msg;
      }
      if (typeof data.message === 'string' && data.message.trim()) {
        return data.message;
      }
    } else {
      const text = (await res.text()).trim();
      if (text) return text;
    }
  } catch {
    // Ignore parse errors
  }
  return `${fallback} (HTTP ${res.status}).`;
}

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

function formatDateToday(): string {
  const now = new Date();
  return `${String(now.getDate()).padStart(2, '0')}/${String(now.getMonth() + 1).padStart(2, '0')}/${now.getFullYear()}`;
}

export async function fetchHealth(): Promise<HealthResponse> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/health`);
    if (!res.ok) {
      throw new Error(await parseApiError(res, 'Không thể kiểm tra trạng thái Backend'));
    }
    return res.json();
  }

  await new Promise((r) => setTimeout(r, 60));
  return {
    status: 'ok',
    embedding_provider: 'mock',
    llm_provider: 'mock',
    llm_model: 'notebooklm-demo',
    llm_configured: true,
    reranker_provider: 'lexical',
    chunking_strategy: 'recursive',
    contextual_mode: 'header',
    vectordb: { ok: true, backend: 'mock', vector_mode: 'memory' },
    stats: {
      documents: mockDocuments.length,
      chunks: mockChunks.length,
    },
  };
}

export async function fetchDocuments(): Promise<DocumentItem[]> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/documents`);
    if (!res.ok) {
      throw new Error(await parseApiError(res, 'Không thể tải danh sách tài liệu'));
    }
    return res.json();
  }

  await new Promise((r) => setTimeout(r, 90));
  return [...mockDocuments];
}

export async function fetchDocumentChunks(documentId: string): Promise<DocumentChunk[]> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/chunks`);
    if (!res.ok) {
      throw new Error(await parseApiError(res, 'Không thể tải danh sách đoạn văn bản'));
    }
    return res.json();
  }

  await new Promise((r) => setTimeout(r, 60));
  return mockChunks.filter((c) => c.documentId === documentId);
}

export async function fetchDocumentGuide(documentId: string): Promise<SourceGuideResponse> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/guide`);
    if (!res.ok) {
      throw new Error(await parseApiError(res, 'Không thể tải tóm tắt tài liệu'));
    }
    return res.json();
  }

  const doc = mockDocuments.find((d) => d.id === documentId);
  const chunks = mockChunks.filter((c) => c.documentId === documentId);
  return {
    documentId,
    documentTitle: doc?.title ?? 'Tài liệu',
    summary: doc?.summary ?? 'Tài liệu nội bộ.',
    keyTopics: chunks.map((c) => c.section).slice(0, 4),
    suggestedQuestions: [
      `Tóm tắt các điểm chính trong ${doc?.title ?? 'tài liệu này'}?`,
      'Các điều kiện hoặc thời hạn cần lưu ý là gì?',
    ],
    chunkCount: chunks.length,
    generationMode: 'extractive_fallback',
    modelUsed: 'mock',
  };
}

function runMockQuery(req: QueryRequest, startedAt: number): QueryResponse {
  const allowedIds = new Set(req.documentIds ?? mockDocuments.filter((d) => d.enabled).map((d) => d.id));
  const queryNorm = normalizeText(req.question);
  const topK = req.topK ?? 5;

  const ranked = mockChunks
    .filter((chunk) => allowedIds.has(chunk.documentId))
    .map((chunk) => ({
      chunk,
      score: scoreChunk(queryNorm, chunk),
    }))
    .filter((item) => item.score > 0.14)
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);

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
    usedInAnswer: true,
  }));

  const answer = buildMockAnswer(req.question, citations);
  const latencyMs = Math.round(performance.now() - startedAt + 280);

  return {
    answer,
    citations,
    latencyMs,
    generationMode: 'llm',
    modelUsed: 'notebooklm-demo',
    providerUsed: 'mock',
    followUpQuestions: citations.slice(0, 2).map((c) => `Chi tiết thêm về ${c.section} trong ${c.documentTitle}?`),
    conversationId: req.conversationId ?? null,
  };
}

export async function queryRag(req: QueryRequest): Promise<QueryResponse> {
  const startedAt = performance.now();
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      throw new Error(await parseApiError(res, 'Truy vấn thất bại'));
    }
    return res.json();
  }

  await new Promise((r) => setTimeout(r, 320));
  return runMockQuery(req, startedAt);
}

export interface StreamQueryCallbacks {
  onStatus?: (message: string, stage?: string) => void;
  onCitations?: (citations: CitationItem[]) => void;
  onDelta?: (textChunk: string) => void;
  onDone?: (response: QueryResponse) => void;
}

export async function streamQueryRag(
  req: QueryRequest,
  callbacks: StreamQueryCallbacks,
  signal?: AbortSignal
): Promise<QueryResponse> {
  const startedAt = performance.now();

  if (USE_MOCK) {
    callbacks.onStatus?.('Đang tìm kiếm trên các nguồn đang bật...', 'retrieving');
    await new Promise((r) => setTimeout(r, 220));
    const full = runMockQuery(req, startedAt);
    callbacks.onCitations?.(full.citations);

    const words = full.answer.split(/(\s+)/);
    for (let i = 0; i < words.length; i += 4) {
      if (signal?.aborted) break;
      callbacks.onDelta?.(words.slice(i, i + 4).join(''));
      await new Promise((r) => setTimeout(r, 24));
    }
    callbacks.onDone?.(full);
    return full;
  }

  const res = await fetch(`${API_BASE_URL}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(await parseApiError(res, 'Truy vấn streaming thất bại'));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let finalResponse: QueryResponse | null = null;
  let streamedAnswer = '';
  let latestCitations: CitationItem[] = [];

  const handleEventBlock = (block: string) => {
    const lines = block.split(/\r?\n/);
    let eventName = 'message';
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (dataLines.length === 0) return;

    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(dataLines.join('\n')) as Record<string, unknown>;
    } catch {
      return;
    }

    if (eventName === 'status') {
      callbacks.onStatus?.(String(payload.message ?? ''), String(payload.stage ?? ''));
    } else if (eventName === 'citations') {
      const cits = (payload.citations as CitationItem[]) ?? [];
      latestCitations = cits;
      callbacks.onCitations?.(cits);
    } else if (eventName === 'delta') {
      const piece = String(payload.text ?? '');
      if (piece) {
        streamedAnswer += piece;
        callbacks.onDelta?.(piece);
      }
    } else if (eventName === 'error') {
      throw new Error(String(payload.detail ?? 'Lỗi xử lý truy vấn'));
    } else if (eventName === 'done') {
      finalResponse = payload as unknown as QueryResponse;
      callbacks.onDone?.(finalResponse);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() ?? '';
    for (const part of parts) {
      if (part.trim()) {
        handleEventBlock(part);
      }
    }
  }

  if (buffer.trim()) {
    handleEventBlock(buffer);
  }

  if (finalResponse) {
    return finalResponse;
  }

  return {
    answer: streamedAnswer,
    citations: latestCitations,
    latencyMs: Math.round(performance.now() - startedAt),
    generationMode: 'extractive_fallback',
  };
}

export async function uploadDocument(
  file: File,
  category: DocumentCategory,
  onStatusChange?: (doc: DocumentItem, replacedId?: string) => void,
  onUploadFailed?: (tempId: string) => void
): Promise<DocumentItem> {
  const dateLabel = formatDateToday();
  const cleanTitle = file.name.replace(/\.[^/.]+$/, '').replace(/[-_]+/g, ' ');
  const formattedTitle = cleanTitle ? cleanTitle.charAt(0).toUpperCase() + cleanTitle.slice(1) : file.name;

  if (!USE_MOCK) {
    const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const tempDoc: DocumentItem = {
      id: tempId,
      title: formattedTitle,
      filename: file.name,
      format: detectFormat(file.name),
      category,
      sizeLabel: formatFileSize(file.size),
      chunkCount: 0,
      updatedAt: dateLabel,
      status: 'embedding',
      enabled: true,
      summary: 'Đang tải lên và lập chỉ mục vào hệ thống...',
    };
    onStatusChange?.(tempDoc);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);

    try {
      const res = await fetch(`${API_BASE_URL}/documents/upload`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        throw new Error(await parseApiError(res, `Tải tài liệu "${file.name}" thất bại`));
      }
      const savedDoc = (await res.json()) as DocumentItem;
      onStatusChange?.(savedDoc, tempId);
      return savedDoc;
    } catch (err) {
      onUploadFailed?.(tempId);
      throw err;
    }
  }

  const docId = `doc-custom-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  const draftDoc: DocumentItem = {
    id: docId,
    title: formattedTitle,
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

  await new Promise((r) => setTimeout(r, 400));
  const readyDoc: DocumentItem = { ...draftDoc, status: 'ready' };
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
      content: `Nội dung trích xuất từ tệp ${file.name} thuộc danh mục ${category}.`,
      highlight: file.name,
    },
    ...mockChunks,
  ];
  onStatusChange?.(readyDoc);
  return readyDoc;
}

export async function updateDocumentEnabled(documentId: string, enabled: boolean): Promise<DocumentItem> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(documentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    if (!res.ok) {
      throw new Error(await parseApiError(res, 'Không thể cập nhật trạng thái tài liệu'));
    }
    return res.json();
  }

  const found = mockDocuments.find((d) => d.id === documentId);
  if (!found) throw new Error('Không tìm thấy tài liệu.');
  const updated = { ...found, enabled };
  mockDocuments = mockDocuments.map((d) => (d.id === documentId ? updated : d));
  return updated;
}

export async function deleteDocument(documentId: string): Promise<void> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(documentId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      throw new Error(await parseApiError(res, 'Không thể xóa tài liệu'));
    }
    return;
  }

  mockDocuments = mockDocuments.filter((d) => d.id !== documentId);
  mockChunks = mockChunks.filter((c) => c.documentId !== documentId);
}

export async function syncKnowledgeBase(force = false): Promise<IngestionJobResult> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/ingestion/sync?force=${force ? 'true' : 'false'}`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(await parseApiError(res, 'Đồng bộ kho tri thức thất bại'));
    }
    return res.json();
  }

  const now = new Date().toISOString();
  return {
    job_id: `mock-job-${Date.now()}`,
    trigger: 'sync',
    status: 'completed',
    processed_files: mockDocuments.length,
    indexed_files: 0,
    skipped_files: mockDocuments.length,
    failed_files: 0,
    total_chunks: mockChunks.length,
    document_ids: mockDocuments.map((d) => d.id),
    errors: [],
    started_at: now,
    finished_at: now,
  };
}

// === Notebooks ===

export async function fetchNotebooks(): Promise<NotebookItem[]> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/notebooks`);
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể tải danh sách Notebook'));
    return res.json();
  }
  return [...mockNotebooks];
}

export async function createNotebook(
  title: string,
  documentIds: string[],
  description = ''
): Promise<NotebookItem> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/notebooks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, documentIds, description }),
    });
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể tạo Notebook'));
    return res.json();
  }
  const now = new Date().toISOString();
  const nb: NotebookItem = {
    id: `nb-${Date.now()}`,
    title,
    description,
    documentIds,
    overview: '',
    suggestedQuestions: [],
    createdAt: now,
    updatedAt: now,
  };
  mockNotebooks = [nb, ...mockNotebooks];
  return nb;
}

export async function updateNotebook(
  notebookId: string,
  patch: Partial<Pick<NotebookItem, 'title' | 'description' | 'documentIds'>>
): Promise<NotebookItem> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/notebooks/${encodeURIComponent(notebookId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể cập nhật Notebook'));
    return res.json();
  }
  const idx = mockNotebooks.findIndex((n) => n.id === notebookId);
  if (idx === -1) throw new Error('Không tìm thấy Notebook');
  const updated = { ...mockNotebooks[idx], ...patch, updatedAt: new Date().toISOString() };
  mockNotebooks[idx] = updated;
  return updated;
}

export async function deleteNotebook(notebookId: string): Promise<void> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/notebooks/${encodeURIComponent(notebookId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể xóa Notebook'));
    return;
  }
  mockNotebooks = mockNotebooks.filter((n) => n.id !== notebookId);
}

export async function generateNotebookOverview(
  documentIds: string[],
  notebookId?: string | null
): Promise<NotebookOverviewResponse> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/notebooks/overview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ documentIds, notebookId: notebookId ?? null }),
    });
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể tạo tổng quan Notebook'));
    return res.json();
  }
  const docs = mockDocuments.filter((d) => documentIds.includes(d.id));
  return {
    overview: `Tổng hợp ${docs.length} nguồn tài liệu nội bộ đang bật.`,
    suggestedQuestions: docs.slice(0, 3).map((d) => `Những điểm chính trong ${d.title}?`),
    modelUsed: 'mock',
    generationMode: 'extractive_fallback',
  };
}

// === Conversations ===

export async function fetchConversations(notebookId?: string | null): Promise<ConversationSummary[]> {
  if (!USE_MOCK) {
    const qs = notebookId ? `?notebook_id=${encodeURIComponent(notebookId)}` : '';
    const res = await fetch(`${API_BASE_URL}/conversations${qs}`);
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể tải lịch sử hội thoại'));
    return res.json();
  }
  return mockConversations
    .filter((c) => !notebookId || c.notebookId === notebookId)
    .map((c) => ({
      id: c.id,
      title: c.title,
      notebookId: c.notebookId,
      messageCount: c.messages.length,
      createdAt: c.createdAt,
      updatedAt: c.updatedAt,
    }));
}

export async function createConversation(
  title = 'Cuộc hội thoại mới',
  notebookId?: string | null
): Promise<ConversationItem> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, notebookId: notebookId ?? null }),
    });
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể tạo cuộc hội thoại'));
    return res.json();
  }
  const now = new Date().toISOString();
  const conv: ConversationItem = {
    id: `conv-${Date.now()}`,
    title,
    notebookId: notebookId ?? null,
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
  mockConversations = [conv, ...mockConversations];
  return conv;
}

export async function fetchConversation(conversationId: string): Promise<ConversationItem> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/conversations/${encodeURIComponent(conversationId)}`);
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể tải cuộc hội thoại'));
    return res.json();
  }
  const found = mockConversations.find((c) => c.id === conversationId);
  if (!found) throw new Error('Không tìm thấy cuộc hội thoại');
  return found;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/conversations/${encodeURIComponent(conversationId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể xóa cuộc hội thoại'));
    return;
  }
  mockConversations = mockConversations.filter((c) => c.id !== conversationId);
}

// === Studio & Notes ===

export async function generateStudioArtifact(
  type: StudioGenerateType,
  documentIds: string[],
  notebookId?: string | null,
  customInstruction?: string
): Promise<StudioGenerateResponse> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/studio/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type,
        documentIds,
        notebookId: notebookId ?? null,
        saveAsNote: true,
        customInstruction,
      }),
    });
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể tạo nội dung Studio'));
    return res.json();
  }

  const now = new Date().toISOString();
  const content = `### Kết quả ${type}\n\nTổng hợp từ ${documentIds.length} nguồn đang bật.`;
  const note: NoteItem = {
    id: `note-${Date.now()}`,
    notebookId: notebookId ?? null,
    title: `Studio (${type})`,
    content,
    noteType: type,
    sourceDocumentIds: documentIds,
    createdAt: now,
    updatedAt: now,
  };
  mockNotes = [note, ...mockNotes];
  return { title: note.title, content, type, generationMode: 'extractive_fallback', note };
}

export async function fetchNotes(notebookId?: string | null): Promise<NoteItem[]> {
  if (!USE_MOCK) {
    const qs = notebookId ? `?notebook_id=${encodeURIComponent(notebookId)}` : '';
    const res = await fetch(`${API_BASE_URL}/notes${qs}`);
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể tải danh sách ghi chú'));
    return res.json();
  }
  return mockNotes.filter((n) => !notebookId || n.notebookId === notebookId);
}

export async function createNote(payload: {
  title: string;
  content: string;
  noteType?: NoteType;
  notebookId?: string | null;
  sourceDocumentIds?: string[];
}): Promise<NoteItem> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể lưu ghi chú'));
    return res.json();
  }
  const now = new Date().toISOString();
  const note: NoteItem = {
    id: `note-${Date.now()}`,
    notebookId: payload.notebookId ?? null,
    title: payload.title,
    content: payload.content,
    noteType: payload.noteType ?? 'pinned',
    sourceDocumentIds: payload.sourceDocumentIds ?? [],
    createdAt: now,
    updatedAt: now,
  };
  mockNotes = [note, ...mockNotes];
  return note;
}

export async function deleteNote(noteId: string): Promise<void> {
  if (!USE_MOCK) {
    const res = await fetch(`${API_BASE_URL}/notes/${encodeURIComponent(noteId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await parseApiError(res, 'Không thể xóa ghi chú'));
    return;
  }
  mockNotes = mockNotes.filter((n) => n.id !== noteId);
}
