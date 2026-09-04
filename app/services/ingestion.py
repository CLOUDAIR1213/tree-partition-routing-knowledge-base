import secrets
from pathlib import Path

from anyio import to_thread
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.models.schemas import ParseQualityReport
from app.services.chunker import SectionChunker
from app.services.file_storage import FileStorage
from app.services.parser import ParseResult, StandardDocumentParser
from app.services.partition_suggestion import KeywordPartitionSuggester


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
        self.partition_suggester = KeywordPartitionSuggester()

    async def ingest(
        self,
        session: AsyncSession,
        *,
        original_filename: str,
        content: bytes,
        partition: Partition,
        custom_title: str | None,
    ) -> tuple[DocumentTable, ParseQualityReport]:
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
            parse_result = await to_thread.run_sync(
                self.parser.parse_with_diagnostics,
                Path(document.stored_path),
                document.mime_type,
            )
            sections = parse_result.sections
            # A document's display identity must not depend on a repeated first section heading.
            title = custom_title or Path(document.original_filename).stem
            chunks = await to_thread.run_sync(
                self.chunker.chunk, document.id, title, sections
            )
            if not chunks:
                raise AppError("EMPTY_DOCUMENT", "文件没有可索引的正文", 422)
            parse_quality = self._build_parse_quality(parse_result, chunks, title)
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
                    "parse_quality": parse_quality.model_dump(mode="json"),
                },
            )
            return document, parse_quality
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

    def _build_parse_quality(self, result: ParseResult, chunks, title: str) -> ParseQualityReport:
        section_count = len(result.sections)
        titled_section_count = sum(1 for section in result.sections if section.title)
        token_counts = [self.chunker.token_count(chunk.text) for chunk in chunks]
        min_tokens = min(token_counts, default=0)
        max_tokens = max(token_counts, default=0)
        average_tokens = round(sum(token_counts) / len(token_counts), 1) if token_counts else 0
        short_chunk_count = sum(
            count < self.chunker.min_tokens for count in token_counts
        )
        near_limit_chunk_count = sum(
            count >= self.chunker.max_tokens * 0.9 for count in token_counts
        )
        over_limit_chunk_count = sum(
            count > self.chunker.max_tokens for count in token_counts
        )
        content_for_suggestion = "\n".join(
            [title, *[section.section_path or "" for section in result.sections], *[section.text for section in result.sections]]
        )
        suggestion = self.partition_suggester.suggest(content_for_suggestion)
        warnings: list[str] = []
        if section_count == 1:
            warnings.append("仅识别到 1 个章节，引用定位可能不够精确。")
        if section_count and titled_section_count / section_count < 0.5:
            warnings.append("标题识别率低，建议使用 DOCX Heading 或 Markdown 标题。")
        if result.diagnostics.blank_page_numbers:
            pages = "、".join(str(page) for page in result.diagnostics.blank_page_numbers)
            warnings.append(f"第 {pages} 页未提取到正文，扫描页可能需要 OCR。")
        if result.diagnostics.table_count:
            warnings.append(
                f"识别到 {result.diagnostics.table_count} 个表格，已按原文顺序扁平化为文本。"
            )
        if short_chunk_count:
            warnings.append(
                f"有 {short_chunk_count} 个 Chunk 少于最小长度 {self.chunker.min_tokens}。"
            )
        if near_limit_chunk_count:
            warnings.append(
                f"有 {near_limit_chunk_count} 个 Chunk 接近最大长度 {self.chunker.max_tokens}。"
            )
        if over_limit_chunk_count:
            warnings.append("存在超过最大长度的 Chunk，建议检查分段规则。")
        if suggestion.partition is None:
            warnings.append("未形成唯一的内容分区建议，请人工确认最终分区。")
        elif suggestion.confidence < 0.6:
            warnings.append("内容分区建议置信度较低，请人工确认最终分区。")
        return ParseQualityReport(
            source_format=result.diagnostics.source_format,
            section_count=section_count,
            titled_section_count=titled_section_count,
            heading_recognition_rate=round(
                titled_section_count / section_count, 2
            )
            if section_count
            else 0,
            page_count=result.diagnostics.page_count,
            blank_page_numbers=result.diagnostics.blank_page_numbers,
            table_count=result.diagnostics.table_count,
            chunk_count=len(chunks),
            min_chunk_tokens=min_tokens,
            max_chunk_tokens=max_tokens,
            average_chunk_tokens=average_tokens,
            short_chunk_count=short_chunk_count,
            near_limit_chunk_count=near_limit_chunk_count,
            over_limit_chunk_count=over_limit_chunk_count,
            partition_suggestion=suggestion,
            warnings=warnings,
        )


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
