import { FileText, FileUp, RefreshCw } from "lucide-react";
import { useState, type DragEvent } from "react";

const MAX_FILE_SIZE = 25 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(["pdf", "docx", "txt", "md"]);

export function validateUploadFile(file: File) {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    return "仅支持 PDF、DOCX、TXT 和 Markdown 文件";
  }
  if (file.size > MAX_FILE_SIZE) return "文件不能超过 25 MB";
  if (file.size === 0) return "不能上传空文件";
  return null;
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

interface UploadDropzoneProps {
  file: File | null;
  error: string | null;
  disabled?: boolean;
  onFile: (file: File | null) => void;
  onError: (message: string | null) => void;
}

export function UploadDropzone({
  file,
  error,
  disabled = false,
  onFile,
  onError,
}: UploadDropzoneProps) {
  const [dragging, setDragging] = useState(false);

  function acceptFile(nextFile: File | undefined) {
    if (!nextFile) return;
    const message = validateUploadFile(nextFile);
    onError(message);
    onFile(message ? null : nextFile);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) acceptFile(event.dataTransfer.files[0]);
  }

  return (
    <div>
      <div
        className="upload-dropzone"
        data-dragging={dragging}
        data-error={Boolean(error)}
        data-filled={Boolean(file)}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={onDrop}
      >
        <input
          accept=".pdf,.docx,.txt,.md"
          aria-describedby={error ? "upload-file-error" : "upload-file-help"}
          disabled={disabled}
          id="knowledge-file"
          onChange={(event) => acceptFile(event.target.files?.[0])}
          type="file"
        />
        <label htmlFor="knowledge-file">
          {file ? (
            <>
              <span className="dropzone-icon dropzone-icon--file">
                <FileText aria-hidden="true" size={21} />
              </span>
              <span className="dropzone-file-copy">
                <strong>{file.name}</strong>
                <small>
                  {file.type || "未知类型"} · {formatFileSize(file.size)}
                </small>
              </span>
              <span className="dropzone-replace">
                <RefreshCw aria-hidden="true" size={14} />
                替换
              </span>
            </>
          ) : (
            <>
              <span className="dropzone-icon">
                <FileUp aria-hidden="true" size={22} />
              </span>
              <span className="dropzone-file-copy">
                <strong>选择文件或拖放到这里</strong>
                <small id="upload-file-help">PDF、DOCX、TXT、MD，最大 25 MB</small>
              </span>
            </>
          )}
        </label>
      </div>
      {error && (
        <p className="field-error" id="upload-file-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
