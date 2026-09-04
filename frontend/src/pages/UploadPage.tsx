import { ArrowLeft, LoaderCircle, Upload, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, ApiTimeoutError, documentsApi } from "../api/client";
import type { Partition } from "../api/types";
import { PartitionSelector } from "../components/PartitionSelector";
import { UploadDropzone } from "../components/UploadDropzone";

function uploadErrorMessage(error: unknown) {
  if (error instanceof ApiTimeoutError) return "上传和解析超时，文件选择已保留，请手动重试。";
  if (!(error instanceof ApiError)) return "无法连接后端服务，请检查后端是否已启动。";
  switch (error.body.code) {
    case "UNSUPPORTED_FILE_TYPE":
      return "文件内容或扩展名不受支持，请重新选择文件。";
    case "FILE_TOO_LARGE":
      return "文件超过后端允许的大小限制。";
    case "EMPTY_DOCUMENT":
      return "文件中没有可解析的正文。";
    case "DOCUMENT_PARSE_FAILED":
      return `文档解析失败（请求 ID：${error.body.request_id}）`;
    default:
      return `${error.body.message}（请求 ID：${error.body.request_id}）`;
  }
}

export function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [partition, setPartition] = useState<Partition | null>(null);
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [duplicateId, setDuplicateId] = useState<string | null>(null);

  const canSubmit = Boolean(file && partition && !fileError && !submitting);

  async function submit() {
    if (!file || !partition || !canSubmit) return;
    setSubmitting(true);
    setPageError(null);
    setDuplicateId(null);
    try {
      const response = await documentsApi.upload({
        file,
        partition,
        title: title.trim() || undefined,
      });
      navigate(`/knowledge/documents/${response.document_id}`);
    } catch (error) {
      if (error instanceof ApiError && error.body.code === "DUPLICATE_DOCUMENT") {
        const documentId = error.body.details?.document_id;
        if (typeof documentId === "string") setDuplicateId(documentId);
      }
      setPageError(uploadErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="standard-page upload-page">
      <div className="page-heading-row">
        <div>
          <h1>上传知识库文档</h1>
          <p>选择一个文件和初始知识分区，解析完成后进入待审核区。</p>
        </div>
        <Link className="secondary-button" to="/">
          <ArrowLeft aria-hidden="true" size={17} />
          返回问答
        </Link>
      </div>

      {pageError && (
        <div className="page-alert upload-page-alert" role="alert">
          <span>{pageError}</span>
          {duplicateId && (
            <Link to={`/knowledge/review/${duplicateId}`}>
              查看已有文档
              <ExternalLink aria-hidden="true" size={14} />
            </Link>
          )}
        </div>
      )}

      <form
        className="upload-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <section className="upload-column" aria-labelledby="file-section-heading">
          <div className="form-section-heading">
            <span>1</span>
            <div>
              <h2 id="file-section-heading">选择文档</h2>
              <p>单次上传一个文件，新选择会替换当前文件。</p>
            </div>
          </div>
          <UploadDropzone
            disabled={submitting}
            error={fileError}
            file={file}
            onError={setFileError}
            onFile={setFile}
          />
          <div className="form-field">
            <label htmlFor="document-title">文档标题 <span>选填</span></label>
            <input
              disabled={submitting}
              id="document-title"
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="默认使用文件名（不含扩展名）"
              type="text"
              value={title}
            />
            <small>{title.length}/200</small>
          </div>
        </section>

        <section className="upload-column" aria-labelledby="partition-section-heading">
          <div className="form-section-heading">
            <span>2</span>
            <div>
              <h2 id="partition-section-heading">选择知识分区</h2>
              <p>审核时仍可修改最终入库分区。</p>
            </div>
          </div>
          <PartitionSelector
            disabled={submitting}
            layout="list"
            onChange={(value) => setPartition(value)}
            value={partition}
          />
          <div className="upload-submit-area">
            <p>提交后端将同步完成文件解析与 Chunking，请保持页面打开。</p>
            <button className="review-primary-button" disabled={!canSubmit} type="submit">
              {submitting ? (
                <LoaderCircle aria-hidden="true" className="spin" size={17} />
              ) : (
                <Upload aria-hidden="true" size={17} />
              )}
              {submitting ? "上传并解析中" : "上传并解析"}
            </button>
          </div>
        </section>
      </form>
    </div>
  );
}
