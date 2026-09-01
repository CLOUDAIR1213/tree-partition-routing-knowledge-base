import {
  ArrowLeft,
  Check,
  FileText,
  Layers3,
  LoaderCircle,
  RotateCcw,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, ApiTimeoutError, documentsApi } from "../api/client";
import type {
  ChunkPreviewResponse,
  DocumentDetailResponse,
  Partition,
} from "../api/types";
import { ChunkPreviewList } from "../components/ChunkPreviewList";
import { DocumentStatusBadge } from "../components/DocumentStatusBadge";
import { PartitionSelector } from "../components/PartitionSelector";
import { formatFileSize } from "../components/UploadDropzone";
import { partitionLabels } from "../constants/partitions";

const PAGE_SIZE = 20;

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function reviewErrorMessage(error: unknown) {
  if (error instanceof ApiTimeoutError) return "请求超时，当前填写内容已保留，请手动重试。";
  if (!(error instanceof ApiError)) return "无法连接后端服务，请检查后端是否已启动。";
  switch (error.body.code) {
    case "DOCUMENT_NOT_FOUND":
    case "NOT_FOUND":
      return "文档不存在或已被移除。";
    case "INVALID_DOCUMENT_STATE":
      return "文档状态已变化，请刷新后重试。";
    case "REVIEW_PARTITION_REQUIRED":
      return "批准入库前必须选择最终分区。";
    case "INDEX_WRITE_FAILED":
      return `索引写入失败，文档未完成入库（请求 ID：${error.body.request_id}）`;
    default:
      return `${error.body.message}（请求 ID：${error.body.request_id}）`;
  }
}

export function ReviewPage() {
  const { documentId = "" } = useParams();
  const [document, setDocument] = useState<DocumentDetailResponse | null>(null);
  const [preview, setPreview] = useState<ChunkPreviewResponse | null>(null);
  const [confirmedPartition, setConfirmedPartition] = useState<Partition | null>(null);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [action, setAction] = useState<"approve" | "reject" | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const loadDocument = useCallback(async () => {
    if (!documentId) return;
    setLoading(true);
    setPageError(null);
    try {
      const [detail, chunks] = await Promise.all([
        documentsApi.get(documentId),
        documentsApi.preview(documentId, { limit: PAGE_SIZE, offset: 0 }),
      ]);
      setDocument(detail);
      setPreview(chunks);
      setConfirmedPartition(detail.confirmed_partition ?? detail.selected_partition);
      setNote(detail.review_note ?? "");
    } catch (error) {
      setPageError(reviewErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    void loadDocument();
  }, [loadDocument]);

  async function changePage(page: number) {
    if (!documentId) return;
    setPreviewLoading(true);
    try {
      const chunks = await documentsApi.preview(documentId, {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      setPreview(chunks);
    } catch (error) {
      setReviewError(reviewErrorMessage(error));
    } finally {
      setPreviewLoading(false);
    }
  }

  async function approve() {
    if (!confirmedPartition || !document) {
      setReviewError("批准入库前必须选择最终分区。");
      return;
    }
    setAction("approve");
    setReviewError(null);
    try {
      const response = await documentsApi.review(document.document_id, {
        action: "approve",
        confirmed_partition: confirmedPartition,
        reviewer_name: null,
        note: note.trim() || null,
      });
      setDocument((current) =>
        current
          ? {
              ...current,
              status: response.status,
              confirmed_partition: response.confirmed_partition,
              reviewed_at: response.reviewed_at,
              review_note: response.review_note,
              updated_at: response.reviewed_at,
            }
          : current,
      );
    } catch (error) {
      setReviewError(reviewErrorMessage(error));
    } finally {
      setAction(null);
    }
  }

  async function reject() {
    if (!document || !rejectReason.trim()) return;
    setAction("reject");
    setReviewError(null);
    try {
      const response = await documentsApi.review(document.document_id, {
        action: "reject",
        confirmed_partition: null,
        reviewer_name: null,
        note: rejectReason.trim(),
      });
      setDocument((current) =>
        current
          ? {
              ...current,
              status: response.status,
              confirmed_partition: response.confirmed_partition,
              reviewed_at: response.reviewed_at,
              review_note: response.review_note,
              updated_at: response.reviewed_at,
            }
          : current,
      );
      setRejectOpen(false);
    } catch (error) {
      setReviewError(reviewErrorMessage(error));
    } finally {
      setAction(null);
    }
  }

  if (loading) {
    return (
      <div className="standard-page centered-page-state" role="status">
        <LoaderCircle aria-hidden="true" className="spin" size={22} />
        正在读取文档状态
      </div>
    );
  }

  if (pageError || !document || !preview) {
    return (
      <div className="standard-page review-error-state">
        <h1>无法打开审核页面</h1>
        <p>{pageError || "文档预览尚未就绪。"}</p>
        <div>
          <button className="secondary-button" onClick={() => void loadDocument()} type="button">
            <RotateCcw aria-hidden="true" size={16} />
            重新读取
          </button>
          <Link className="secondary-button" to="/knowledge/upload">
            返回上传
          </Link>
        </div>
      </div>
    );
  }

  const reviewable = document.status === "pending_review";

  return (
    <div className="standard-page review-page">
      <div className="review-title-row">
        <Link aria-label="返回上传" className="icon-button" to="/knowledge/upload">
          <ArrowLeft aria-hidden="true" size={19} />
        </Link>
        <div>
          <span>文档审核</span>
          <h1>{document.title || document.original_filename}</h1>
        </div>
        <DocumentStatusBadge status={document.status} />
      </div>

      <section className="document-summary" aria-label="文档信息">
        <div>
          <FileText aria-hidden="true" size={17} />
          <span><small>文件</small><strong>{document.original_filename}</strong></span>
        </div>
        <div>
          <Layers3 aria-hidden="true" size={17} />
          <span><small>Chunk</small><strong>{document.chunk_count} 条</strong></span>
        </div>
        <div>
          <span><small>文件大小</small><strong>{formatFileSize(document.size_bytes)}</strong></span>
        </div>
        <div>
          <span><small>创建时间</small><strong>{formatDate(document.created_at)}</strong></span>
        </div>
      </section>

      {document.error_message && (
        <div className="page-alert" role="alert">
          {document.error_message} {document.error_code && `（${document.error_code}）`}
        </div>
      )}

      <ChunkPreviewList data={preview} loading={previewLoading} onPageChange={changePage} />

      <section className="review-section" aria-labelledby="review-heading">
        <div className="section-heading-row">
          <div>
            <h2 id="review-heading">审核入库</h2>
            <p>确认 Chunk 内容，并决定文档最终进入的唯一分区。</p>
          </div>
        </div>

        <div className="partition-comparison">
          <span>上传选择 <strong>{partitionLabels[document.selected_partition]}</strong></span>
          <span>最终确认 <strong>{confirmedPartition ? partitionLabels[confirmedPartition] : "未选择"}</strong></span>
        </div>

        <PartitionSelector
          disabled={!reviewable || Boolean(action)}
          layout="list"
          onChange={(value) => setConfirmedPartition(value)}
          value={confirmedPartition}
        />

        <div className="form-field review-note-field">
          <label htmlFor="review-note">审核备注 <span>选填</span></label>
          <textarea
            disabled={!reviewable || Boolean(action)}
            id="review-note"
            maxLength={500}
            onChange={(event) => setNote(event.target.value)}
            placeholder="记录分区修正或审核结论"
            rows={3}
            value={note}
          />
          <small>{note.length}/500</small>
        </div>

        {reviewError && <div className="page-alert review-action-error" role="alert">{reviewError}</div>}

        <div className="review-actions">
          {reviewable ? (
            <>
              <button
                className="reject-button"
                disabled={Boolean(action)}
                onClick={() => setRejectOpen(true)}
                type="button"
              >
                <X aria-hidden="true" size={17} />
                拒绝
              </button>
              <button
                className="review-primary-button"
                disabled={!confirmedPartition || Boolean(action)}
                onClick={() => void approve()}
                type="button"
              >
                {action === "approve" ? (
                  <LoaderCircle aria-hidden="true" className="spin" size={17} />
                ) : (
                  <Check aria-hidden="true" size={17} />
                )}
                {action === "approve" ? "正在入库" : "批准入库"}
              </button>
            </>
          ) : document.status === "ready" && document.confirmed_partition ? (
            <Link className="review-primary-button" to={`/?partition=${document.confirmed_partition}`}>
              返回问答并选择{partitionLabels[document.confirmed_partition]}
            </Link>
          ) : (
            <Link className="secondary-button" to="/knowledge/upload">继续上传文档</Link>
          )}
        </div>
      </section>

      {rejectOpen && (
        <div className="dialog-backdrop" role="presentation">
          <div aria-labelledby="reject-dialog-title" aria-modal="true" className="confirm-dialog" role="dialog">
            <h2 id="reject-dialog-title">拒绝这份文档？</h2>
            <p>拒绝后不会写入任何知识分区，请填写简短原因。</p>
            <label htmlFor="reject-reason">拒绝原因</label>
            <textarea
              autoFocus
              id="reject-reason"
              maxLength={500}
              onChange={(event) => setRejectReason(event.target.value)}
              rows={3}
              value={rejectReason}
            />
            <div className="dialog-actions">
              <button className="secondary-button" disabled={action === "reject"} onClick={() => setRejectOpen(false)} type="button">
                取消
              </button>
              <button className="reject-confirm-button" disabled={!rejectReason.trim() || action === "reject"} onClick={() => void reject()} type="button">
                {action === "reject" ? "正在拒绝" : "确认拒绝"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
