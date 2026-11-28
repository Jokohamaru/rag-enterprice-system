import { useEffect, useState } from 'react';
import { BookOpen, Loader2, MessageSquare, Search, Sparkles, X } from 'lucide-react';
import { fetchDocumentChunks, fetchDocumentGuide } from '../api/ragClient';
import type { DocumentChunk, DocumentItem, SourceGuideResponse } from '../types/rag';

interface SourceGuideModalProps {
  document: DocumentItem | null;
  onClose: () => void;
  onAskQuestion: (question: string) => void;
}

export function SourceGuideModal({
  document,
  onClose,
  onAskQuestion,
}: SourceGuideModalProps) {
  const [guide, setGuide] = useState<SourceGuideResponse | null>(null);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chunkSearch, setChunkSearch] = useState('');

  useEffect(() => {
    if (!document) {
      setGuide(null);
      setChunks([]);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setChunkSearch('');

    Promise.all([fetchDocumentGuide(document.id), fetchDocumentChunks(document.id)])
      .then(([g, ch]) => {
        if (cancelled) return;
        setGuide(g);
        setChunks(ch);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Không thể tải chi tiết tài liệu.');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [document]);

  if (!document) return null;

  const filteredChunks = chunks.filter((c) => {
    const q = chunkSearch.trim().toLowerCase();
    if (!q) return true;
    return c.content.toLowerCase().includes(q) || c.section.toLowerCase().includes(q);
  });

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Source Guide">
      <div className="guide-modal">
        <header className="guide-modal-header">
          <div className="guide-modal-title-wrap">
            <span className="doc-category-tag">{document.category}</span>
            <h2 className="guide-modal-title">{document.title}</h2>
            <span className="guide-modal-sub">
              {document.filename} · {document.sizeLabel} · {document.chunkCount} đoạn
            </span>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Đóng">
            <X size={16} />
          </button>
        </header>

        <div className="guide-modal-body">
          {isLoading ? (
            <div className="loading-pulse" style={{ padding: '24px 0' }}>
              <Loader2 size={16} className="spin" />
              <span>Đang tạo Source Guide và tải các đoạn nội dung...</span>
            </div>
          ) : error ? (
            <div className="error-banner">{error}</div>
          ) : (
            <>
              {guide && (
                <section className="guide-summary-card">
                  <div className="guide-card-label">
                    <Sparkles size={14} />
                    <span>Source Guide (Tóm tắt nguồn)</span>
                    {guide.modelUsed && (
                      <span className="model-mini-badge">{guide.modelUsed}</span>
                    )}
                  </div>
                  <p className="guide-summary-text">{guide.summary}</p>

                  {guide.keyTopics.length > 0 && (
                    <div className="guide-topics">
                      {guide.keyTopics.map((topic) => (
                        <span key={topic} className="topic-chip">
                          {topic}
                        </span>
                      ))}
                    </div>
                  )}

                  {guide.suggestedQuestions.length > 0 && (
                    <div className="guide-questions">
                      <span className="guide-questions-label">Câu hỏi gợi ý cho nguồn này:</span>
                      <div className="follow-up-row">
                        {guide.suggestedQuestions.map((q) => (
                          <button
                            key={q}
                            type="button"
                            className="follow-up-chip"
                            onClick={() => {
                              onAskQuestion(q);
                              onClose();
                            }}
                          >
                            <MessageSquare size={12} />
                            <span>{q}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </section>
              )}

              <section className="guide-chunks-section">
                <div className="guide-chunks-head">
                  <h3 className="guide-chunks-title">
                    <BookOpen size={14} />
                    <span>Các đoạn đã lập chỉ mục ({filteredChunks.length})</span>
                  </h3>
                  <div className="search-input-wrap" style={{ maxWidth: 260 }}>
                    <Search size={14} className="search-icon" />
                    <input
                      type="search"
                      className="search-input"
                      style={{ height: 32, fontSize: 12.5 }}
                      placeholder="Lọc trong tài liệu..."
                      value={chunkSearch}
                      onChange={(e) => setChunkSearch(e.target.value)}
                    />
                  </div>
                </div>

                <div className="guide-chunk-list">
                  {filteredChunks.map((ch) => (
                    <article key={ch.id} className="guide-chunk-item">
                      <div className="chunk-meta-line" style={{ marginBottom: 4 }}>
                        <span className="doc-mono">#{ch.chunkIndex}</span>
                        <span>{ch.section}</span>
                        {ch.page != null && <span>Trang {ch.page}</span>}
                      </div>
                      <p className="chunk-excerpt">{ch.content}</p>
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
