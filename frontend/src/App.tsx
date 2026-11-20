import { useEffect, useMemo, useState } from 'react';
import { BookMarked, Menu } from 'lucide-react';
import {
  deleteDocument as apiDeleteDocument,
  fetchDocuments,
  queryRag,
  uploadDocument,
} from './api/ragClient';
import { ChatView } from './components/ChatView';
import { LibraryView } from './components/LibraryView';
import { Sidebar } from './components/Sidebar';
import { SourceInspector } from './components/SourceInspector';
import type { ChatMessage, CitationItem, DocumentCategory, DocumentItem } from './types/rag';

function formatTimeNow(): string {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

export function App() {
  const [activeView, setActiveView] = useState<'chat' | 'library'>('chat');
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);

  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);

  useEffect(() => {
    fetchDocuments()
      .then(setDocuments)
      .catch(() => {
        // Keep empty list if backend unreachable
      });
  }, []);

  const enabledDocuments = useMemo(
    () => documents.filter((d) => d.enabled && d.status === 'ready'),
    [documents]
  );

  const activeCitations = useMemo<CitationItem[]>(() => {
    if (!activeMessageId) return [];
    const target = messages.find((m) => m.id === activeMessageId);
    return target?.citations ?? [];
  }, [activeMessageId, messages]);

  const handleToggleCategory = (category: DocumentCategory) => {
    const catDocs = documents.filter((d) => d.category === category && d.status === 'ready');
    const anyEnabled = catDocs.some((d) => d.enabled);
    setDocuments((prev) =>
      prev.map((doc) =>
        doc.category === category && doc.status === 'ready'
          ? { ...doc, enabled: !anyEnabled }
          : doc
      )
    );
  };

  const handleEnableAllDocuments = () => {
    setDocuments((prev) =>
      prev.map((doc) => (doc.status === 'ready' ? { ...doc, enabled: true } : doc))
    );
  };

  const handleToggleDocument = (documentId: string) => {
    setDocuments((prev) =>
      prev.map((doc) => (doc.id === documentId ? { ...doc, enabled: !doc.enabled } : doc))
    );
  };

  const handleDeleteDocument = async (documentId: string) => {
    await apiDeleteDocument(documentId);
    setDocuments((prev) => prev.filter((doc) => doc.id !== documentId));
  };

  const handleUploadFiles = (fileList: FileList, category: DocumentCategory) => {
    const files = Array.from(fileList);
    for (const file of files) {
      uploadDocument(file, category, (updatedDoc) => {
        setDocuments((prev) => {
          const exists = prev.some((d) => d.id === updatedDoc.id);
          if (exists) {
            return prev.map((d) => (d.id === updatedDoc.id ? updatedDoc : d));
          }
          return [updatedDoc, ...prev];
        });
      });
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
          onUploadFiles={handleUploadFiles}
          onToggleDocument={handleToggleDocument}
          onDeleteDocument={handleDeleteDocument}
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
