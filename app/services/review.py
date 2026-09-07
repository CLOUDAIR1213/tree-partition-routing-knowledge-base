import logging
from datetime import UTC, datetime
from time import perf_counter

from anyio import to_thread
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, ReviewAction
from app.models.schemas import ReviewRequest
from app.services.hierarchy_builder import HierarchyIndexBuilder
from app.services.ingestion import get_document_or_404

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, tree_index_registry) -> None:
        self.tree_index_registry = tree_index_registry
        self.hierarchy_builder = HierarchyIndexBuilder(tree_index_registry)

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
            return await self._reject(session, document_id, request, reviewed_at, document)

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

        rows = self.hierarchy_builder.chunk_rows_for_document(
            document, chunks, partition
        )
        chunk_ids = [chunk.id for chunk in chunks]
        hierarchy_nodes = self.hierarchy_builder.nodes_for_document(
            document, chunks, partition
        )
        indexing_started_at = perf_counter()
        try:
            await self._run_index_stage(
                document.id,
                partition,
                "chunk",
                "upsert",
                len(rows),
                self.tree_index_registry.upsert_chunks_and_save,
                partition,
                rows,
            )
            verified = await self._run_index_stage(
                document.id,
                partition,
                "chunk",
                "verify",
                len(chunk_ids),
                self.tree_index_registry.verify_chunks,
                partition,
                chunk_ids,
            )
            if not verified:
                raise RuntimeError("chunk index verification failed")
            if hierarchy_nodes:
                await self._upsert_hierarchy(document.id, hierarchy_nodes)

            indexed_at = datetime.now(UTC)
            await session.execute(
                update(ChunkCandidateTable)
                .where(ChunkCandidateTable.document_id == document_id)
                .values(indexed_at=indexed_at)
            )
            if hierarchy_nodes:
                await self.hierarchy_builder.replace_persisted_nodes(
                    session,
                    document_id,
                    hierarchy_nodes,
                    indexed_at=indexed_at,
                )
            document.status = DocumentStatus.READY.value
            document.error_code = None
            document.error_message = None
            await session.commit()
            logger.info(
                "review_index_completed document_id=%s partition=%s chunk_count=%d "
                "hierarchy_node_count=%d elapsed_ms=%d",
                document.id,
                partition.value,
                len(chunk_ids),
                len(hierarchy_nodes),
                round((perf_counter() - indexing_started_at) * 1000),
            )
        except Exception as exc:
            await session.rollback()
            compensation = await self._compensate(partition, chunk_ids, hierarchy_nodes)
            await session.execute(
                update(DocumentTable)
                .where(
                    DocumentTable.id == document_id,
                    DocumentTable.status == DocumentStatus.INDEXING.value,
                )
                .values(
                    status=DocumentStatus.FAILED.value,
                    error_code="INDEX_WRITE_FAILED",
                    error_message=f"索引写入失败；{compensation}",
                )
            )
            await session.commit()
            raise AppError(
                "INDEX_WRITE_FAILED",
                "审核通过后的索引写入失败",
                500,
                {"compensation": compensation},
            ) from exc

        await session.refresh(document)
        return document, len(chunks)

    async def _reject(
        self,
        session: AsyncSession,
        document_id: str,
        request: ReviewRequest,
        reviewed_at: datetime,
        document: DocumentTable,
    ) -> tuple[DocumentTable, int]:
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

    async def _upsert_hierarchy(self, document_id: str, nodes) -> None:
        for level, level_nodes in self.hierarchy_builder.by_level(nodes).items():
            partition = level_nodes[0].partition
            node_ids = [node.id for node in level_nodes]
            await self._run_index_stage(
                document_id,
                partition,
                level,
                "upsert",
                len(level_nodes),
                self.tree_index_registry.upsert_and_save,
                partition,
                level,
                level_nodes,
            )
            verified = await self._run_index_stage(
                document_id,
                partition,
                level,
                "verify",
                len(node_ids),
                self.tree_index_registry.verify,
                partition,
                level,
                node_ids,
            )
            if not verified:
                raise RuntimeError("hierarchy index verification failed")

    @staticmethod
    async def _run_index_stage(
        document_id,
        partition,
        level,
        operation,
        item_count,
        function,
        *args,
    ):
        started_at = perf_counter()
        outcome = "error"
        try:
            result = await to_thread.run_sync(function, *args)
            outcome = "ok"
            return result
        finally:
            logger.info(
                "review_index_stage document_id=%s partition=%s level=%s "
                "operation=%s item_count=%d elapsed_ms=%d outcome=%s",
                document_id,
                partition.value,
                level,
                operation,
                item_count,
                round((perf_counter() - started_at) * 1000),
                outcome,
            )

    async def _compensate(self, partition, chunk_ids, hierarchy_nodes) -> str:
        try:
            if hierarchy_nodes:
                for level, nodes in self.hierarchy_builder.by_level(hierarchy_nodes).items():
                    await to_thread.run_sync(
                        self.tree_index_registry.delete_and_save,
                        partition,
                        level,
                        [node.id for node in nodes],
                    )
                    absent = await to_thread.run_sync(
                        self.tree_index_registry.verify_absent,
                        partition,
                        level,
                        [node.id for node in nodes],
                    )
                    if not absent:
                        raise RuntimeError("hierarchy compensation verification failed")
            await to_thread.run_sync(
                self.tree_index_registry.delete_chunks_and_save, partition, chunk_ids
            )
            absent = await to_thread.run_sync(
                self.tree_index_registry.verify_chunks_absent, partition, chunk_ids
            )
            if not absent:
                raise RuntimeError("chunk compensation verification failed")
        except Exception:  # noqa: BLE001
            return "compensation_failed"
        return "compensation_succeeded"
