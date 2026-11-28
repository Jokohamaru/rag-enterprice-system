import type { ReactNode } from 'react';
import type { CitationItem } from '../types/rag';

interface InlineCitationOptions {
  citations?: CitationItem[];
  selectedCitationId?: string | null;
  messageId?: string;
  onSelectCitation?: (messageId: string, citation: CitationItem) => void;
}

function renderInline(text: string, opts: InlineCitationOptions): ReactNode[] {
  // Match **bold**, *italic*, `code`, or [n] citation marker
  const tokenRegex = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`\n]+`|\[\d+\])/g;
  const parts = text.split(tokenRegex);

  return parts.map((part, idx) => {
    if (!part) return null;

    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={idx}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={idx}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={idx} className="md-inline-code">
          {part.slice(1, -1)}
        </code>
      );
    }

    const citMatch = part.match(/^\[(\d+)\]$/);
    if (citMatch && opts.citations && opts.onSelectCitation && opts.messageId) {
      const num = Number(citMatch[1]);
      const found = opts.citations.find((c) => c.citationNumber === num);
      if (found) {
        const isActive = opts.selectedCitationId === found.id;
        const excerpt = found.highlight || found.content.slice(0, 140);
        return (
          <span key={idx} className="citation-wrap">
            <button
              type="button"
              className={`citation-chip ${isActive ? 'active' : ''}`}
              onClick={() => opts.onSelectCitation?.(opts.messageId!, found)}
              aria-label={`Nguồn [${num}]: ${found.documentTitle}`}
            >
              {num}
            </button>
            <span className="citation-tooltip" role="tooltip">
              <strong className="citation-tooltip-title">
                [{num}] {found.documentTitle}
              </strong>
              <span className="citation-tooltip-meta">
                {found.section}
                {found.page != null ? ` · Tr. ${found.page}` : ''}
              </span>
              <span className="citation-tooltip-excerpt">“{excerpt}”</span>
            </span>
          </span>
        );
      }
    }

    return <span key={idx}>{part}</span>;
  });
}

function isTableSeparator(line: string): boolean {
  return /^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{0,}:?\s*\|?$/.test(line.trim());
}

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return trimmed.split('|').map((cell) => cell.trim());
}

export function renderMarkdown(
  content: string,
  opts: InlineCitationOptions = {}
): ReactNode {
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  const nodes: ReactNode[] = [];
  let i = 0;
  let keyCounter = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    // Fenced code block
    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i += 1;
      }
      i += 1;
      nodes.push(
        <pre key={`code-${keyCounter++}`} className="md-code-block" data-lang={lang || undefined}>
          <code>{codeLines.join('\n')}</code>
        </pre>
      );
      continue;
    }

    // Headings
    const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const cls = `md-h${level}`;
      if (level === 1) {
        nodes.push(<h3 key={`h-${keyCounter++}`} className={cls}>{renderInline(text, opts)}</h3>);
      } else if (level === 2) {
        nodes.push(<h4 key={`h-${keyCounter++}`} className={cls}>{renderInline(text, opts)}</h4>);
      } else {
        nodes.push(<h5 key={`h-${keyCounter++}`} className={cls}>{renderInline(text, opts)}</h5>);
      }
      i += 1;
      continue;
    }

    // GFM Table
    if (trimmed.includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      const headers = splitTableRow(trimmed);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().includes('|')) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      nodes.push(
        <div key={`tbl-${keyCounter++}`} className="md-table-wrap">
          <table className="md-table">
            <thead>
              <tr>
                {headers.map((h, hIdx) => (
                  <th key={hIdx}>{renderInline(h, opts)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rIdx) => (
                <tr key={rIdx}>
                  {headers.map((_, cIdx) => (
                    <td key={cIdx}>{renderInline(row[cIdx] ?? '', opts)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Blockquote
    if (trimmed.startsWith('>')) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ''));
        i += 1;
      }
      nodes.push(
        <blockquote key={`bq-${keyCounter++}`} className="md-blockquote">
          {renderInline(quoteLines.join(' '), opts)}
        </blockquote>
      );
      continue;
    }

    // Unordered list
    if (/^[-*•]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) {
        items.push(lines[i].trim().replace(/^[-*•]\s+/, ''));
        i += 1;
      }
      nodes.push(
        <ul key={`ul-${keyCounter++}`} className="md-list">
          {items.map((item, idx) => (
            <li key={idx}>{renderInline(item, opts)}</li>
          ))}
        </ul>
      );
      continue;
    }

    // Ordered list
    if (/^\d+[.)]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].trim().replace(/^\d+[.)]\s+/, ''));
        i += 1;
      }
      nodes.push(
        <ol key={`ol-${keyCounter++}`} className="md-list md-list-ordered">
          {items.map((item, idx) => (
            <li key={idx}>{renderInline(item, opts)}</li>
          ))}
        </ol>
      );
      continue;
    }

    // Paragraph (collect consecutive non-special lines)
    const paraLines: string[] = [];
    while (i < lines.length) {
      const cur = lines[i].trim();
      if (
        !cur ||
        cur.startsWith('```') ||
        /^#{1,4}\s+/.test(cur) ||
        cur.startsWith('>') ||
        /^[-*•]\s+/.test(cur) ||
        /^\d+[.)]\s+/.test(cur) ||
        (cur.includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1]))
      ) {
        break;
      }
      paraLines.push(cur);
      i += 1;
    }

    if (paraLines.length > 0) {
      nodes.push(
        <p key={`p-${keyCounter++}`}>{renderInline(paraLines.join(' '), opts)}</p>
      );
    }
  }

  return nodes;
}
