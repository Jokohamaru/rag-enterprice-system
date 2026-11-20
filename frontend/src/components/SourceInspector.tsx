import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import type { CitationItem } from '../types/rag';

interface SourceInspectorProps {
  citations: CitationItem[];
  selectedCitationId: string | null;
  onSelectCitation: (citationId: string) => void;
  isOpenDrawer: boolean;
  onCloseDrawer: () => void;
}

function renderHighlightedExcerpt(content: string, highlight?: string) {
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
  citations,
  selectedCitationId,
  onSelectCitation,
  isOpenDrawer,
  onCloseDrawer,
}: SourceInspectorProps) {
  const itemRefs = useRef<Record<string, HTMLElement | null>>({});

  useEffect(() => {
    if (selectedCitationId && itemRefs.current[selectedCitationId]) {
      itemRefs.current[selectedCitationId]?.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      });
    }
  }, [selectedCitationId]);

  return (
    <aside
      className={`inspector-pane ${isOpenDrawer ? 'open' : ''}`}
      aria-label="Nguồn trích dẫn"
    >
      <div className="inspector-header">
        <div>
          <h2 className="inspector-title">Nguồn trích dẫn</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {citations.length > 0 && (
            <span className="inspector-count">{citations.length} đoạn</span>
          )}
          {isOpenDrawer && (
            <button
              type="button"
              className="icon-btn inspector-drawer-only"
              onClick={onCloseDrawer}
              aria-label="Đóng khung nguồn trích dẫn"
            >
              <X size={15} />
            </button>
          )}
        </div>
      </div>

      <div className="inspector-scroll">
        {citations.length === 0 ? (
          <div className="inspector-empty">
            <h3 className="inspector-empty-title">Đối chiếu nguyên văn</h3>
            <p>
              Khi hệ thống trả lời, các đoạn tài liệu gốc kèm độ tương đồng sẽ hiển thị tại đây.
              Nhấn vào từng số chú thích trong câu trả lời để kiểm chứng nhanh.
            </p>
          </div>
        ) : (
          <div className="chunk-list">
            {citations.map((item) => {
              const isSelected = item.id === selectedCitationId;
              const scorePct = Math.round(item.score * 100);

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

                    <div className="chunk-score-box" title="Độ tương đồng ngữ nghĩa">
                      <span className="chunk-score-val">{item.score.toFixed(2)}</span>
                      <div className="score-bar-track" aria-hidden="true">
                        <div
                          className="score-bar-fill"
                          style={{ width: `${scorePct}%` }}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="chunk-meta-line">
                    <span>{item.section}</span>
                    {item.page !== undefined && <span>Trang {item.page}</span>}
                    <span className="doc-mono">Đoạn #{item.chunkIndex}</span>
                  </div>

                  <p className="chunk-excerpt">
                    “{renderHighlightedExcerpt(item.content, item.highlight)}”
                  </p>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
