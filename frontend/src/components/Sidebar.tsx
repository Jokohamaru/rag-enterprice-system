import { BookOpen, FileText, MessageSquare, Plus } from 'lucide-react';
import { apiBaseUrl, isMockMode } from '../api/ragClient';
import type { DocumentCategory, DocumentItem } from '../types/rag';

const CATEGORIES: DocumentCategory[] = ['Nhân sự', 'Vận hành', 'Kỹ thuật & IT'];

interface SidebarProps {
  activeView: 'chat' | 'library';
  onSelectView: (view: 'chat' | 'library') => void;
  onNewChat: () => void;
  documents: DocumentItem[];
  onToggleCategory: (category: DocumentCategory) => void;
  onEnableAllDocuments: () => void;
  isOpenMobile: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({
  activeView,
  onSelectView,
  onNewChat,
  documents,
  onToggleCategory,
  onEnableAllDocuments,
  isOpenMobile,
  onCloseMobile,
}: SidebarProps) {
  const readyDocs = documents.filter((d) => d.status === 'ready');
  const enabledCount = readyDocs.filter((d) => d.enabled).length;

  return (
    <aside className={`sidebar ${isOpenMobile ? 'open' : ''}`} aria-label="Điều hướng chính">
      <div className="sidebar-brand">
        <h1 className="brand-title">Kho Tri Thức</h1>
        <span className="brand-edition">Nội bộ</span>
      </div>

      <button
        type="button"
        className="new-chat-btn"
        onClick={() => {
          onNewChat();
          onCloseMobile();
        }}
      >
        <Plus size={16} strokeWidth={2} />
        <span>Cuộc hỏi mới</span>
      </button>

      <nav className="nav-group" aria-label="Chế độ làm việc">
        <button
          type="button"
          className={`nav-item ${activeView === 'chat' ? 'active' : ''}`}
          onClick={() => {
            onSelectView('chat');
            onCloseMobile();
          }}
        >
          <span className="nav-item-left">
            <MessageSquare size={16} strokeWidth={1.8} />
            <span>Hỏi đáp tài liệu</span>
          </span>
        </button>

        <button
          type="button"
          className={`nav-item ${activeView === 'library' ? 'active' : ''}`}
          onClick={() => {
            onSelectView('library');
            onCloseMobile();
          }}
        >
          <span className="nav-item-left">
            <FileText size={16} strokeWidth={1.8} />
            <span>Thư viện tài liệu</span>
          </span>
          <span className="nav-count">{documents.length}</span>
        </button>
      </nav>

      <section className="sidebar-section" aria-label="Phạm vi tra cứu">
        <div className="sidebar-section-header">
          <h2 className="sidebar-section-title">Phạm vi tra cứu</h2>
          {enabledCount < readyDocs.length && (
            <button type="button" className="text-link-btn" onClick={onEnableAllDocuments}>
              Chọn tất cả
            </button>
          )}
        </div>

        <div className="scope-list">
          {CATEGORIES.map((category) => {
            const catDocs = readyDocs.filter((d) => d.category === category);
            const activeInCat = catDocs.filter((d) => d.enabled).length;
            const isChecked = catDocs.length > 0 && activeInCat > 0;

            return (
              <label key={category} className="scope-row">
                <span className="scope-row-left">
                  <input
                    type="checkbox"
                    className="scope-checkbox"
                    checked={isChecked}
                    disabled={catDocs.length === 0}
                    onChange={() => onToggleCategory(category)}
                  />
                  <span>{category}</span>
                </span>
                <span className="scope-count">
                  {activeInCat}/{catDocs.length}
                </span>
              </label>
            );
          })}
        </div>
      </section>

      <div className="sidebar-footer">
        <div className="connection-status">
          <span className="status-dot" aria-hidden="true" />
          <span>{isMockMode ? 'Chế độ dữ liệu mẫu' : 'Đang kết nối API'}</span>
        </div>
        <div className="connection-detail" title={isMockMode ? 'VITE_USE_MOCK=true' : apiBaseUrl}>
          {isMockMode ? 'Sẵn sàng nối FastAPI qua .env' : apiBaseUrl}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
          <BookOpen size={12} />
          <span>
            {enabledCount} / {readyDocs.length} tài liệu đang bật
          </span>
        </div>
      </div>
    </aside>
  );
}
