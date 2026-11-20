export type DocumentCategory = 'Nhân sự' | 'Vận hành' | 'Kỹ thuật & IT';

export type DocumentFormat = 'PDF' | 'DOCX' | 'MD' | 'TXT';

export type DocumentStatus = 'ready' | 'chunking' | 'embedding' | 'error';

export interface DocumentChunk {
  id: string;
  documentId: string;
  documentTitle: string;
  category: DocumentCategory;
  section: string;
  page?: number;
  chunkIndex: number;
  content: string;
  highlight?: string;
}

export interface DocumentItem {
  id: string;
  title: string;
  filename: string;
  format: DocumentFormat;
  category: DocumentCategory;
  sizeLabel: string;
  chunkCount: number;
  updatedAt: string;
  status: DocumentStatus;
  enabled: boolean;
  summary: string;
}

export interface CitationItem extends DocumentChunk {
  citationNumber: number;
  score: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  citations?: CitationItem[];
  latencyMs?: number;
  isStreaming?: boolean;
  error?: string;
}

export interface QueryRequest {
  question: string;
  documentIds: string[];
  topK?: number;
}

export interface QueryResponse {
  answer: string;
  citations: CitationItem[];
  latencyMs: number;
}
