import {
  ArrowLeft,
  ArrowRightLeft,
  Check,
  FileText,
  Layers3,
  LoaderCircle,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, ApiTimeoutError, documentsApi } from "../api/client";
import type {
  ChunkPreviewResponse,
  DocumentDetailResponse,
  Partition,
} from "../api/types";
import { ChunkPreviewList } from "../components/ChunkPreviewList";
import { DocumentStatusBadge } from "../components/DocumentStatusBadge";
import { ParseQualitySummary } from "../components/ParseQualitySummary";
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
    case "PARTITION_UNCHANGED":
      return "请选择与当前不同的分区。";
    case "PARTITION_CHANGE_FAILED":
      return `更改分区失败，系统已尝试恢复原索引（请求 ID：${error.body.request_id}）`;
    case "REOPEN_REVIEW_FAILED":
      return `退回重新审核失败，系统已尝试恢复原索引（请求 ID：${error.body.request_id}）`;
    case "DOCUMENT_DELETE_FAILED":
      return `文档未完成全部删除，可重试（请求 ID：${error.body.request_id}）`;
    default:
      return `${error.body.message}（请求 ID：${error.body.request_id}）`;
  }
}

export function ReviewPage() {
  const { documentId = "" } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState<DocumentDetailResponse | null>(null);
  const [preview, setPreview] = useState<ChunkPreviewResponse | null>(null);
  const [confirmedPartition, setConfirmedPartition] = useState<Partition | null>(null);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [action, setAction] = useState<
    "approve" | "reject" | "change_partition" | "reopen" | "delete" | null
  >(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [managementDialog, setManagementDialog] = useState<
    "change_partition" | "reopen" | "delete" | null
  >(null);
  const [managementPartition, setManagementPartition] = useState<Partition | null>(null);
  const [managementNote, setManagementNote] = useState("");
  const [managementError, setManagementError] = useState<string | null>(null);

  const loadDocument = useCallback(async () => {
    if (!documentId) return;
    setLoading(true);
    setPageError(null);
    try {
      const detail = await documentsApi.get(documentId);
      setDocument(detail);
      setConfirmedPartition(detail.confirmed_partition ?? null);
      setNote(detail.review_note ?? "");
      setPreview(null);
      setPreviewError(null);
      if (detail.chunk_count > 0) {
        try {
          const chunks = await documentsApi.preview(documentId, {
            limit: PAGE_SIZE,
            offset: 0,
          });
          setPreview(chunks);
        } catch (error) {
          setPreviewError(reviewErrorMessage(error));
        }
      }
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
    setPreviewError(null);
    try {
      const chunks = await documentsApi.preview(documentId, {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      setPreview(chunks);
    } catch (error) {
      setPreviewError(reviewErrorMessage(error));
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

  function openManagementDialog(kind: "change_partition" | "reopen" | "delete") {
    setManagementError(null);
    setManagementNote("");
    setManagementPartition(document?.confirmed_partition ?? null);
    setManagementDialog(kind);
  }

  async function changePartition() {
    if (!document || !managementPartition) return;
    if (managementPartition === document.confirmed_partition) {
      setManagementError("请选择与当前不同的分区。");
      return;
    }
    setAction("change_partition");
    setManagementError(null);
    try {
      await documentsApi.changePartition(document.document_id, {
        confirmed_partition: managementPartition,
        reviewer_name: null,
        note: managementNote.trim() || null,
      });
      setManagementDialog(null);
      await loadDocument();
    } catch (error) {
      setManagementError(reviewErrorMessage(error));
    } finally {
      setAction(null);
    }
  }

  async function reopenReview() {
    if (!document) return;
    setAction("reopen");
    setManagementError(null);
    try {
      await documentsApi.reopenReview(document.document_id, {
        reviewer_name: null,
        note: managementNote.trim() || null,
      });
      setManagementDialog(null);
      await loadDocument();
    } catch (error) {
      setManagementError(reviewErrorMessage(error));
    } finally {
      setAction(null);
    }
  }

  async function deleteDocument() {
    if (!document) return;
    setAction("delete");
    setManagementError(null);
    try {
      await documentsApi.delete(document.document_id);
      navigate("/knowledge", { replace: true });
    } catch (error) {
      setManagementError(reviewErrorMessage(error));
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

  if (pageError || !document) {
    return (
      <div className="standard-page review-error-state">
        <h1>无法打开文档</h1>
        <p>{pageError || "文档不存在或暂时不可读取。"}</p>
        <div>
          <button className="secondary-button" onClick={() => void loadDocument()} type="button">
            <RotateCcw aria-hidden="true" size={16} />
            重新读取
          </button>
          <Link className="secondary-button" to="/knowledge">
            返回知识库
          </Link>
        </div>
      </div>
    );
  }

  const reviewable = document.status === "pending_review";
  const previewReady = Boolean(preview) && !previewLoading && !previewError;
  const ready = document.status === "ready" && Boolean(document.confirmed_partition);
  const deletable = ["pending_review", "ready", "rejected", "failed"].includes(
    document.status,
  );

  return (
    <div className="standard-page review-page">
      <div className="review-title-row">
        <Link aria-label="返回知识库" className="icon-button" to="/knowledge">
          <ArrowLeft aria-hidden="true" size={19} />
        </Link>
        <div>
          <span>文档详情</span>
          <h1>{document.title || document.original_filename}</h1>
        </div>
        <div className="review-title-status">
          <DocumentStatusBadge status={document.status} />
        </div>
      </div>

      <section className="document-summary" aria-label="文档信息">
        <div className="document-summary-primary">
          <FileText aria-hidden="true" size={17} />
          <span><small>文件</small><strong>{document.original_filename}</strong></span>
        </div>
        <div>
          <span><small>初选分区</small><strong>{partitionLabels[document.selected_partition]}</strong></span>
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

      <ParseQualitySummary quality={document.parse_quality} />

      {document.error_message && (
        <div className="page-alert" role="alert">
          {document.error_message} {document.error_code && `（${document.error_code}）`}
        </div>
      )}

      {preview ? (
        <ChunkPreviewList data={preview} loading={previewLoading} onPageChange={changePage} />
      ) : (
        <section className="chunk-section chunk-unavailable" aria-labelledby="chunk-heading">
          <div className="section-heading-row">
            <div>
              <h2 id="chunk-heading">Chunk 预览</h2>
              <p>{previewError || "文档正在处理，暂未生成可预览的 Chunk。"}</p>
            </div>
            {document.chunk_count > 0 && (
              <button className="secondary-button" onClick={() => void loadDocument()} type="button">
                重新读取
              </button>
            )}
          </div>
        </section>
      )}

      <section className="review-section" aria-labelledby="review-heading">
        <div className="section-heading-row">
          <div>
            <h2 id="review-heading">审核入库</h2>
            <p>确认 Chunk 内容，并决定文档最终进入的唯一分区。</p>
          </div>
        </div>

        <div className="partition-comparison">
          <span>上传选择 <strong>{partitionLabels[document.selected_partition]}</strong></span>
          <span>内容建议 <strong>{document.parse_quality?.partition_suggestion.partition ? partitionLabels[document.parse_quality.partition_suggestion.partition] : "未形成唯一建议"}</strong></span>
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
        {reviewable && !previewReady && (
          <div className="page-alert review-action-error" role="alert">
            Chunk 完整预览不可用，无法批准入库。请重新读取或检查解析状态。
          </div>
        )}

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
                disabled={!confirmedPartition || !previewReady || Boolean(action)}
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

      <section className="document-management-section" aria-labelledby="management-heading">
        <div className="section-heading-row">
          <div>
            <h2 id="management-heading">文档管理</h2>
          </div>
        </div>
        {managementError && (
          <div className="page-alert review-action-error" role="alert">{managementError}</div>
        )}
        <div className="management-actions">
          {ready && (
            <>
              <button
                className="secondary-button"
                disabled={Boolean(action)}
                onClick={() => openManagementDialog("change_partition")}
                type="button"
              >
                <ArrowRightLeft aria-hidden="true" size={16} />
                更改分区
              </button>
              <button
                className="secondary-button"
                disabled={Boolean(action)}
                onClick={() => openManagementDialog("reopen")}
                type="button"
              >
                <RotateCcw aria-hidden="true" size={16} />
                重新审核
              </button>
            </>
          )}
          {deletable && (
            <button
              className="reject-button"
              disabled={Boolean(action)}
              onClick={() => openManagementDialog("delete")}
              type="button"
            >
              <Trash2 aria-hidden="true" size={16} />
              删除文档
            </button>
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

      {managementDialog && (
        <div className="dialog-backdrop" role="presentation">
          <div
            aria-labelledby="management-dialog-title"
            aria-modal="true"
            className="confirm-dialog management-dialog"
            role="dialog"
          >
            <h2 id="management-dialog-title">
              {managementDialog === "change_partition"
                ? "更改文档分区"
                : managementDialog === "reopen"
                  ? "退回重新审核？"
                  : "删除这份文档？"}
            </h2>
            <p>
              {managementDialog === "change_partition"
                ? "文档 Chunk 将从旧分区移除并写入新分区。"
                : managementDialog === "reopen"
                  ? "文档将从索引移除并回到待审核状态。"
                  : "原文件、解析快照、Chunk 和索引数据都会被删除，且无法撤销。"}
            </p>

            {managementDialog === "change_partition" && (
              <PartitionSelector
                disabled={action === "change_partition"}
                layout="segmented"
                legend="选择新的知识分区"
                onChange={setManagementPartition}
                value={managementPartition}
              />
            )}

            {managementDialog !== "delete" && (
              <div className="form-field management-note-field">
                <label htmlFor="management-note">操作备注 <span>选填</span></label>
                <textarea
                  disabled={Boolean(action)}
                  id="management-note"
                  maxLength={500}
                  onChange={(event) => setManagementNote(event.target.value)}
                  rows={2}
                  value={managementNote}
                />
                <small>{managementNote.length}/500</small>
              </div>
            )}

            {managementError && (
              <div className="page-alert review-action-error" role="alert">{managementError}</div>
            )}
            <div className="dialog-actions">
              <button
                className="secondary-button"
                disabled={Boolean(action)}
                onClick={() => setManagementDialog(null)}
                type="button"
              >
                取消
              </button>
              {managementDialog === "change_partition" ? (
                <button
                  className="review-primary-button"
                  disabled={
                    !managementPartition ||
                    managementPartition === document.confirmed_partition ||
                    action === "change_partition"
                  }
                  onClick={() => void changePartition()}
                  type="button"
                >
                  {action === "change_partition" ? "正在调整" : "确认更改"}
                </button>
              ) : managementDialog === "reopen" ? (
                <button
                  className="review-primary-button"
                  disabled={action === "reopen"}
                  onClick={() => void reopenReview()}
                  type="button"
                >
                  {action === "reopen" ? "正在退回" : "确认重新审核"}
                </button>
              ) : (
                <button
                  className="reject-confirm-button"
                  disabled={action === "delete"}
                  onClick={() => void deleteDocument()}
                  type="button"
                >
                  {action === "delete" ? "正在删除" : "确认删除"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
