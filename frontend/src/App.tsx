import { useCallback, useEffect, useMemo, useState } from 'react';
import { BookMarked, Menu } from 'lucide-react';
import {
  createConversation,
  createNotebook,
  createNote,
  deleteConversation,
  deleteDocument as apiDeleteDocument,
  deleteNotebook,
  deleteNote,
  fetchConversation,
  fetchConversations,
  fetchDocuments,
  fetchHealth,
  fetchNotebooks,
  fetchNotes,
  generateNotebookOverview,
  generateStudioArtifact,
  isMockMode,
  streamQueryRag,
  syncKnowledgeBase,
  updateDocumentEnabled,
  updateNotebook,
  uploadDocument,
} from './api/ragClient';
import { ChatView } from './components/ChatView';
import { LibraryView } from './components/LibraryView';
import { Sidebar } from './components/Sidebar';
import { SourceGuideModal } from './components/SourceGuideModal';
import { SourceInspector } from './components/SourceInspector';
import type {
  ChatMessage,
  CitationItem,
  ConnectionState,
  ConversationSummary,
  DocumentCategory,
  DocumentItem,
  HealthResponse,
  NotebookItem,
  NoteItem,
  StudioGenerateType,
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

  const [notebooks, setNotebooks] = useState<NotebookItem[]>([]);
  const [activeNotebookId, setActiveNotebookId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [notes, setNotes] = useState<NoteItem[]>([]);

  const [overviewText, setOverviewText] = useState('');
  const [overviewQuestions, setOverviewQuestions] = useState<string[]>([]);
  const [isGeneratingOverview, setIsGeneratingOverview] = useState(false);

  const [inspectorTab, setInspectorTab] = useState<'citations' | 'studio'>('citations');
  const [isGeneratingStudio, setIsGeneratingStudio] = useState(false);
  const [generatingStudioType, setGeneratingStudioType] = useState<StudioGenerateType | null>(null);
  const [inspectedDocument, setInspectedDocument] = useState<DocumentItem | null>(null);

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

  const loadWorkspaceData = useCallback(async (nbId: string | null) => {
    const [convRes, notesRes] = await Promise.allSettled([
      fetchConversations(nbId),
      fetchNotes(nbId),
    ]);
    if (convRes.status === 'fulfilled') {
      setConversations(convRes.value);
    }
    if (notesRes.status === 'fulfilled') {
      setNotes(notesRes.value);
    }
  }, []);

  const loadBackendState = useCallback(async () => {
    setIsLoadingDocs(true);
    if (!isMockMode) {
      setConnectionState('checking');
    }

    const [healthRes, docsRes, nbRes] = await Promise.allSettled([
      fetchHealth(),
      fetchDocuments(),
      fetchNotebooks(),
    ]);

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

    if (nbRes.status === 'fulfilled') {
      setNotebooks(nbRes.value);
    }

    await loadWorkspaceData(activeNotebookId);
    setIsLoadingDocs(false);
  }, [activeNotebookId, loadWorkspaceData]);

  useEffect(() => {
    void loadBackendState();
  }, [loadBackendState]);

  const activeNotebook = useMemo(
    () => notebooks.find((n) => n.id === activeNotebookId) ?? null,
    [notebooks, activeNotebookId]
  );

  useEffect(() => {
    if (activeNotebook) {
      setOverviewText(activeNotebook.overview || '');
      setOverviewQuestions(activeNotebook.suggestedQuestions || []);
    } else {
      setOverviewText('');
      setOverviewQuestions([]);
    }
  }, [activeNotebook]);

  const enabledDocuments = useMemo(() => {
    const readyEnabled = documents.filter((d) => d.enabled && d.status === 'ready');
    if (activeNotebook) {
      const nbSet = new Set(activeNotebook.documentIds);
      return readyEnabled.filter((d) => nbSet.has(d.id));
    }
    return readyEnabled;
  }, [documents, activeNotebook]);

  const activeCitations = useMemo<CitationItem[]>(() => {
    if (!activeMessageId) return [];
    const target = messages.find((m) => m.id === activeMessageId);
    return target?.citations ?? [];
  }, [activeMessageId, messages]);

  const handleSelectNotebook = async (notebookId: string | null) => {
    setActiveNotebookId(notebookId);
    setActiveConversationId(null);
    setMessages([]);
    setActiveMessageId(null);
    setSelectedCitationId(null);
    await loadWorkspaceData(notebookId);
  };

  const handleCreateNotebook = async (title: string) => {
    const initialDocIds = documents.filter((d) => d.enabled && d.status === 'ready').map((d) => d.id);
    const created = await createNotebook(title, initialDocIds);
    setNotebooks((prev) => [created, ...prev]);
    await handleSelectNotebook(created.id);
  };

  const handleDeleteNotebook = async (notebookId: string) => {
    await deleteNotebook(notebookId);
    setNotebooks((prev) => prev.filter((n) => n.id !== notebookId));
    if (activeNotebookId === notebookId) {
      await handleSelectNotebook(null);
    }
  };

  const handleSelectConversation = async (conversationId: string) => {
    try {
      const conv = await fetchConversation(conversationId);
      setActiveConversationId(conv.id);
      setMessages(conv.messages);
      const lastAssistant = [...conv.messages].reverse().find((m) => m.role === 'assistant');
      setActiveMessageId(lastAssistant?.id ?? null);
      setSelectedCitationId(lastAssistant?.citations?.[0]?.id ?? null);
      setActiveView('chat');
      setInspectorTab('citations');
    } catch (err) {
      setLibraryError(err instanceof Error ? err.message : 'Không thể mở cuộc hội thoại.');
    }
  };

  const handleDeleteConversation = async (conversationId: string) => {
    await deleteConversation(conversationId);
    setConversations((prev) => prev.filter((c) => c.id !== conversationId));
    if (activeConversationId === conversationId) {
      setActiveConversationId(null);
      setMessages([]);
      setActiveMessageId(null);
      setSelectedCitationId(null);
    }
  };

  const handleToggleCategory = async (category: DocumentCategory | string) => {
    const catDocs = documents.filter((d) => d.category === category && d.status === 'ready');
    if (catDocs.length === 0) return;

    if (activeNotebook) {
      const nbSet = new Set(activeNotebook.documentIds);
      const anyInCat = catDocs.some((d) => nbSet.has(d.id));
      if (anyInCat) {
        catDocs.forEach((d) => nbSet.delete(d.id));
      } else {
        catDocs.forEach((d) => nbSet.add(d.id));
      }
      const nextIds = Array.from(nbSet);
      const updated = await updateNotebook(activeNotebook.id, { documentIds: nextIds });
      setNotebooks((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
      return;
    }

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
      const msg = err instanceof Error ? err.message : 'Không thể cập nhật phạm vi danh mục.';
      setLibraryError(msg);
      try {
        setDocuments(await fetchDocuments());
      } catch {
        // ignore
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
      const updatedList = await Promise.all(targets.map((doc) => updateDocumentEnabled(doc.id, true)));
      const updatedMap = new Map(updatedList.map((d) => [d.id, d]));
      setDocuments((prev) => prev.map((doc) => updatedMap.get(doc.id) ?? doc));
    } catch (err) {
      setLibraryError(err instanceof Error ? err.message : 'Không thể bật toàn bộ tài liệu.');
    }
  };

  const handleToggleDocument = async (documentId: string) => {
    if (activeNotebook && activeView === 'chat') {
      const nbSet = new Set(activeNotebook.documentIds);
      if (nbSet.has(documentId)) nbSet.delete(documentId);
      else nbSet.add(documentId);
      const updated = await updateNotebook(activeNotebook.id, { documentIds: Array.from(nbSet) });
      setNotebooks((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
      return;
    }

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
      setLibraryError(err instanceof Error ? err.message : 'Không thể cập nhật trạng thái tài liệu.');
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
        fetchHealth().then(setHealthInfo).catch(() => {});
      }
    } catch (err) {
      setLibraryError(err instanceof Error ? err.message : 'Không thể xóa tài liệu.');
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
        const saved = await uploadDocument(
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

        if (activeNotebook && saved.status === 'ready') {
          const nextIds = Array.from(new Set([...activeNotebook.documentIds, saved.id]));
          const updatedNb = await updateNotebook(activeNotebook.id, { documentIds: nextIds });
          setNotebooks((prev) => prev.map((n) => (n.id === updatedNb.id ? updatedNb : n)));
        }

        if (!isMockMode) {
          fetchHealth()
            .then((h) => {
              setHealthInfo(h);
              setConnectionState(h.status === 'ok' ? 'connected' : 'degraded');
            })
            .catch(() => {});
        }
      } catch (err) {
        setLibraryError(
          err instanceof Error ? err.message : `Tải tài liệu "${file.name}" thất bại.`
        );
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
      setLibraryError(err instanceof Error ? err.message : 'Không thể đồng bộ kho tri thức.');
    } finally {
      setIsSyncing(false);
    }
  };

  const handleGenerateOverview = async () => {
    if (isGeneratingOverview || enabledDocuments.length === 0) return;
    setIsGeneratingOverview(true);
    try {
      const res = await generateNotebookOverview(
        enabledDocuments.map((d) => d.id),
        activeNotebookId
      );
      setOverviewText(res.overview);
      setOverviewQuestions(res.suggestedQuestions);
      if (activeNotebookId) {
        setNotebooks((prev) =>
          prev.map((n) =>
            n.id === activeNotebookId
              ? { ...n, overview: res.overview, suggestedQuestions: res.suggestedQuestions }
              : n
          )
        );
      }
    } catch (err) {
      setLibraryError(err instanceof Error ? err.message : 'Không thể tạo tổng quan.');
    } finally {
      setIsGeneratingOverview(false);
    }
  };

  const handleNewChat = () => {
    setActiveConversationId(null);
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
    const streamAsstId = `msg-asst-${Date.now() + 1}`;
    const placeholderAsst: ChatMessage = {
      id: streamAsstId,
      role: 'assistant',
      content: '',
      createdAt: formatTimeNow(),
      isStreaming: true,
      statusText: 'Đang khởi tạo truy vấn...',
    };

    const historyPayload = messages
      .filter((m) => !m.error && !m.isStreaming && m.content.trim())
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [...prev, userMsg, placeholderAsst]);
    setActiveMessageId(streamAsstId);
    setInspectorTab('citations');
    setIsQuerying(true);

    let convId = activeConversationId;
    if (!convId) {
      try {
        const createdConv = await createConversation(question.slice(0, 70), activeNotebookId);
        convId = createdConv.id;
        setActiveConversationId(convId);
      } catch {
        convId = null;
      }
    }

    try {
      const finalRes = await streamQueryRag(
        {
          question,
          documentIds: enabledDocuments.map((d) => d.id),
          topK: 6,
          history: historyPayload,
          conversationId: convId,
          notebookId: activeNotebookId,
        },
        {
          onStatus: (message) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === streamAsstId ? { ...m, statusText: message } : m))
            );
          },
          onCitations: (cits) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === streamAsstId ? { ...m, citations: cits } : m))
            );
            setSelectedCitationId(cits[0]?.id ?? null);
          },
          onDelta: (chunk) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === streamAsstId ? { ...m, content: `${m.content}${chunk}`, statusText: undefined } : m
              )
            );
          },
        }
      );

      setMessages((prev) =>
        prev.map((m) =>
          m.id === streamAsstId
            ? {
                ...m,
                content: finalRes.answer || m.content,
                citations: finalRes.citations,
                latencyMs: finalRes.latencyMs,
                generationMode: finalRes.generationMode,
                modelUsed: finalRes.modelUsed,
                providerUsed: finalRes.providerUsed,
                rewrittenQuery: finalRes.rewrittenQuery,
                followUpQuestions: finalRes.followUpQuestions,
                warning: finalRes.warning,
                isStreaming: false,
                statusText: undefined,
              }
            : m
        )
      );
      setSelectedCitationId(finalRes.citations[0]?.id ?? null);
      if (convId) {
        fetchConversations(activeNotebookId).then(setConversations).catch(() => {});
      }
    } catch (err) {
      const errorText =
        err instanceof Error ? err.message : 'Không thể xử lý câu hỏi. Vui lòng thử lại.';
      setMessages((prev) =>
        prev.map((m) =>
          m.id === streamAsstId
            ? { ...m, content: '', error: errorText, isStreaming: false, statusText: undefined }
            : m
        )
      );
    } finally {
      setIsQuerying(false);
    }
  };

  const handlePinNote = async (msg: ChatMessage) => {
    const firstLine = msg.content.split('\n')[0]?.replace(/[#*`]/g, '').trim() || 'Ghi chú từ hỏi đáp';
    const title = firstLine.slice(0, 80);
    const sourceIds = Array.from(new Set((msg.citations ?? []).map((c) => c.documentId)));
    const created = await createNote({
      title,
      content: msg.content,
      noteType: 'pinned',
      notebookId: activeNotebookId,
      sourceDocumentIds: sourceIds,
    });
    setNotes((prev) => [created, ...prev]);
    setInspectorTab('studio');
  };

  const handleGenerateStudio = async (type: StudioGenerateType) => {
    if (isGeneratingStudio || enabledDocuments.length === 0) return;
    setIsGeneratingStudio(true);
    setGeneratingStudioType(type);
    try {
      const res = await generateStudioArtifact(
        type,
        enabledDocuments.map((d) => d.id),
        activeNotebookId
      );
      if (res.note) {
        setNotes((prev) => [res.note!, ...prev]);
      }
    } catch (err) {
      setLibraryError(err instanceof Error ? err.message : 'Không thể tạo nội dung Studio.');
    } finally {
      setIsGeneratingStudio(false);
      setGeneratingStudioType(null);
    }
  };

  const handleCreateManualNote = async (title: string, content: string) => {
    const created = await createNote({
      title,
      content,
      noteType: 'custom',
      notebookId: activeNotebookId,
      sourceDocumentIds: enabledDocuments.map((d) => d.id),
    });
    setNotes((prev) => [created, ...prev]);
  };

  const handleDeleteNote = async (noteId: string) => {
    await deleteNote(noteId);
    setNotes((prev) => prev.filter((n) => n.id !== noteId));
  };

  const handleSelectCitation = (messageId: string, citation: CitationItem) => {
    setActiveMessageId(messageId);
    setSelectedCitationId(citation.id);
    setInspectorTab('citations');
    setIsInspectorOpen(true);
  };

  const handleInspectDocumentById = (documentId: string) => {
    const doc = documents.find((d) => d.id === documentId) ?? null;
    if (doc) setInspectedDocument(doc);
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
        onToggleDocument={handleToggleDocument}
        onEnableAllDocuments={handleEnableAllDocuments}
        onInspectDocument={(doc) => setInspectedDocument(doc)}
        notebooks={notebooks}
        activeNotebookId={activeNotebookId}
        onSelectNotebook={handleSelectNotebook}
        onCreateNotebook={handleCreateNotebook}
        onDeleteNotebook={handleDeleteNotebook}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
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
          activeNotebook={activeNotebook}
          overviewText={overviewText}
          overviewQuestions={overviewQuestions}
          isGeneratingOverview={isGeneratingOverview}
          onGenerateOverview={handleGenerateOverview}
          onSendQuestion={handleSendQuestion}
          onSelectCitation={handleSelectCitation}
          onPinNote={handlePinNote}
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
          activeTab={inspectorTab}
          onChangeTab={setInspectorTab}
          citations={activeCitations}
          selectedCitationId={selectedCitationId}
          onSelectCitation={(id) => setSelectedCitationId(id)}
          onInspectDocument={handleInspectDocumentById}
          notes={notes}
          enabledDocCount={enabledDocuments.length}
          isGeneratingStudio={isGeneratingStudio}
          generatingStudioType={generatingStudioType}
          onGenerateStudio={handleGenerateStudio}
          onCreateManualNote={handleCreateManualNote}
          onDeleteNote={handleDeleteNote}
          isOpenDrawer={isInspectorOpen}
          onCloseDrawer={() => setIsInspectorOpen(false)}
        />
      )}

      <SourceGuideModal
        document={inspectedDocument}
        onClose={() => setInspectedDocument(null)}
        onAskQuestion={(q) => {
          setActiveView('chat');
          void handleSendQuestion(q);
        }}
      />
    </div>
  );
}
export default App;
