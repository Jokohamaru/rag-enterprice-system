import { useCallback, useEffect, useMemo, useState } from 'react';
import { BookMarked, Menu } from 'lucide-react';
import {
  deleteDocument as apiDeleteDocument,
  fetchDocuments,
  fetchHealth,
  isMockMode,
  queryRag,
  syncKnowledgeBase,
  updateDocumentEnabled,
  uploadDocument,
} from './api/ragClient';
import { ChatView } from './components/ChatView';
import { LibraryView } from './components/LibraryView';
import { Sidebar } from './components/Sidebar';
import { SourceInspector } from './components/SourceInspector';
import type {
  ChatMessage,
  CitationItem,
  ConnectionState,
  DocumentCategory,
  DocumentItem,
  HealthResponse,
} from './types/rag';

function formatTimeNow(): string {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

export function App() {
  const [activeView, setActiveView] = useState<'chat' | 'library'>('chat');
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);

  const [connectionState, setConnectionState] = useState<ConnectionState>(
    isMockMode ? 'connected' : 'checking'
  );
  const [healthInfo, setHealthInfo] = useState<HealthResponse | null>(null);
  const [isLoadingDocs, setIsLoadingDocs] = useState(true);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [deletingDocIds, setDeletingDocIds] = useState<Set<string>>(() => new Set());

  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);

  const loadBackendState = useCallback(async () => {
    setIsLoadingDocs(true);
    if (!isMockMode) {
      setConnectionState('checking');
    }

    const [healthRes, docsRes] = await Promise.allSettled([fetchHealth(), fetchDocuments()]);

    if (healthRes.status === 'fulfilled') {
      setHealthInfo(healthRes.value);
      setConnectionState(healthRes.value.status === 'ok' ? 'connected' : 'degraded');
    } else {
      setHealthInfo(null);
      setConnectionState('offline');
    }

    if (docsRes.status === 'fulfilled') {
      setDocuments(docsRes.value);
      setLibraryError(null);
    } else {
      const msg =
        docsRes.reason instanceof Error
          ? docsRes.reason.message
          : 'Không thể kết nối tới Backend để tải danh sách tài liệu.';
      setLibraryError(msg);
    }

    setIsLoadingDocs(false);
  }, []);

  useEffect(() => {
    void loadBackendState();
  }, [loadBackendState]);

  const enabledDocuments = useMemo(
    () => documents.filter((d) => d.enabled && d.status === 'ready'),
    [documents]
  );

  const activeCitations = useMemo<CitationItem[]>(() => {
    if (!activeMessageId) return [];
    const target = messages.find((m) => m.id === activeMessageId);
    return target?.citations ?? [];
  }, [activeMessageId, messages]);

  const handleToggleCategory = async (category: DocumentCategory | string) => {
    const catDocs = documents.filter((d) => d.category === category && d.status === 'ready');
    if (catDocs.length === 0) return;

    const anyEnabled = catDocs.some((d) => d.enabled);
    const nextEnabled = !anyEnabled;
    const targets = catDocs.filter((d) => d.enabled !== nextEnabled);
    if (targets.length === 0) return;

    const targetIds = new Set(targets.map((d) => d.id));
    setLibraryError(null);
    setDocuments((prev) =>
      prev.map((doc) => (targetIds.has(doc.id) ? { ...doc, enabled: nextEnabled } : doc))
    );

    try {
      const updatedList = await Promise.all(
        targets.map((doc) => updateDocumentEnabled(doc.id, nextEnabled))
      );
      const updatedMap = new Map(updatedList.map((d) => [d.id, d]));
      setDocuments((prev) => prev.map((doc) => updatedMap.get(doc.id) ?? doc));
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Không thể cập nhật phạm vi danh mục.';
      setLibraryError(msg);
      try {
        const fresh = await fetchDocuments();
        setDocuments(fresh);
      } catch {
        setDocuments((prev) =>
          prev.map((doc) => (targetIds.has(doc.id) ? { ...doc, enabled: !nextEnabled } : doc))
        );
      }
    }
  };

  const handleEnableAllDocuments = async () => {
    const targets = documents.filter((d) => d.status === 'ready' && !d.enabled);
    if (targets.length === 0) return;

    const targetIds = new Set(targets.map((d) => d.id));
    setLibraryError(null);
    setDocuments((prev) =>
      prev.map((doc) => (targetIds.has(doc.id) ? { ...doc, enabled: true } : doc))
    );

    try {
      const updatedList = await Promise.all(
        targets.map((doc) => updateDocumentEnabled(doc.id, true))
      );
      const updatedMap = new Map(updatedList.map((d) => [d.id, d]));
      setDocuments((prev) => prev.map((doc) => updatedMap.get(doc.id) ?? doc));
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Không thể bật toàn bộ tài liệu.';
      setLibraryError(msg);
      try {
        const fresh = await fetchDocuments();
        setDocuments(fresh);
      } catch {
        setDocuments((prev) =>
          prev.map((doc) => (targetIds.has(doc.id) ? { ...doc, enabled: false } : doc))
        );
      }
    }
  };

  const handleToggleDocument = async (documentId: string) => {
    const target = documents.find((d) => d.id === documentId);
    if (!target) return;

    const nextEnabled = !target.enabled;
    setLibraryError(null);
    setDocuments((prev) =>
      prev.map((doc) => (doc.id === documentId ? { ...doc, enabled: nextEnabled } : doc))
    );

    try {
      const updated = await updateDocumentEnabled(documentId, nextEnabled);
      setDocuments((prev) => prev.map((doc) => (doc.id === documentId ? updated : doc)));
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Không thể cập nhật trạng thái tài liệu.';
      setLibraryError(msg);
      setDocuments((prev) =>
        prev.map((doc) => (doc.id === documentId ? { ...doc, enabled: !nextEnabled } : doc))
      );
    }
  };

  const handleDeleteDocument = async (documentId: string) => {
    if (deletingDocIds.has(documentId)) return;

    setLibraryError(null);
    setDeletingDocIds((prev) => new Set(prev).add(documentId));
    try {
      await apiDeleteDocument(documentId);
      setDocuments((prev) => prev.filter((doc) => doc.id !== documentId));
      if (!isMockMode) {
        fetchHealth()
          .then(setHealthInfo)
          .catch(() => {});
      }
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Không thể xóa tài liệu.';
      setLibraryError(msg);
    } finally {
      setDeletingDocIds((prev) => {
        const next = new Set(prev);
        next.delete(documentId);
        return next;
      });
    }
  };

  const handleUploadFiles = (fileList: FileList, category: DocumentCategory) => {
    const files = Array.from(fileList);
    setLibraryError(null);

    files.forEach(async (file) => {
      try {
        await uploadDocument(
          file,
          category,
          (updatedDoc, replacedId) => {
            setDocuments((prev) => {
              const withoutTemp = replacedId ? prev.filter((d) => d.id !== replacedId) : prev;
              const exists = withoutTemp.some((d) => d.id === updatedDoc.id);
              if (exists) {
                return withoutTemp.map((d) => (d.id === updatedDoc.id ? updatedDoc : d));
              }
              return [updatedDoc, ...withoutTemp];
            });
          },
          (tempId) => {
            setDocuments((prev) => prev.filter((d) => d.id !== tempId));
          }
        );

        if (!isMockMode) {
          fetchHealth()
            .then((h) => {
              setHealthInfo(h);
              setConnectionState(h.status === 'ok' ? 'connected' : 'degraded');
            })
            .catch(() => {});
        }
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : `Tải tài liệu "${file.name}" thất bại.`;
        setLibraryError(msg);
      }
    });
  };

  const handleSyncKnowledgeBase = async () => {
    if (isSyncing) return;
    setIsSyncing(true);
    setLibraryError(null);
    try {
      const job = await syncKnowledgeBase(false);
      await loadBackendState();
      if (job.errors.length > 0) {
        setLibraryError(`Đồng bộ hoàn tất với ${job.errors.length} lỗi: ${job.errors[0]}`);
      }
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Không thể đồng bộ kho tri thức.';
      setLibraryError(msg);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setActiveMessageId(null);
    setSelectedCitationId(null);
    setActiveView('chat');
  };

  const handleSendQuestion = async (question: string) => {
    const userMsg: ChatMessage = {
      id: `msg-user-${Date.now()}`,
      role: 'user',
      content: question,
      createdAt: formatTimeNow(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsQuerying(true);

    try {
      const response = await queryRag({
        question,
        documentIds: enabledDocuments.map((d) => d.id),
        topK: 3,
      });

      const assistantMsg: ChatMessage = {
        id: `msg-asst-${Date.now()}`,
        role: 'assistant',
        content: response.answer,
        citations: response.citations,
        latencyMs: response.latencyMs,
        createdAt: formatTimeNow(),
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setActiveMessageId(assistantMsg.id);
      setSelectedCitationId(response.citations[0]?.id ?? null);
    } catch (err) {
      const errorText =
        err instanceof Error ? err.message : 'Không thể xử lý câu hỏi. Vui lòng thử lại.';
      const errorMsg: ChatMessage = {
        id: `msg-err-${Date.now()}`,
        role: 'assistant',
        content: '',
        error: errorText,
        createdAt: formatTimeNow(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsQuerying(false);
    }
  };

  const handleSelectCitation = (messageId: string, citation: CitationItem) => {
    setActiveMessageId(messageId);
    setSelectedCitationId(citation.id);
    setIsInspectorOpen(true);
  };

  const showInspectorColumn = activeView === 'chat';

  return (
    <div className={`app-shell ${showInspectorColumn ? 'has-inspector' : ''}`}>
      <div className="mobile-topbar">
        <button
          type="button"
          className="icon-btn"
          onClick={() => setIsSidebarOpen(true)}
          aria-label="Mở menu điều hướng"
        >
          <Menu size={16} />
        </button>
        <span className="mobile-brand">Kho Tri Thức</span>
        {activeView === 'chat' ? (
          <button
            type="button"
            className="icon-btn"
            onClick={() => setIsInspectorOpen(true)}
            aria-label="Xem nguồn trích dẫn"
          >
            <BookMarked size={15} />
            <span>{activeCitations.length}</span>
          </button>
        ) : (
          <span style={{ width: 36 }} />
        )}
      </div>

      <div
        className={`drawer-backdrop ${isSidebarOpen || isInspectorOpen ? 'visible' : ''}`}
        onClick={() => {
          setIsSidebarOpen(false);
          setIsInspectorOpen(false);
        }}
      />

      <Sidebar
        activeView={activeView}
        onSelectView={setActiveView}
        onNewChat={handleNewChat}
        documents={documents}
        onToggleCategory={handleToggleCategory}
        onEnableAllDocuments={handleEnableAllDocuments}
        connectionState={connectionState}
        healthInfo={healthInfo}
        onRetryConnection={loadBackendState}
        isOpenMobile={isSidebarOpen}
        onCloseMobile={() => setIsSidebarOpen(false)}
      />

      {activeView === 'chat' ? (
        <ChatView
          messages={messages}
          isQuerying={isQuerying}
          enabledDocCount={enabledDocuments.length}
          selectedCitationId={selectedCitationId}
          onSendQuestion={handleSendQuestion}
          onSelectCitation={handleSelectCitation}
          onOpenLibrary={() => setActiveView('library')}
          onOpenInspectorDrawer={() => setIsInspectorOpen(true)}
          activeCitationsCount={activeCitations.length}
        />
      ) : (
        <LibraryView
          documents={documents}
          isLoading={isLoadingDocs}
          error={libraryError}
          onDismissError={() => setLibraryError(null)}
          onUploadFiles={handleUploadFiles}
          onToggleDocument={handleToggleDocument}
          onDeleteDocument={handleDeleteDocument}
          onSyncKnowledgeBase={handleSyncKnowledgeBase}
          isSyncing={isSyncing}
          deletingDocIds={deletingDocIds}
        />
      )}

      {showInspectorColumn && (
        <SourceInspector
          citations={activeCitations}
          selectedCitationId={selectedCitationId}
          onSelectCitation={(id) => setSelectedCitationId(id)}
          isOpenDrawer={isInspectorOpen}
          onCloseDrawer={() => setIsInspectorOpen(false)}
        />
      )}
    </div>
  );
}
export default App;
