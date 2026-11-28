export type DocumentCategory = 'Nhân sự' | 'Vận hành' | 'Kỹ thuật & IT';

export type DocumentFormat = 'PDF' | 'DOCX' | 'MD' | 'TXT';

export type DocumentStatus = 'ready' | 'chunking' | 'embedding' | 'error';

export type ConnectionState = 'checking' | 'connected' | 'degraded' | 'offline';

export type GenerationMode = 'llm' | 'extractive_fallback';

export type StudioGenerateType =
  | 'summary'
  | 'faq'
  | 'briefing'
  | 'study_guide'
  | 'comparison_table';

export type NoteType = 'pinned' | StudioGenerateType | 'custom';

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
  usedInAnswer?: boolean;
  parentContent?: string | null;
}

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  citations?: CitationItem[];
  latencyMs?: number;
  isStreaming?: boolean;
  statusText?: string;
  generationMode?: GenerationMode;
  modelUsed?: string | null;
  providerUsed?: string | null;
  rewrittenQuery?: string | null;
  followUpQuestions?: string[];
  warning?: string | null;
  error?: string;
}

export interface QueryRequest {
  question: string;
  documentIds?: string[];
  topK?: number;
  history?: ChatTurn[];
  conversationId?: string | null;
  notebookId?: string | null;
  useReranker?: boolean;
}

export interface QueryResponse {
  answer: string;
  citations: CitationItem[];
  latencyMs: number;
  generationMode?: GenerationMode;
  modelUsed?: string | null;
  providerUsed?: string | null;
  rewrittenQuery?: string | null;
  followUpQuestions?: string[];
  warning?: string | null;
  conversationId?: string | null;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  embedding_provider: string;
  embedding_model?: string;
  llm_provider?: string;
  llm_model?: string;
  llm_configured?: boolean;
  reranker_provider?: string;
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

export interface NotebookItem {
  id: string;
  title: string;
  description: string;
  documentIds: string[];
  overview: string;
  suggestedQuestions: string[];
  createdAt: string;
  updatedAt: string;
}

export interface NotebookOverviewResponse {
  overview: string;
  suggestedQuestions: string[];
  modelUsed?: string | null;
  generationMode: GenerationMode;
}

export interface ConversationSummary {
  id: string;
  title: string;
  notebookId?: string | null;
  messageCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationItem {
  id: string;
  title: string;
  notebookId?: string | null;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

export interface NoteItem {
  id: string;
  notebookId?: string | null;
  title: string;
  content: string;
  noteType: NoteType;
  sourceDocumentIds: string[];
  createdAt: string;
  updatedAt: string;
}

export interface StudioGenerateResponse {
  title: string;
  content: string;
  type: StudioGenerateType;
  generationMode: GenerationMode;
  modelUsed?: string | null;
  note?: NoteItem | null;
}

export interface SourceGuideResponse {
  documentId: string;
  documentTitle: string;
  summary: string;
  keyTopics: string[];
  suggestedQuestions: string[];
  chunkCount: number;
  generationMode: GenerationMode;
  modelUsed?: string | null;
}
