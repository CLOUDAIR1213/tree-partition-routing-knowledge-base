import secrets
from pathlib import Path

from anyio import to_thread
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.services.chunker import SectionChunker
from app.services.file_storage import FileStorage
from app.services.parser import StandardDocumentParser


class IngestionService:
    def __init__(self, settings: Settings) -> None:
        self.storage = FileStorage(
            settings.raw_root,
            settings.staging_root,
            settings.max_upload_size_bytes,
            settings.allowed_file_types,
        )
        self.parser = StandardDocumentParser()
        self.chunker = SectionChunker(
            settings.chunk_target_tokens,
            settings.chunk_min_tokens,
            settings.chunk_max_tokens,
            settings.chunk_overlap_tokens,
        )

    async def ingest(
        self,
        session: AsyncSession,
        *,
        original_filename: str,
        content: bytes,
        partition: Partition,
        custom_title: str | None,
    ) -> tuple[DocumentTable, list[str]]:
        checksum = __import__("hashlib").sha256(content).hexdigest()
        existing = await session.scalar(
            select(DocumentTable).where(
                DocumentTable.checksum_sha256 == checksum,
                DocumentTable.status.notin_(
                    [DocumentStatus.REJECTED.value, DocumentStatus.FAILED.value]
                ),
            )
        )
        if existing:
            raise AppError(
                "DUPLICATE_DOCUMENT",
                "相同内容的文档已存在",
                409,
                {"document_id": existing.id, "status": existing.status},
            )

        document_id = f"doc_{secrets.token_hex(12)}"
        stored = await to_thread.run_sync(
            self.storage.validate_and_store,
            document_id,
            original_filename,
            content,
        )
        document = DocumentTable(
            id=document_id,
            original_filename=stored.original_filename,
            stored_path=str(stored.path),
            mime_type=stored.mime_type,
            size_bytes=stored.size_bytes,
            checksum_sha256=stored.checksum_sha256,
            selected_partition=partition.value,
            title=custom_title,
            status=DocumentStatus.UPLOADED.value,
            chunk_count=0,
        )
        session.add(document)
        await session.commit()

        try:
            document.status = DocumentStatus.PARSING.value
            await session.commit()
            sections = await to_thread.run_sync(
                self.parser.parse, Path(document.stored_path), document.mime_type
            )
            title = custom_title or next(
                (section.title for section in sections if section.title),
                Path(document.original_filename).stem,
            )
            chunks = await to_thread.run_sync(
                self.chunker.chunk, document.id, title, sections
            )
            if not chunks:
                raise AppError("EMPTY_DOCUMENT", "文件没有可索引的正文", 422)
            for item in chunks:
                session.add(
                    ChunkCandidateTable(
                        id=item.chunk_id,
                        document_id=item.document_id,
                        chunk_index=item.chunk_index,
                        text=item.text,
                        embedding_text=item.embedding_text,
                        title=item.title,
                        section_path=item.section_path,
                        page_start=item.page_start,
                        page_end=item.page_end,
                        checksum_sha256=item.checksum_sha256,
                    )
                )
            document.title = title
            document.chunk_count = len(chunks)
            document.status = DocumentStatus.PENDING_REVIEW.value
            await session.commit()
            await session.refresh(document)
            await to_thread.run_sync(
                self.storage.write_parse_snapshot,
                document.id,
                {
                    "document_id": document.id,
                    "title": title,
                    "sections": [section.model_dump() for section in sections],
                    "chunk_ids": [chunk.chunk_id for chunk in chunks],
                },
            )
            return document, []
        except AppError as exc:
            document.status = DocumentStatus.FAILED.value
            document.error_code = exc.code
            document.error_message = exc.message
            await session.commit()
            raise
        except Exception as exc:
            document.status = DocumentStatus.FAILED.value
            document.error_code = "DOCUMENT_PARSE_FAILED"
            document.error_message = "文档解析失败"
            await session.commit()
            raise AppError("DOCUMENT_PARSE_FAILED", "文档解析失败", 422) from exc


async def get_document_or_404(session: AsyncSession, document_id: str) -> DocumentTable:
    document = await session.get(DocumentTable, document_id)
    if document is None:
        raise AppError("DOCUMENT_NOT_FOUND", "文档不存在", 404)
    return document


async def count_chunks(session: AsyncSession, document_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(ChunkCandidateTable).where(
                ChunkCandidateTable.document_id == document_id
            )
        )
        or 0
    )

