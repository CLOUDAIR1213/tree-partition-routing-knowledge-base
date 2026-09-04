import { ChevronLeft, ChevronRight, FilePlus2, LoaderCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, ApiTimeoutError, documentsApi } from "../api/client";
import type { DocumentListResponse, DocumentStatus, Partition } from "../api/types";
import { KnowledgeDocumentTable } from "../components/KnowledgeDocumentTable";
import { KnowledgeFilters } from "../components/KnowledgeFilters";

const PAGE_SIZE = 20;
const statuses = new Set<DocumentStatus>([
  "uploaded",
  "parsing",
  "pending_review",
  "indexing",
  "reindexing",
  "deleting",
  "ready",
  "rejected",
  "failed",
]);
const partitions = new Set<Partition>(["finance", "hr", "tech"]);

function toPage(value: string | null) {
  const page = Number(value);
  return Number.isInteger(page) && page > 0 ? page : 1;
}

function listErrorMessage(error: unknown) {
  if (error instanceof ApiTimeoutError) return "读取知识库超时，请重试。";
  if (error instanceof ApiError) return `${error.body.message}（请求 ID：${error.body.request_id}）`;
  return "无法连接后端服务，请检查后端是否已启动。";
}

export function KnowledgeLibraryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const rawStatus = searchParams.get("status");
  const rawPartition = searchParams.get("partition");
  const status = rawStatus && statuses.has(rawStatus as DocumentStatus)
    ? (rawStatus as DocumentStatus)
    : null;
  const partition = rawPartition && partitions.has(rawPartition as Partition)
    ? (rawPartition as Partition)
    : null;
  const page = toPage(searchParams.get("page"));
  const [data, setData] = useState<DocumentListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);

  const updateParams = useCallback((changes: Record<string, string | null>) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      Object.entries(changes).forEach(([key, value]) => {
        if (value) next.set(key, value);
        else next.delete(key);
      });
      return next;
    });
  }, [setSearchParams]);

  const load = useCallback(async () => {
    const request = ++sequence.current;
    setLoading(true);
    setError(null);
    try {
      const response = await documentsApi.list({
        q: query || undefined,
        status: status ?? undefined,
        partition: partition ?? undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      if (request === sequence.current) setData(response);
    } catch (loadError) {
      if (request === sequence.current) setError(listErrorMessage(loadError));
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  }, [page, partition, query, status]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 300);
    return () => window.clearTimeout(timer);
  }, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const start = data?.total ? (page - 1) * PAGE_SIZE + 1 : 0;
  const end = data ? Math.min(page * PAGE_SIZE, data.total) : 0;

  useEffect(() => {
    if (data && page > totalPages) updateParams({ page: String(totalPages) });
  }, [data, page, totalPages, updateParams]);

  return (
    <div className="standard-page knowledge-library-page">
      <div className="knowledge-page-heading">
        <div>
          <span>知识库</span>
          <h1>文档目录</h1>
          <p>查看文档状态、分区与原始 Chunk 顺序。</p>
        </div>
        <Link className="review-primary-button" to="/knowledge/upload">
          <FilePlus2 aria-hidden="true" size={17} />
          上传知识
        </Link>
      </div>

      <KnowledgeFilters
        onClear={() => updateParams({ q: null, status: null, partition: null, page: null })}
        onPartitionChange={(value) => updateParams({ partition: value, page: null })}
        onQueryChange={(value) => updateParams({ q: value || null, page: null })}
        onStatusChange={(value) => updateParams({ status: value, page: null })}
        partition={partition}
        query={query}
        status={status}
      />

      {error ? (
        <div className="knowledge-error" role="alert">
          <p>{error}</p>
          <button className="secondary-button" onClick={() => void load()} type="button">
            重新加载
          </button>
        </div>
      ) : loading && !data ? (
        <div className="centered-page-state" role="status">
          <LoaderCircle aria-hidden="true" className="spin" size={22} />
          正在读取知识库
        </div>
      ) : data?.items.length ? (
        <>
          <div className="knowledge-result-count">
            共 {data.total} 份文档，显示第 {start}-{end} 份
          </div>
          <KnowledgeDocumentTable documents={data.items} />
          <nav className="pagination" aria-label="文档分页">
            <button
              disabled={page <= 1 || loading}
              onClick={() => updateParams({ page: String(page - 1) })}
              type="button"
            >
              <ChevronLeft aria-hidden="true" size={16} />
              上一页
            </button>
            <span>第 {page} 页，共 {totalPages} 页</span>
            <button
              disabled={page >= totalPages || loading}
              onClick={() => updateParams({ page: String(page + 1) })}
              type="button"
            >
              下一页
              <ChevronRight aria-hidden="true" size={16} />
            </button>
          </nav>
        </>
      ) : (
        <div className="knowledge-empty">
          <h2>没有匹配的文档</h2>
          <p>{query || status || partition ? "调整筛选条件后再试。" : "上传第一份知识文档后，它会显示在这里。"}</p>
          {query || status || partition ? (
            <button className="secondary-button" onClick={() => updateParams({ q: null, status: null, partition: null, page: null })} type="button">
              清除筛选
            </button>
          ) : (
            <Link className="review-primary-button" to="/knowledge/upload">上传知识</Link>
          )}
        </div>
      )}
    </div>
  );
}
