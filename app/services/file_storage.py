import hashlib
import json
import re
import shutil
from pathlib import Path

from app.core.errors import AppError

MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class StoredUpload:
    def __init__(
        self,
        *,
        original_filename: str,
        path: Path,
        mime_type: str,
        size_bytes: int,
        checksum_sha256: str,
    ) -> None:
        self.original_filename = original_filename
        self.path = path
        self.mime_type = mime_type
        self.size_bytes = size_bytes
        self.checksum_sha256 = checksum_sha256


class FileStorage:
    def __init__(
        self,
        raw_root: Path,
        staging_root: Path,
        max_size_bytes: int,
        allowed_types: tuple[str, ...],
    ) -> None:
        self.raw_root = raw_root.resolve()
        self.staging_root = staging_root.resolve()
        self.max_size_bytes = max_size_bytes
        self.allowed_extensions = {f".{item.lower().lstrip('.')}" for item in allowed_types}

    def validate_and_store(
        self,
        document_id: str,
        original_filename: str,
        content: bytes,
    ) -> StoredUpload:
        display_name = self._display_filename(original_filename)
        suffix = Path(display_name).suffix.lower()
        if suffix not in self.allowed_extensions or suffix not in MIME_BY_EXTENSION:
            raise AppError(
                "UNSUPPORTED_FILE_TYPE", "仅支持 PDF、DOCX、TXT 和 Markdown", 415
            )
        if not content:
            raise AppError("EMPTY_DOCUMENT", "上传文件为空", 422)
        if len(content) > self.max_size_bytes:
            raise AppError(
                "FILE_TOO_LARGE",
                "上传文件超过大小限制",
                413,
                {"max_size_bytes": self.max_size_bytes},
            )

        mime_type = self._detect_mime(suffix, content)
        target_dir = (self.raw_root / document_id).resolve()
        if self.raw_root not in target_dir.parents:
            raise AppError("VALIDATION_ERROR", "非法文档路径", 422)
        target_dir.mkdir(parents=True, exist_ok=False)
        target_path = target_dir / f"document{suffix}"
        target_path.write_bytes(content)
        return StoredUpload(
            original_filename=display_name,
            path=target_path,
            mime_type=mime_type,
            size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
        )

    def write_parse_snapshot(self, document_id: str, payload: dict) -> None:
        target_dir = (self.staging_root / document_id).resolve()
        if self.staging_root not in target_dir.parents:
            raise AppError("VALIDATION_ERROR", "非法暂存路径", 422)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "parse.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def remove_document(self, document_id: str) -> None:
        for root in (self.raw_root, self.staging_root):
            target = (root / document_id).resolve()
            if root in target.parents and target.exists():
                shutil.rmtree(target)

    @staticmethod
    def _display_filename(filename: str) -> str:
        normalized = filename.replace("\\", "/")
        name = normalized.rsplit("/", 1)[-1]
        name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
        return name[:255] or "document"

    @staticmethod
    def _detect_mime(suffix: str, content: bytes) -> str:
        if suffix == ".pdf":
            if not content.startswith(b"%PDF-"):
                raise AppError("UNSUPPORTED_FILE_TYPE", "PDF 文件签名不匹配", 415)
        elif suffix == ".docx":
            if not content.startswith(b"PK") or b"[Content_Types].xml" not in content:
                raise AppError("UNSUPPORTED_FILE_TYPE", "DOCX 文件签名不匹配", 415)
        else:
            try:
                content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise AppError(
                    "DOCUMENT_PARSE_FAILED", "文本文件必须使用 UTF-8 编码", 422
                ) from exc
            if content.startswith((b"%PDF-", b"PK\x03\x04")):
                raise AppError("UNSUPPORTED_FILE_TYPE", "文件内容与扩展名不匹配", 415)
        return MIME_BY_EXTENSION[suffix]

