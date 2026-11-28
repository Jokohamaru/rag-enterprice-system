import { useEffect, useRef, useState } from 'react';
import { BookMarked, ChevronDown, ChevronUp, ExternalLink, Sparkles, X } from 'lucide-react';
import type { CitationItem, NoteItem, StudioGenerateType } from '../types/rag';
import { StudioPanel } from './StudioPanel';

interface SourceInspectorProps {
  activeTab: 'citations' | 'studio';
  onChangeTab: (tab: 'citations' | 'studio') => void;
  citations: CitationItem[];
  selectedCitationId: string | null;
  onSelectCitation: (citationId: string) => void;
  onInspectDocument?: (documentId: string) => void;
  notes: NoteItem[];
  enabledDocCount: number;
  isGeneratingStudio: boolean;
  generatingStudioType: StudioGenerateType | null;
  onGenerateStudio: (type: StudioGenerateType) => void;
  onCreateManualNote: (title: string, content: string) => Promise<void>;
  onDeleteNote: (noteId: string) => Promise<void>;
  isOpenDrawer: boolean;
  onCloseDrawer: () => void;
}

function renderHighlightedExcerpt(content: string, highlight?: string | null) {
  if (!highlight) return content;
  const idx = content.toLowerCase().indexOf(highlight.toLowerCase());
  if (idx === -1) return content;

  const before = content.slice(0, idx);
  const match = content.slice(idx, idx + highlight.length);
  const after = content.slice(idx + highlight.length);

  return (
    <>
      {before}
      <mark className="chunk-highlight">{match}</mark>
      {after}
    </>
  );
}

export function SourceInspector({
  activeTab,
  onChangeTab,
  citations,
  selectedCitationId,
  onSelectCitation,
  onInspectDocument,
  notes,
  enabledDocCount,
  isGeneratingStudio,
  generatingStudioType,
  onGenerateStudio,
  onCreateManualNote,
  onDeleteNote,
  isOpenDrawer,
  onCloseDrawer,
}: SourceInspectorProps) {
  const itemRefs = useRef<Record<string, HTMLElement | null>>({});
  const [expandedParents, setExpandedParents] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (activeTab === 'citations' && selectedCitationId && itemRefs.current[selectedCitationId]) {
      itemRefs.current[selectedCitationId]?.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      });
    }
  }, [activeTab, selectedCitationId]);

  const toggleParent = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedParents((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <aside
      className={`inspector-pane ${isOpenDrawer ? 'open' : ''}`}
      aria-label="Nguồn trích dẫn & Studio"
    >
      <div className="inspector-header">
        <div className="inspector-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'citations'}
            className={`inspector-tab ${activeTab === 'citations' ? 'active' : ''}`}
            onClick={() => onChangeTab('citations')}
          >
            <BookMarked size={14} />
            <span>Trích dẫn</span>
            {citations.length > 0 && <span className="tab-badge">{citations.length}</span>}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'studio'}
            className={`inspector-tab ${activeTab === 'studio' ? 'active' : ''}`}
            onClick={() => onChangeTab('studio')}
          >
            <Sparkles size={14} />
            <span>Studio</span>
            {notes.length > 0 && <span className="tab-badge">{notes.length}</span>}
          </button>
        </div>

        {isOpenDrawer && (
          <button
            type="button"
            className="icon-btn inspector-drawer-only"
            onClick={onCloseDrawer}
            aria-label="Đóng khung bên phải"
          >
            <X size={15} />
          </button>
        )}
      </div>

      <div className="inspector-scroll">
        {activeTab === 'studio' ? (
          <StudioPanel
            notes={notes}
            enabledDocCount={enabledDocCount}
            isGenerating={isGeneratingStudio}
            generatingType={generatingStudioType}
            onGenerateStudio={onGenerateStudio}
            onCreateManualNote={onCreateManualNote}
            onDeleteNote={onDeleteNote}
          />
        ) : citations.length === 0 ? (
          <div className="inspector-empty">
            <h3 className="inspector-empty-title">Đối chiếu nguyên văn</h3>
            <p>
              Khi hệ thống trả lời, các đoạn tài liệu gốc kèm độ liên quan sẽ hiển thị tại đây.
              Di chuột hoặc nhấn vào từng số chú thích [1], [2]... để kiểm chứng nhanh.
            </p>
          </div>
        ) : (
          <div className="chunk-list">
            {citations.map((item) => {
              const isSelected = item.id === selectedCitationId;
              const scorePct = Math.round(item.score * 100);
              const isParentExpanded = expandedParents.has(item.id);
              const textToShow =
                isParentExpanded && item.parentContent ? item.parentContent : item.content;

              return (
                <article
                  key={item.id}
                  ref={(el) => {
                    itemRefs.current[item.id] = el;
                  }}
                  className={`chunk-entry ${isSelected ? 'selected' : ''}`}
                  onClick={() => onSelectCitation(item.id)}
                >
                  <div className="chunk-top">
                    <div className="chunk-badge-title">
                      <span className="chunk-num">{item.citationNumber}</span>
                      <h3 className="chunk-doc-title">{item.documentTitle}</h3>
                    </div>

                    <div className="chunk-score-box" title="Điểm liên quan tổng hợp">
                      <span className="chunk-score-val">{item.score.toFixed(2)}</span>
                      <div className="score-bar-track" aria-hidden="true">
                        <div className="score-bar-fill" style={{ width: `${scorePct}%` }} />
                      </div>
                    </div>
                  </div>

                  <div className="chunk-meta-line">
                    <span>{item.section}</span>
                    {item.page != null && <span>Trang {item.page}</span>}
                    <span className="doc-mono">Đoạn #{item.chunkIndex}</span>
                    {item.usedInAnswer === false && (
                      <span className="ref-only-tag">Tham khảo thêm</span>
                    )}
                  </div>

                  <p className="chunk-excerpt">
                    “{renderHighlightedExcerpt(textToShow, item.highlight)}”
                  </p>

                  <div className="chunk-footer-actions">
                    {item.parentContent && (
                      <button
                        type="button"
                        className="text-link-btn"
                        onClick={(e) => toggleParent(item.id, e)}
                      >
                        {isParentExpanded ? (
                          <>
                            <ChevronUp size={12} style={{ verticalAlign: -2 }} /> Thu gọn ngữ cảnh
                          </>
                        ) : (
                          <>
                            <ChevronDown size={12} style={{ verticalAlign: -2 }} /> Mở rộng ngữ cảnh
                          </>
                        )}
                      </button>
                    )}

                    {onInspectDocument && (
                      <button
                        type="button"
                        className="text-link-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          onInspectDocument(item.documentId);
                        }}
                      >
                        <ExternalLink size={11} style={{ verticalAlign: -1, marginRight: 3 }} />
                        Xem Source Guide
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
