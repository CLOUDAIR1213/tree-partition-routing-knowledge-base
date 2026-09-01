from datetime import UTC, datetime

from anyio import to_thread
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, ReviewAction
from app.models.schemas import ReviewRequest
from app.services.ingestion import get_document_or_404


class ReviewService:
    def __init__(self, index_registry) -> None:
        self.index_registry = index_registry

    async def review(
        self,
        session: AsyncSession,
        document_id: str,
        request: ReviewRequest,
    ) -> tuple[DocumentTable, int]:
        document = await get_document_or_404(session, document_id)
        if document.status != DocumentStatus.PENDING_REVIEW.value:
            raise AppError(
                "INVALID_DOCUMENT_STATE",
                "只有 pending_review 文档可以审核",
                409,
                {"status": document.status},
            )
        reviewed_at = datetime.now(UTC)
        if request.action == ReviewAction.REJECT:
            if request.confirmed_partition is not None:
                raise AppError(
                    "VALIDATION_ERROR",
                    "拒绝时 confirmed_partition 必须为 null",
                    422,
                    {"field": "confirmed_partition"},
                )
            claimed = await session.execute(
                update(DocumentTable)
                .where(
                    DocumentTable.id == document_id,
                    DocumentTable.status == DocumentStatus.PENDING_REVIEW.value,
                )
                .values(
                    confirmed_partition=None,
                    status=DocumentStatus.REJECTED.value,
                    reviewed_by=request.reviewer_name,
                    review_note=request.note,
                    reviewed_at=reviewed_at,
                )
            )
            if claimed.rowcount != 1:
                await session.rollback()
                raise AppError(
                    "INVALID_DOCUMENT_STATE", "文档已被其他审核请求处理", 409
                )
            await session.commit()
            await session.refresh(document)
            return document, 0

        if request.confirmed_partition is None:
            raise AppError(
                "REVIEW_PARTITION_REQUIRED", "批准时必须确认最终分区", 422
            )
        partition = request.confirmed_partition
        chunks = list(
            (
                await session.scalars(
                    select(ChunkCandidateTable)
                    .where(ChunkCandidateTable.document_id == document_id)
                    .order_by(ChunkCandidateTable.chunk_index)
                )
            ).all()
        )
        if not chunks:
            raise AppError("PREVIEW_NOT_READY", "文档尚未产生可索引 Chunk", 409)

        claimed = await session.execute(
            update(DocumentTable)
            .where(
                DocumentTable.id == document_id,
                DocumentTable.status == DocumentStatus.PENDING_REVIEW.value,
            )
            .values(
                confirmed_partition=partition.value,
                status=DocumentStatus.INDEXING.value,
                reviewed_by=request.reviewer_name,
                review_note=request.note,
                reviewed_at=reviewed_at,
            )
        )
        if claimed.rowcount != 1:
            await session.rollback()
            raise AppError(
                "INVALID_DOCUMENT_STATE", "文档已被其他审核请求处理", 409
            )
        await session.commit()
        await session.refresh(document)

        rows = [
            {
                "id": chunk.id,
                "text": chunk.embedding_text,
                "document_id": document.id,
                "partition": partition.value,
                "title": chunk.title or document.title or document.original_filename,
                "section": chunk.section_path,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
            }
            for chunk in chunks
        ]
        expected_ids = [chunk.id for chunk in chunks]
        try:
            await to_thread.run_sync(
                self.index_registry.upsert_and_save, partition, rows
            )
            verified = await to_thread.run_sync(
                self.index_registry.verify, partition, expected_ids
            )
            if not verified:
                raise RuntimeError("index verification did not find the sampled chunk")
        except Exception as exc:
            compensation = "compensation_succeeded"
            try:
                await to_thread.run_sync(
                    self.index_registry.delete_and_save, partition, expected_ids
                )
            except Exception:  # noqa: BLE001
                compensation = "compensation_failed"
            document.status = DocumentStatus.FAILED.value
            document.error_code = "INDEX_WRITE_FAILED"
            document.error_message = f"索引写入失败；{compensation}"
            await session.commit()
            raise AppError(
                "INDEX_WRITE_FAILED",
                "审核通过后的索引写入失败",
                500,
                {"compensation": compensation},
            ) from exc

        indexed_at = datetime.now(UTC)
        await session.execute(
            update(ChunkCandidateTable)
            .where(ChunkCandidateTable.document_id == document_id)
            .values(indexed_at=indexed_at)
        )
        document.status = DocumentStatus.READY.value
        document.error_code = None
        document.error_message = None
        await session.commit()
        await session.refresh(document)
        return document, len(chunks)
