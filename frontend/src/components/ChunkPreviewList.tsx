import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { useState } from "react";
import type { ChunkPreviewResponse } from "../api/types";

interface ChunkPreviewListProps {
  data: ChunkPreviewResponse;
  loading?: boolean;
  onPageChange: (page: number) => void;
}

function pageRange(start: number | null, end: number | null) {
  if (start === null) return "无页码";
  if (end === null || end === start) return `第 ${start} 页`;
  return `第 ${start}-${end} 页`;
}

export function ChunkPreviewList({
  data,
  loading = false,
  onPageChange,
}: ChunkPreviewListProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const page = Math.floor(data.offset / data.limit) + 1;
  const pageCount = Math.max(1, Math.ceil(data.total / data.limit));

  function toggle(chunkId: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  }

  return (
    <section className="chunk-section" aria-labelledby="chunk-heading" aria-busy={loading}>
      <div className="section-heading-row">
        <div>
          <h2 id="chunk-heading">Chunk 预览</h2>
          <p>共 {data.total} 条，当前每页 {data.limit} 条</p>
        </div>
        <span className="page-count">{page} / {pageCount}</span>
      </div>

      <ol className="chunk-list">
        {data.items.map((chunk) => {
          const isExpanded = expanded.has(chunk.chunk_id);
          const section = chunk.section_path || chunk.title || "未命名章节";
          return (
            <li key={chunk.chunk_id}>
              <div className="chunk-number">{chunk.chunk_index + 1}</div>
              <div className="chunk-copy">
                <div className="chunk-meta">
                  <strong>{section}</strong>
                  <span>{pageRange(chunk.page_start, chunk.page_end)}</span>
                </div>
                <p data-expanded={isExpanded}>{chunk.preview}</p>
                <div className="chunk-footer">
                  <code>{chunk.chunk_id}</code>
                  {chunk.preview.length > 150 && (
                    <button onClick={() => toggle(chunk.chunk_id)} type="button">
                      {isExpanded ? (
                        <ChevronUp aria-hidden="true" size={14} />
                      ) : (
                        <ChevronDown aria-hidden="true" size={14} />
                      )}
                      {isExpanded ? "收起" : "展开"}
                    </button>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      <nav className="pagination" aria-label="Chunk 分页">
        <button disabled={page <= 1 || loading} onClick={() => onPageChange(page - 1)} type="button">
          <ChevronLeft aria-hidden="true" size={16} />
          上一页
        </button>
        <span>第 {page} 页，共 {pageCount} 页</span>
        <button
          disabled={page >= pageCount || loading}
          onClick={() => onPageChange(page + 1)}
          type="button"
        >
          下一页
          <ChevronRight aria-hidden="true" size={16} />
        </button>
      </nav>
    </section>
  );
}
