import { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  BookMarked,
  BookmarkPlus,
  Check,
  Copy,
  Loader2,
  Send,
  Sparkles,
} from 'lucide-react';
import { SAMPLE_QUESTIONS } from '../data/mockData';
import type { ChatMessage, CitationItem, NotebookItem } from '../types/rag';
import { renderMarkdown } from '../utils/markdown';

interface ChatViewProps {
  messages: ChatMessage[];
  isQuerying: boolean;
  enabledDocCount: number;
  selectedCitationId: string | null;
  activeNotebook: NotebookItem | null;
  overviewText: string;
  overviewQuestions: string[];
  isGeneratingOverview: boolean;
  onGenerateOverview: () => void;
  onSendQuestion: (question: string) => void;
  onSelectCitation: (messageId: string, citation: CitationItem) => void;
  onPinNote: (message: ChatMessage) => void;
  onOpenLibrary: () => void;
  onOpenInspectorDrawer: () => void;
  activeCitationsCount: number;
}

export function ChatView({
  messages,
  isQuerying,
  enabledDocCount,
  selectedCitationId,
  activeNotebook,
  overviewText,
  overviewQuestions,
  isGeneratingOverview,
  onGenerateOverview,
  onSendQuestion,
  onSelectCitation,
  onPinNote,
  onOpenLibrary,
  onOpenInspectorDrawer,
  activeCitationsCount,
}: ChatViewProps) {
  const [input, setInput] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(() => new Set());
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

  const handleCopy = async (msg: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopiedId(msg.id);
      setTimeout(() => setCopiedId((cur) => (cur === msg.id ? null : cur)), 1600);
    } catch {
      // Ignore clipboard failure
    }
  };

  const handlePin = (msg: ChatMessage) => {
    onPinNote(msg);
    setPinnedIds((prev) => new Set(prev).add(msg.id));
  };

  const starterItems =
    overviewQuestions.length > 0
      ? overviewQuestions.map((q, idx) => ({
          label: `Gợi ý #${idx + 1}`,
          question: q,
        }))
      : SAMPLE_QUESTIONS;

  return (
    <main className="main-stage">
      <header className="stage-header">
        <div className="stage-header-info">
          <h2 className="stage-title">
            {activeNotebook ? activeNotebook.title : 'Hỏi đáp tài liệu'}
          </h2>
          <span className="stage-subtitle">
            {enabledDocCount > 0
              ? `Đang tra cứu trên ${enabledDocCount} tài liệu nội bộ`
              : 'Chưa có tài liệu nào được bật trong phạm vi tra cứu'}
          </span>
        </div>

        <button
          type="button"
          className="icon-btn inspector-drawer-only"
          onClick={onOpenInspectorDrawer}
          title="Mở khung nguồn & Studio"
        >
          <BookMarked size={15} />
          <span>Nguồn ({activeCitationsCount})</span>
        </button>
      </header>

      <div className="chat-scroll">
        <div className="chat-inner">
          {messages.length === 0 ? (
            <section className="empty-reading-room" aria-label="Bắt đầu tra cứu">
              <h2 className="empty-headline">
                Tra cứu quy định và tài liệu nội bộ có dẫn nguồn rõ ràng.
              </h2>
              <p className="empty-lead">
                Đặt câu hỏi bằng tiếng Việt tự nhiên. Hệ thống kết hợp tìm kiếm ngữ nghĩa + từ khóa,
                xếp hạng lại và gọi AI tổng hợp kèm trích dẫn từng đoạn nguyên văn.
              </p>

              {enabledDocCount > 0 && (
                <div className="overview-box">
                  <div className="overview-box-head">
                    <span className="overview-box-title">
                      <Sparkles size={14} />
                      <span>Tổng quan nhanh các nguồn đang chọn</span>
                    </span>
                    <button
                      type="button"
                      className="text-link-btn"
                      disabled={isGeneratingOverview}
                      onClick={onGenerateOverview}
                    >
                      {isGeneratingOverview ? (
                        <>
                          <Loader2 size={12} className="spin" style={{ verticalAlign: -2 }} /> Đang tạo...
                        </>
                      ) : overviewText ? (
                        'Làm mới tổng quan'
                      ) : (
                        'Tạo tổng quan AI'
                      )}
                    </button>
                  </div>
                  {overviewText && (
                    <div className="overview-box-body assistant-prose">
                      {renderMarkdown(overviewText)}
                    </div>
                  )}
                </div>
              )}

              <div className="starter-grid">
                {starterItems.map((item) => (
                  <button
                    key={item.question}
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
              {messages.map((msg, msgIdx) => {
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

                const isLastAssistant = msgIdx === messages.length - 1;

                return (
                  <article key={msg.id} className="message-block">
                    <div className="message-role-row">
                      <div className="message-role-left">
                        <span className="message-role assistant">Tổng hợp từ kho tài liệu</span>
                        {msg.modelUsed && (
                          <span
                            className={`model-mini-badge ${
                              msg.generationMode === 'extractive_fallback' ? 'fallback' : ''
                            }`}
                          >
                            {msg.generationMode === 'extractive_fallback'
                              ? 'Trích xuất dự phòng'
                              : msg.modelUsed}
                          </span>
                        )}
                      </div>
                      <span className="message-meta">
                        {msg.latencyMs ? `${(msg.latencyMs / 1000).toFixed(2)}s` : msg.createdAt}
                      </span>
                    </div>

                    {msg.warning && (
                      <div className="warning-banner">
                        <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} />
                        <span>{msg.warning}</span>
                      </div>
                    )}

                    {msg.error ? (
                      <div className="error-banner">{msg.error}</div>
                    ) : (
                      <>
                        {msg.isStreaming && msg.statusText && !msg.content && (
                          <div className="loading-pulse">
                            <span className="loading-dot" aria-hidden="true" />
                            <span>{msg.statusText}</span>
                          </div>
                        )}

                        {msg.content && (
                          <div className={`assistant-prose ${msg.isStreaming ? 'streaming' : ''}`}>
                            {renderMarkdown(msg.content, {
                              citations: msg.citations,
                              selectedCitationId,
                              messageId: msg.id,
                              onSelectCitation,
                            })}
                          </div>
                        )}

                        {!msg.isStreaming && msg.content && (
                          <div className="answer-action-row">
                            <button
                              type="button"
                              className="answer-action-btn"
                              onClick={() => handlePin(msg)}
                            >
                              {pinnedIds.has(msg.id) ? (
                                <>
                                  <Check size={13} />
                                  <span>Đã lưu ghi chú</span>
                                </>
                              ) : (
                                <>
                                  <BookmarkPlus size={13} />
                                  <span>Ghim ghi chú</span>
                                </>
                              )}
                            </button>

                            <button
                              type="button"
                              className="answer-action-btn"
                              onClick={() => void handleCopy(msg)}
                            >
                              {copiedId === msg.id ? (
                                <>
                                  <Check size={13} />
                                  <span>Đã sao chép</span>
                                </>
                              ) : (
                                <>
                                  <Copy size={13} />
                                  <span>Sao chép</span>
                                </>
                              )}
                            </button>
                          </div>
                        )}

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
                                    {cit.page != null ? ` (Tr. ${cit.page})` : ''}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        )}

                        {isLastAssistant &&
                          !msg.isStreaming &&
                          msg.followUpQuestions &&
                          msg.followUpQuestions.length > 0 && (
                            <div className="follow-up-box">
                              <span className="follow-up-label">Câu hỏi tiếp theo gợi ý:</span>
                              <div className="follow-up-row">
                                {msg.followUpQuestions.map((fq) => (
                                  <button
                                    key={fq}
                                    type="button"
                                    className="follow-up-chip"
                                    disabled={isQuerying || enabledDocCount === 0}
                                    onClick={() => onSendQuestion(fq)}
                                  >
                                    {fq}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                      </>
                    )}
                  </article>
                );
              })}

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
                ? 'Đặt câu hỏi về tài liệu đang chọn (hỗ trợ hỏi nối tiếp nhiều lượt)...'
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
              <span>{isQuerying ? 'Đang trả lời...' : 'Gửi câu hỏi'}</span>
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
