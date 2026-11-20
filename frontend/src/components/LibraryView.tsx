import { useRef, useState } from 'react';
import { CheckCircle2, Loader2, Search, Trash2, Upload } from 'lucide-react';
import type { DocumentCategory, DocumentItem } from '../types/rag';

const CATEGORIES: DocumentCategory[] = ['Nhân sự', 'Vận hành', 'Kỹ thuật & IT'];

interface LibraryViewProps {
  documents: DocumentItem[];
  onUploadFiles: (files: FileList, category: DocumentCategory) => void;
  onToggleDocument: (documentId: string) => void;
  onDeleteDocument: (documentId: string) => void;
}

export function LibraryView({
  documents,
  onUploadFiles,
  onToggleDocument,
  onDeleteDocument,
}: LibraryViewProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCategory, setFilterCategory] = useState<'Tất cả' | DocumentCategory>('Tất cả');
  const [uploadCategory, setUploadCategory] = useState<DocumentCategory>('Nhân sự');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const filteredDocs = documents.filter((doc) => {
    const matchesCat = filterCategory === 'Tất cả' || doc.category === filterCategory;
    const q = searchQuery.trim().toLowerCase();
    const matchesQuery =
      !q ||
      doc.title.toLowerCase().includes(q) ||
      doc.filename.toLowerCase().includes(q) ||
      doc.summary.toLowerCase().includes(q);
    return matchesCat && matchesQuery;
  });

  const totalChunks = documents.reduce((sum, doc) => sum + doc.chunkCount, 0);
  const activeDocsCount = documents.filter((d) => d.enabled && d.status === 'ready').length;

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onUploadFiles(e.dataTransfer.files, uploadCategory);
    }
  };

  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      onUploadFiles(e.target.files, uploadCategory);
      e.target.value = '';
    }
  };

  const renderStatus = (status: DocumentItem['status']) => {
    if (status === 'ready') {
      return (
        <span className="doc-status ready">
          <CheckCircle2 size={14} />
          <span>Sẵn sàng</span>
        </span>
      );
    }
    if (status === 'chunking') {
      return (
        <span className="doc-status processing">
          <Loader2 size={14} className="spin" />
          <span>Đang tách đoạn</span>
        </span>
      );
    }
    if (status === 'embedding') {
      return (
        <span className="doc-status processing">
          <Loader2 size={14} className="spin" />
          <span>Đang tạo vector</span>
        </span>
      );
    }
    return <span className="doc-status">Lỗi xử lý</span>;
  };

  return (
    <main className="main-stage">
      <header className="stage-header">
        <div className="stage-header-info">
          <h2 className="stage-title">Thư viện tài liệu</h2>
          <span className="stage-subtitle">Quản lý nguồn tri thức phục vụ truy xuất RAG</span>
        </div>
      </header>

      <div className="library-scroll">
        <div className="library-inner">
          <div className="library-heading-row">
            <div>
              <h2 className="library-title">Tài liệu đã lập chỉ mục</h2>
              <p className="library-desc">
                Tải lên tệp PDF, DOCX hoặc Markdown để hệ thống tự động tách đoạn và đưa vào phạm vi
                hỏi đáp.
              </p>
            </div>

            <div className="library-stats">
              <div className="stat-item">
                <span className="stat-num">{activeDocsCount}</span>
                <span className="stat-label">Đang bật</span>
              </div>
              <div className="stat-item">
                <span className="stat-num">{totalChunks}</span>
                <span className="stat-label">Tổng đoạn văn</span>
              </div>
            </div>
          </div>

          <div
            className={`upload-zone ${isDragging ? 'dragging' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            <div className="upload-zone-left">
              <div className="upload-icon-wrap" aria-hidden="true">
                <Upload size={20} strokeWidth={1.8} />
              </div>
              <div>
                <h3 className="upload-title">Kéo thả tài liệu vào đây hoặc chọn từ máy tính</h3>
                <p className="upload-sub">
                  Hỗ trợ PDF, DOCX, MD, TXT. Tài liệu mới sẽ khả dụng ngay sau khi lập chỉ mục xong.
                </p>
              </div>
            </div>

            <div className="upload-controls">
              <select
                aria-label="Chọn danh mục cho tài liệu tải lên"
                className="category-select"
                value={uploadCategory}
                onChange={(e) => setUploadCategory(e.target.value as DocumentCategory)}
              >
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>

              <button
                type="button"
                className="upload-trigger-btn"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload size={15} />
                <span>Chọn tệp tải lên</span>
              </button>

              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.md,.txt"
                multiple
                hidden
                onChange={handleFilePick}
              />
            </div>
          </div>

          <div className="library-toolbar">
            <div className="search-input-wrap">
              <Search size={15} className="search-icon" />
              <input
                type="search"
                className="search-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Tìm theo tên tài liệu hoặc nội dung..."
              />
            </div>

            <div className="filter-tabs" role="tablist" aria-label="Lọc theo danh mục">
              {(['Tất cả', ...CATEGORIES] as const).map((cat) => (
                <button
                  key={cat}
                  type="button"
                  role="tab"
                  aria-selected={filterCategory === cat}
                  className={`filter-tab ${filterCategory === cat ? 'active' : ''}`}
                  onClick={() => setFilterCategory(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          <div className="doc-ledger" role="table" aria-label="Danh sách tài liệu">
            <div className="doc-row header-row" role="row">
              <span role="columnheader" aria-label="Bật tra cứu" />
              <span role="columnheader">Tài liệu</span>
              <span role="columnheader">Danh mục</span>
              <span role="columnheader">Số đoạn</span>
              <span role="columnheader">Trạng thái</span>
              <span role="columnheader" aria-label="Thao tác" />
            </div>

            {filteredDocs.length === 0 ? (
              <div style={{ padding: '28px 20px', color: 'var(--ink-muted)', fontSize: 14 }}>
                Không tìm thấy tài liệu phù hợp với bộ lọc hiện tại.
              </div>
            ) : (
              filteredDocs.map((doc) => (
                <div
                  key={doc.id}
                  role="row"
                  className={`doc-row ${!doc.enabled ? 'disabled' : ''}`}
                >
                  <div role="cell">
                    <input
                      type="checkbox"
                      className="scope-checkbox"
                      checked={doc.enabled}
                      disabled={doc.status !== 'ready'}
                      onChange={() => onToggleDocument(doc.id)}
                      aria-label={`Dùng tài liệu ${doc.title} khi hỏi đáp`}
                    />
                  </div>

                  <div className="doc-title-cell" role="cell">
                    <p className="doc-name" title={doc.title}>
                      {doc.title}
                    </p>
                    <div className="doc-sub-meta">
                      {doc.filename} ({doc.sizeLabel}) — Cập nhật {doc.updatedAt}
                    </div>
                  </div>

                  <div className="doc-hide-sm" role="cell">
                    <span className="doc-category-tag">{doc.category}</span>
                  </div>

                  <div className="doc-hide-sm doc-mono" role="cell">
                    {doc.chunkCount}
                  </div>

                  <div className="doc-hide-sm" role="cell">
                    {renderStatus(doc.status)}
                  </div>

                  <div role="cell">
                    <button
                      type="button"
                      className="delete-btn"
                      onClick={() => onDeleteDocument(doc.id)}
                      title={`Xóa tài liệu ${doc.title}`}
                      aria-label={`Xóa tài liệu ${doc.title}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
