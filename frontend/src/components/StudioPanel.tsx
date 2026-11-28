import { useState } from 'react';
import {
  BookOpen,
  Check,
  Copy,
  FileSpreadsheet,
  FileText,
  HelpCircle,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
} from 'lucide-react';
import type { NoteItem, StudioGenerateType } from '../types/rag';
import { renderMarkdown } from '../utils/markdown';

interface StudioPanelProps {
  notes: NoteItem[];
  enabledDocCount: number;
  isGenerating: boolean;
  generatingType: StudioGenerateType | null;
  onGenerateStudio: (type: StudioGenerateType) => void;
  onCreateManualNote: (title: string, content: string) => Promise<void>;
  onDeleteNote: (noteId: string) => Promise<void>;
}

const STUDIO_ACTIONS: Array<{
  type: StudioGenerateType;
  label: string;
  desc: string;
  icon: typeof FileText;
}> = [
  { type: 'summary', label: 'Tóm tắt', desc: 'Tổng hợp ý chính', icon: FileText },
  { type: 'faq', label: 'FAQ', desc: 'Câu hỏi thường gặp', icon: HelpCircle },
  { type: 'briefing', label: 'Briefing Doc', desc: 'Tài liệu điều hành', icon: Sparkles },
  { type: 'study_guide', label: 'Ôn tập', desc: 'Điểm nhớ & kiểm tra', icon: BookOpen },
  { type: 'comparison_table', label: 'Bảng đối chiếu', desc: 'So sánh quy định', icon: FileSpreadsheet },
];

const NOTE_TYPE_LABELS: Record<string, string> = {
  pinned: 'Đã ghim',
  summary: 'Tóm tắt',
  faq: 'FAQ',
  briefing: 'Briefing',
  study_guide: 'Ôn tập',
  comparison_table: 'Bảng so sánh',
  custom: 'Ghi chú',
};

export function StudioPanel({
  notes,
  enabledDocCount,
  isGenerating,
  generatingType,
  onGenerateStudio,
  onCreateManualNote,
  onDeleteNote,
}: StudioPanelProps) {
  const [showComposer, setShowComposer] = useState(false);
  const [noteTitle, setNoteTitle] = useState('');
  const [noteContent, setNoteContent] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleSaveManualNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!noteTitle.trim() || !noteContent.trim() || isSaving) return;
    setIsSaving(true);
    try {
      await onCreateManualNote(noteTitle.trim(), noteContent.trim());
      setNoteTitle('');
      setNoteContent('');
      setShowComposer(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCopy = async (note: NoteItem) => {
    try {
      await navigator.clipboard.writeText(note.content);
      setCopiedId(note.id);
      setTimeout(() => setCopiedId((cur) => (cur === note.id ? null : cur)), 1600);
    } catch {
      // Ignore clipboard failure
    }
  };

  return (
    <div className="studio-panel">
      <div className="studio-section">
        <div className="studio-section-head">
          <h3 className="studio-heading">Tạo nhanh từ {enabledDocCount} nguồn</h3>
        </div>
        <div className="studio-action-grid">
          {STUDIO_ACTIONS.map((action) => {
            const Icon = action.icon;
            const runningThis = isGenerating && generatingType === action.type;
            return (
              <button
                key={action.type}
                type="button"
                className="studio-action-card"
                disabled={isGenerating || enabledDocCount === 0}
                onClick={() => onGenerateStudio(action.type)}
              >
                <div className="studio-action-top">
                  {runningThis ? <Loader2 size={14} className="spin" /> : <Icon size={14} />}
                  <span className="studio-action-label">{action.label}</span>
                </div>
                <span className="studio-action-desc">{action.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="studio-section">
        <div className="studio-section-head">
          <h3 className="studio-heading">Ghi chú đã lưu ({notes.length})</h3>
          <button
            type="button"
            className="text-link-btn"
            onClick={() => setShowComposer((prev) => !prev)}
          >
            <Plus size={12} style={{ verticalAlign: -1, marginRight: 2 }} />
            {showComposer ? 'Đóng' : 'Thêm ghi chú'}
          </button>
        </div>

        {showComposer && (
          <form className="note-composer" onSubmit={handleSaveManualNote}>
            <input
              type="text"
              className="note-input"
              placeholder="Tiêu đề ghi chú..."
              value={noteTitle}
              onChange={(e) => setNoteTitle(e.target.value)}
            />
            <textarea
              className="note-textarea"
              rows={3}
              placeholder="Nội dung ghi chú (hỗ trợ Markdown)..."
              value={noteContent}
              onChange={(e) => setNoteContent(e.target.value)}
            />
            <div className="note-composer-actions">
              <button
                type="submit"
                className="send-btn"
                disabled={!noteTitle.trim() || !noteContent.trim() || isSaving}
                style={{ padding: '5px 12px', fontSize: 12.5 }}
              >
                {isSaving ? 'Đang lưu...' : 'Lưu ghi chú'}
              </button>
            </div>
          </form>
        )}

        {notes.length === 0 ? (
          <div className="inspector-empty" style={{ padding: '10px 2px' }}>
            <p>
              Chưa có ghi chú nào. Bạn có thể bấm các nút Studio ở trên hoặc bấm{' '}
              <strong>Ghim ghi chú</strong> dưới câu trả lời AI để lưu lại.
            </p>
          </div>
        ) : (
          <div className="note-list">
            {notes.map((note) => (
              <article key={note.id} className="note-card">
                <div className="note-card-head">
                  <div className="note-card-title-wrap">
                    <span className="note-type-pill">
                      {NOTE_TYPE_LABELS[note.noteType] ?? note.noteType}
                    </span>
                    <h4 className="note-card-title">{note.title}</h4>
                  </div>
                  <div className="note-card-actions">
                    <button
                      type="button"
                      className="icon-mini-btn"
                      onClick={() => void handleCopy(note)}
                      title="Sao chép nội dung"
                    >
                      {copiedId === note.id ? <Check size={13} /> : <Copy size={13} />}
                    </button>
                    <button
                      type="button"
                      className="icon-mini-btn danger"
                      onClick={() => void onDeleteNote(note.id)}
                      title="Xóa ghi chú"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
                <div className="note-card-body assistant-prose">
                  {renderMarkdown(note.content)}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
