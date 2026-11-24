import { useMemo } from 'react';
import { BookOpen, FileText, MessageSquare, Plus, RefreshCw } from 'lucide-react';
import { apiBaseUrl, isMockMode } from '../api/ragClient';
import type { ConnectionState, DocumentCategory, DocumentItem, HealthResponse } from '../types/rag';

const DEFAULT_CATEGORIES: DocumentCategory[] = ['Nhân sự', 'Vận hành', 'Kỹ thuật & IT'];

interface SidebarProps {
  activeView: 'chat' | 'library';
  onSelectView: (view: 'chat' | 'library') => void;
  onNewChat: () => void;
  documents: DocumentItem[];
  onToggleCategory: (category: DocumentCategory | string) => void;
  onEnableAllDocuments: () => void;
  connectionState: ConnectionState;
  healthInfo: HealthResponse | null;
  onRetryConnection: () => void;
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
  connectionState,
  healthInfo,
  onRetryConnection,
  isOpenMobile,
  onCloseMobile,
}: SidebarProps) {
  const readyDocs = documents.filter((d) => d.status === 'ready');
  const enabledCount = readyDocs.filter((d) => d.enabled).length;

  const categories = useMemo(() => {
    const extra = documents
      .map((d) => d.category)
      .filter((c): c is string => Boolean(c) && !DEFAULT_CATEGORIES.includes(c as DocumentCategory));
    return [...DEFAULT_CATEGORIES, ...Array.from(new Set(extra))];
  }, [documents]);

  const statusLabel = isMockMode
    ? 'Chế độ dữ liệu mẫu'
    : connectionState === 'connected'
      ? 'Đã kết nối Backend'
      : connectionState === 'degraded'
        ? 'Backend chạy (DB lỗi)'
        : connectionState === 'checking'
          ? 'Đang kiểm tra kết nối...'
          : 'Mất kết nối Backend';

  const statusDotClass = isMockMode ? 'connected' : connectionState;

  const connectionDetail = isMockMode
    ? 'Sẵn sàng nối FastAPI qua .env'
    : healthInfo
      ? `${healthInfo.embedding_provider} · ${healthInfo.vectordb.vector_mode ?? healthInfo.vectordb.backend}`
      : apiBaseUrl;

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
          {categories.map((category) => {
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
        <div className="connection-row">
          <div className="connection-status">
            <span className={`status-dot ${statusDotClass}`} aria-hidden="true" />
            <span>{statusLabel}</span>
          </div>
          {!isMockMode && (
            <button
              type="button"
              className="retry-link-btn"
              onClick={onRetryConnection}
              disabled={connectionState === 'checking'}
              title="Kiểm tra lại kết nối và tải lại dữ liệu"
            >
              <RefreshCw size={12} className={connectionState === 'checking' ? 'spin' : ''} />
              <span>Thử lại</span>
            </button>
          )}
        </div>
        <div className="connection-detail" title={isMockMode ? 'VITE_USE_MOCK=true' : apiBaseUrl}>
          {connectionDetail}
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
