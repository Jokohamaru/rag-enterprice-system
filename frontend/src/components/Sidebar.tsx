import { useMemo, useState } from 'react';
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  Info,
  MessageSquare,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { apiBaseUrl, isMockMode } from '../api/ragClient';
import type {
  ConnectionState,
  ConversationSummary,
  DocumentCategory,
  DocumentItem,
  HealthResponse,
  NotebookItem,
} from '../types/rag';

const DEFAULT_CATEGORIES: DocumentCategory[] = ['Nhân sự', 'Vận hành', 'Kỹ thuật & IT'];

interface SidebarProps {
  activeView: 'chat' | 'library';
  onSelectView: (view: 'chat' | 'library') => void;
  onNewChat: () => void;
  documents: DocumentItem[];
  onToggleCategory: (category: DocumentCategory | string) => void;
  onToggleDocument: (documentId: string) => void;
  onEnableAllDocuments: () => void;
  onInspectDocument: (document: DocumentItem) => void;
  notebooks: NotebookItem[];
  activeNotebookId: string | null;
  onSelectNotebook: (notebookId: string | null) => void;
  onCreateNotebook: (title: string) => Promise<void>;
  onDeleteNotebook: (notebookId: string) => Promise<void>;
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  onSelectConversation: (conversationId: string) => void;
  onDeleteConversation: (conversationId: string) => Promise<void>;
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
  onToggleDocument,
  onEnableAllDocuments,
  onInspectDocument,
  notebooks,
  activeNotebookId,
  onSelectNotebook,
  onCreateNotebook,
  onDeleteNotebook,
  conversations,
  activeConversationId,
  onSelectConversation,
  onDeleteConversation,
  connectionState,
  healthInfo,
  onRetryConnection,
  isOpenMobile,
  onCloseMobile,
}: SidebarProps) {
  const [expandedCats, setExpandedCats] = useState<Set<string>>(() => new Set(DEFAULT_CATEGORIES));
  const [showNbForm, setShowNbForm] = useState(false);
  const [newNbTitle, setNewNbTitle] = useState('');
  const [isCreatingNb, setIsCreatingNb] = useState(false);

  const readyDocs = documents.filter((d) => d.status === 'ready');
  const activeNotebook = notebooks.find((n) => n.id === activeNotebookId) ?? null;

  const isDocActiveInScope = (doc: DocumentItem): boolean => {
    if (!doc.enabled || doc.status !== 'ready') return false;
    if (activeNotebook) {
      return activeNotebook.documentIds.includes(doc.id);
    }
    return true;
  };

  const enabledCount = readyDocs.filter(isDocActiveInScope).length;

  const categories = useMemo(() => {
    const extra = documents
      .map((d) => d.category)
      .filter((c): c is string => Boolean(c) && !DEFAULT_CATEGORIES.includes(c as DocumentCategory));
    return [...DEFAULT_CATEGORIES, ...Array.from(new Set(extra))];
  }, [documents]);

  const toggleExpandCategory = (cat: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const handleNotebookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNbTitle.trim() || isCreatingNb) return;
    setIsCreatingNb(true);
    try {
      await onCreateNotebook(newNbTitle.trim());
      setNewNbTitle('');
      setShowNbForm(false);
    } finally {
      setIsCreatingNb(false);
    }
  };

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

  const llmSummary = healthInfo?.llm_configured
    ? `${healthInfo.llm_model || healthInfo.llm_provider}`
    : healthInfo
      ? 'LLM chưa cấu hình'
      : '';

  const connectionDetail = isMockMode
    ? 'Sẵn sàng nối FastAPI qua .env'
    : healthInfo
      ? `${llmSummary} · emb:${healthInfo.embedding_provider}`
      : apiBaseUrl;

  return (
    <aside className={`sidebar ${isOpenMobile ? 'open' : ''}`} aria-label="Điều hướng chính">
      <div className="sidebar-brand">
        <h1 className="brand-title">Kho Tri Thức</h1>
        <span className="brand-edition">NotebookLM</span>
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

      {/* Notebooks switcher */}
      <section className="sidebar-section" aria-label="Notebooks">
        <div className="sidebar-section-header">
          <h2 className="sidebar-section-title">Notebooks</h2>
          <button
            type="button"
            className="text-link-btn"
            onClick={() => setShowNbForm((p) => !p)}
          >
            {showNbForm ? 'Hủy' : '+ Tạo mới'}
          </button>
        </div>

        {showNbForm && (
          <form className="nb-create-form" onSubmit={handleNotebookSubmit}>
            <input
              type="text"
              className="nb-input"
              placeholder="Tên Notebook..."
              value={newNbTitle}
              onChange={(e) => setNewNbTitle(e.target.value)}
            />
            <button type="submit" className="nb-add-btn" disabled={!newNbTitle.trim() || isCreatingNb}>
              Lưu
            </button>
          </form>
        )}

        <div className="nb-list">
          <button
            type="button"
            className={`nb-item ${activeNotebookId === null ? 'active' : ''}`}
            onClick={() => onSelectNotebook(null)}
          >
            <span className="nb-item-left">
              <FolderOpen size={13} />
              <span>Tất cả nguồn tài liệu</span>
            </span>
          </button>

          {notebooks.map((nb) => (
            <div key={nb.id} className={`nb-item-row ${activeNotebookId === nb.id ? 'active' : ''}`}>
              <button
                type="button"
                className="nb-item-btn"
                onClick={() => onSelectNotebook(nb.id)}
                title={nb.title}
              >
                <FolderOpen size={13} />
                <span className="nb-item-name">{nb.title}</span>
                <span className="scope-count">{nb.documentIds.length}</span>
              </button>
              <button
                type="button"
                className="icon-mini-btn danger"
                onClick={() => void onDeleteNotebook(nb.id)}
                title="Xóa Notebook"
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Sources Tree */}
      <section className="sidebar-section" aria-label="Nguồn tài liệu">
        <div className="sidebar-section-header">
          <h2 className="sidebar-section-title">Nguồn ({enabledCount}/{readyDocs.length})</h2>
          <div style={{ display: 'flex', gap: 8 }}>
            {enabledCount < readyDocs.length && !activeNotebook && (
              <button type="button" className="text-link-btn" onClick={onEnableAllDocuments}>
                Bật hết
              </button>
            )}
            <button
              type="button"
              className="text-link-btn"
              onClick={() => {
                onSelectView('library');
                onCloseMobile();
              }}
            >
              + Thêm
            </button>
          </div>
        </div>

        <div className="scope-list">
          {categories.map((category) => {
            const catDocs = readyDocs.filter((d) => d.category === category);
            const activeInCat = catDocs.filter(isDocActiveInScope).length;
            const isChecked = catDocs.length > 0 && activeInCat > 0;
            const isExpanded = expandedCats.has(category);

            return (
              <div key={category} className="scope-group">
                <div className="scope-row">
                  <div className="scope-row-left">
                    <button
                      type="button"
                      className="cat-expand-btn"
                      onClick={() => toggleExpandCategory(category)}
                      aria-label={`Mở rộng ${category}`}
                    >
                      {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    </button>
                    <input
                      type="checkbox"
                      className="scope-checkbox"
                      checked={isChecked}
                      disabled={catDocs.length === 0}
                      onChange={() => onToggleCategory(category)}
                    />
                    <span
                      className="scope-cat-label"
                      onClick={() => toggleExpandCategory(category)}
                    >
                      {category}
                    </span>
                  </div>
                  <span className="scope-count">
                    {activeInCat}/{catDocs.length}
                  </span>
                </div>

                {isExpanded && catDocs.length > 0 && (
                  <div className="scope-doc-list">
                    {catDocs.map((doc) => {
                      const docChecked = isDocActiveInScope(doc);
                      return (
                        <div key={doc.id} className="scope-doc-row">
                          <label className="scope-doc-label" title={doc.title}>
                            <input
                              type="checkbox"
                              className="scope-checkbox"
                              checked={docChecked}
                              onChange={() => onToggleDocument(doc.id)}
                            />
                            <span className="scope-doc-title">{doc.title}</span>
                          </label>
                          <button
                            type="button"
                            className="icon-mini-btn"
                            onClick={() => onInspectDocument(doc)}
                            title="Xem Source Guide"
                          >
                            <Info size={12} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Saved Conversations */}
      {conversations.length > 0 && (
        <section className="sidebar-section" aria-label="Lịch sử hội thoại">
          <div className="sidebar-section-header">
            <h2 className="sidebar-section-title">Lịch sử hỏi đáp</h2>
          </div>
          <div className="conv-list">
            {conversations.slice(0, 8).map((conv) => (
              <div
                key={conv.id}
                className={`nb-item-row ${activeConversationId === conv.id ? 'active' : ''}`}
              >
                <button
                  type="button"
                  className="nb-item-btn"
                  onClick={() => {
                    onSelectConversation(conv.id);
                    onCloseMobile();
                  }}
                  title={conv.title}
                >
                  <MessageSquare size={12} />
                  <span className="nb-item-name">{conv.title}</span>
                </button>
                <button
                  type="button"
                  className="icon-mini-btn danger"
                  onClick={() => void onDeleteConversation(conv.id)}
                  title="Xóa hội thoại"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

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
