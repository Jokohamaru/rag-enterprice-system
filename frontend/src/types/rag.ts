export type DocumentCategory = 'Nhân sự' | 'Vận hành' | 'Kỹ thuật & IT';

export type DocumentFormat = 'PDF' | 'DOCX' | 'MD' | 'TXT';

export type DocumentStatus = 'ready' | 'chunking' | 'embedding' | 'error';

export type ConnectionState = 'checking' | 'connected' | 'degraded' | 'offline';

export interface DocumentChunk {
  id: string;
  documentId: string;
  documentTitle: string;
  category: DocumentCategory | string;
  section: string;
  page?: number | null;
  chunkIndex: number;
  content: string;
  highlight?: string | null;
}

export interface DocumentItem {
  id: string;
  title: string;
  filename: string;
  format: DocumentFormat;
  category: DocumentCategory | string;
  sizeLabel: string;
  chunkCount: number;
  updatedAt: string;
  status: DocumentStatus;
  enabled: boolean;
  summary: string;
  tenant_id?: string;
  department?: string;
  error_message?: string | null;
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

export interface HealthResponse {
  status: 'ok' | 'degraded';
  embedding_provider: string;
  chunking_strategy: string;
  contextual_mode: string;
  vectordb: {
    ok: boolean;
    backend: string;
    database?: string;
    vector_mode?: string;
  };
  stats: {
    documents: number;
    chunks: number;
    parent_chunks?: number;
    dlq_events?: number;
    chunks_by_department?: Record<string, number>;
  };
}

export interface IngestionJobResult {
  job_id: string;
  trigger: 'upload' | 'sync' | 'cli';
  status: 'completed' | 'partial' | 'failed';
  processed_files: number;
  indexed_files: number;
  skipped_files: number;
  failed_files: number;
  total_chunks: number;
  document_ids: string[];
  errors: string[];
  started_at: string;
  finished_at: string;
}
