import { useEffect, useRef, useState } from 'react';
import { BookMarked, Send } from 'lucide-react';
import { SAMPLE_QUESTIONS } from '../data/mockData';
import type { ChatMessage, CitationItem } from '../types/rag';

interface ChatViewProps {
  messages: ChatMessage[];
  isQuerying: boolean;
  enabledDocCount: number;
  selectedCitationId: string | null;
  onSendQuestion: (question: string) => void;
  onSelectCitation: (messageId: string, citation: CitationItem) => void;
  onOpenLibrary: () => void;
  onOpenInspectorDrawer: () => void;
  activeCitationsCount: number;
}

function renderFormattedParagraph(
  text: string,
  citations: CitationItem[] | undefined,
  selectedCitationId: string | null,
  messageId: string,
  onSelectCitation: (messageId: string, citation: CitationItem) => void
) {
  // Split by **bold** or [number] inline citation markers
  const parts = text.split(/(\*\*[^*]+\*\*|\[\d+\])/g);

  return parts.map((part, idx) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={idx}>{part.slice(2, -2)}</strong>;
    }

    const citationMatch = part.match(/^\[(\d+)\]$/);
    if (citationMatch && citations) {
      const num = Number(citationMatch[1]);
      const found = citations.find((c) => c.citationNumber === num);
      if (found) {
        const isActive = selectedCitationId === found.id;
        return (
          <button
            key={idx}
            type="button"
            className={`citation-chip ${isActive ? 'active' : ''}`}
            onClick={() => onSelectCitation(messageId, found)}
            title={`Xem nguồn [${num}]: ${found.documentTitle}`}
          >
            {num}
          </button>
        );
      }
    }

    return <span key={idx}>{part}</span>;
  });
}

export function ChatView({
  messages,
  isQuerying,
  enabledDocCount,
  selectedCitationId,
  onSendQuestion,
  onSelectCitation,
  onOpenLibrary,
  onOpenInspectorDrawer,
  activeCitationsCount,
}: ChatViewProps) {
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isQuerying]);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isQuerying || enabledDocCount === 0) return;
    onSendQuestion(trimmed);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  };

  return (
    <main className="main-stage">
      <header className="stage-header">
        <div className="stage-header-info">
          <h2 className="stage-title">Hỏi đáp tài liệu</h2>
          <span className="stage-subtitle">
            {enabledDocCount > 0
              ? `Đang tra cứu trên ${enabledDocCount} tài liệu nội bộ`
              : 'Chưa có tài liệu nào được bật trong phạm vi tra cứu'}
          </span>
        </div>

        {activeCitationsCount > 0 && (
          <button
            type="button"
            className="icon-btn inspector-drawer-only"
            onClick={onOpenInspectorDrawer}
            title="Mở khung đối chiếu nguồn trích dẫn"
          >
            <BookMarked size={15} />
            <span>Nguồn ({activeCitationsCount})</span>
          </button>
        )}
      </header>

      <div className="chat-scroll">
        <div className="chat-inner">
          {messages.length === 0 ? (
            <section className="empty-reading-room" aria-label="Bắt đầu tra cứu">
              <h2 className="empty-headline">
                Tra cứu quy định và tài liệu nội bộ có dẫn nguồn rõ ràng.
              </h2>
              <p className="empty-lead">
                Đặt câu hỏi bằng tiếng Việt tự nhiên. Hệ thống sẽ tổng hợp câu trả lời từ kho tài
                liệu đang chọn và gắn số chú thích dẫn thẳng tới từng đoạn nguyên văn.
              </p>

              <div className="starter-grid">
                {SAMPLE_QUESTIONS.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    className="starter-item"
                    disabled={enabledDocCount === 0}
                    onClick={() => onSendQuestion(item.question)}
                  >
                    <span className="starter-topic">{item.label}</span>
                    <span className="starter-question">{item.question}</span>
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="message-list" role="log" aria-live="polite">
              {messages.map((msg) => {
                if (msg.role === 'user') {
                  return (
                    <article key={msg.id} className="message-block message-user">
                      <div className="message-role-row">
                        <span className="message-role">Câu hỏi của bạn</span>
                        <span className="message-meta">{msg.createdAt}</span>
                      </div>
                      <p className="user-query-text">{msg.content}</p>
                    </article>
                  );
                }

                const paragraphs = msg.content.split(/\n\n+/).filter(Boolean);

                return (
                  <article key={msg.id} className="message-block">
                    <div className="message-role-row">
                      <span className="message-role assistant">Tổng hợp từ kho tài liệu</span>
                      <span className="message-meta">
                        {msg.latencyMs ? `${(msg.latencyMs / 1000).toFixed(2)}s` : msg.createdAt}
                      </span>
                    </div>

                    {msg.error ? (
                      <div className="error-banner">{msg.error}</div>
                    ) : (
                      <>
                        <div className="assistant-prose">
                          {paragraphs.map((para, pIdx) => (
                            <p key={pIdx}>
                              {renderFormattedParagraph(
                                para,
                                msg.citations,
                                selectedCitationId,
                                msg.id,
                                onSelectCitation
                              )}
                            </p>
                          ))}
                        </div>

                        {msg.citations && msg.citations.length > 0 && (
                          <div className="answer-sources-bar" aria-label="Tài liệu đã trích dẫn">
                            {msg.citations.map((cit) => {
                              const isActive = selectedCitationId === cit.id;
                              return (
                                <button
                                  key={cit.id}
                                  type="button"
                                  className={`source-pill-btn ${isActive ? 'active' : ''}`}
                                  onClick={() => onSelectCitation(msg.id, cit)}
                                >
                                  <span className="source-pill-num">[{cit.citationNumber}]</span>
                                  <span className="source-pill-title">
                                    {cit.documentTitle}
                                    {cit.page !== undefined ? ` (Tr. ${cit.page})` : ''}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </>
                    )}
                  </article>
                );
              })}

              {isQuerying && (
                <div className="loading-pulse">
                  <span className="loading-dot" aria-hidden="true" />
                  <span>Đang truy xuất đoạn văn bản liên quan và tổng hợp câu trả lời...</span>
                </div>
              )}

              <div ref={endRef} />
            </div>
          )}
        </div>
      </div>

      <div className="composer-dock">
        <form className="composer-box" onSubmit={handleSubmit}>
          <textarea
            ref={textareaRef}
            className="composer-textarea"
            rows={1}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isQuerying || enabledDocCount === 0}
            placeholder={
              enabledDocCount > 0
                ? 'Đặt câu hỏi về chính sách nghỉ phép, hoàn ứng công tác, VPN hoặc quy trình nội bộ...'
                : 'Hãy bật ít nhất một tài liệu ở thanh bên trái để bắt đầu tra cứu.'
            }
          />
          <div className="composer-footer">
            <span className="composer-hint">
              {enabledDocCount > 0 ? (
                <>Enter để gửi, Shift + Enter để xuống dòng</>
              ) : (
                <button type="button" className="text-link-btn" onClick={onOpenLibrary}>
                  Mở Thư viện tài liệu để quản lý nguồn
                </button>
              )}
            </span>

            <button
              type="submit"
              className="send-btn"
              disabled={!input.trim() || isQuerying || enabledDocCount === 0}
            >
              <Send size={14} />
              <span>Gửi câu hỏi</span>
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
