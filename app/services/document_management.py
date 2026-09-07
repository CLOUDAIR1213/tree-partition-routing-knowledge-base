from datetime import UTC, datetime

from anyio import to_thread
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.models.schemas import (
    ChangeDocumentPartitionRequest,
    ReopenDocumentReviewRequest,
)
from app.services.hierarchy_builder import HierarchyIndexBuilder
from app.services.ingestion import get_document_or_404


class DocumentManagementService:
    def __init__(self, tree_index_registry, file_storage) -> None:
        self.tree_index_registry = tree_index_registry
        self.file_storage = file_storage
        self.hierarchy_builder = HierarchyIndexBuilder(tree_index_registry)

    async def delete_document(
        self,
        session: AsyncSession,
        document_id: str,
    ) -> int:
        document = await get_document_or_404(session, document_id)
        allowed = {
            DocumentStatus.PENDING_REVIEW.value,
            DocumentStatus.READY.value,
            DocumentStatus.REJECTED.value,
            DocumentStatus.FAILED.value,
        }
        if document.status not in allowed:
            self._invalid_state(document.status)

        chunks = await self._chunks(session, document_id)
        chunk_ids = [chunk.id for chunk in chunks]
        hierarchy_nodes = await self._nodes_for_document(session, document, chunks)
        await self._claim(
            session,
            document_id,
            document.status,
            DocumentStatus.DELETING,
        )

        try:
            await self._clear_indexes(chunk_ids, hierarchy_nodes)
        except Exception as exc:
            await self._mark_failed(
                session,
                document_id,
                DocumentStatus.DELETING,
                "DOCUMENT_DELETE_FAILED",
                "文档索引清理失败，可重试删除",
            )
            raise AppError(
                "DOCUMENT_DELETE_FAILED",
                "文档索引清理失败，未删除元数据和文件",
                500,
            ) from exc

        try:
            await to_thread.run_sync(self.file_storage.remove_document, document_id)
            removed = await session.execute(
                delete(DocumentTable).where(
                    DocumentTable.id == document_id,
                    DocumentTable.status == DocumentStatus.DELETING.value,
                )
            )
            if removed.rowcount != 1:
                raise RuntimeError("document deletion claim was lost")
            await session.commit()
        except Exception as exc:
            await session.rollback()
            await self._mark_failed(
                session,
                document_id,
                DocumentStatus.DELETING,
                "DOCUMENT_DELETE_FAILED",
                "文档文件或元数据清理失败，可重试删除",
            )
            raise AppError(
                "DOCUMENT_DELETE_FAILED",
                "文档未完成全部删除，可重试",
                500,
            ) from exc
        return len(chunks)

    async def change_partition(
        self,
        session: AsyncSession,
        document_id: str,
        request: ChangeDocumentPartitionRequest,
    ) -> tuple[DocumentTable, Partition, int]:
        document = await get_document_or_404(session, document_id)
        if document.status != DocumentStatus.READY.value:
            self._invalid_state(document.status)
        if document.confirmed_partition is None:
            raise AppError(
                "INVALID_DOCUMENT_STATE",
                "ready 文档缺少最终分区",
                409,
                {"status": document.status},
            )
        previous_partition = Partition(document.confirmed_partition)
        if request.confirmed_partition == previous_partition:
            raise AppError(
                "PARTITION_UNCHANGED",
                "新分区与当前分区相同",
                422,
                {"partition": previous_partition.value},
            )

        chunks = await self._chunks(session, document_id)
        if not chunks:
            raise AppError("PREVIEW_NOT_READY", "文档尚未产生可索引 Chunk", 409)
        rows = self._index_rows(document, chunks)
        previous_nodes = await self._nodes_for_document(
            session, document, chunks, previous_partition
        )
        target_nodes = self._tree_nodes(document, chunks, request.confirmed_partition)
        old_review = (
            document.reviewed_by,
            document.review_note,
            document.reviewed_at,
        )
        await self._claim(
            session,
            document_id,
            DocumentStatus.READY.value,
            DocumentStatus.REINDEXING,
        )

        reviewed_at = datetime.now(UTC)
        try:
            await self._make_authoritative(
                request.confirmed_partition,
                rows,
                target_nodes,
            )
            indexed_at = datetime.now(UTC)
            await session.execute(
                update(ChunkCandidateTable)
                .where(ChunkCandidateTable.document_id == document_id)
                .values(indexed_at=indexed_at)
            )
            if target_nodes:
                await self.hierarchy_builder.replace_persisted_nodes(
                    session,
                    document_id,
                    target_nodes,
                    indexed_at=indexed_at,
                )
            updated = await session.execute(
                update(DocumentTable)
                .where(
                    DocumentTable.id == document_id,
                    DocumentTable.status == DocumentStatus.REINDEXING.value,
                )
                .values(
                    confirmed_partition=request.confirmed_partition.value,
                    status=DocumentStatus.READY.value,
                    reviewed_by=request.reviewer_name,
                    review_note=request.note,
                    reviewed_at=reviewed_at,
                    error_code=None,
                    error_message=None,
                )
            )
            if updated.rowcount != 1:
                raise RuntimeError("partition change claim was lost")
            await session.commit()
        except Exception as exc:
            await session.rollback()
            compensation = await self._restore_partition(
                previous_partition,
                rows,
                previous_nodes,
            )
            if compensation:
                await session.execute(
                    update(DocumentTable)
                    .where(DocumentTable.id == document_id)
                    .values(
                        confirmed_partition=previous_partition.value,
                        status=DocumentStatus.READY.value,
                        reviewed_by=old_review[0],
                        review_note=old_review[1],
                        reviewed_at=old_review[2],
                        error_code=None,
                        error_message=None,
                    )
                )
            else:
                await session.execute(
                    update(DocumentTable)
                    .where(DocumentTable.id == document_id)
                    .values(
                        status=DocumentStatus.FAILED.value,
                        error_code="PARTITION_CHANGE_FAILED",
                        error_message="分区调整失败且索引恢复未完成",
                    )
                )
            await session.commit()
            raise AppError(
                "PARTITION_CHANGE_FAILED",
                "更改分区失败",
                500,
                {
                    "compensation": (
                        "compensation_succeeded"
                        if compensation
                        else "compensation_failed"
                    )
                },
            ) from exc

        await session.refresh(document)
        return document, previous_partition, len(chunks)

    async def reopen_review(
        self,
        session: AsyncSession,
        document_id: str,
        request: ReopenDocumentReviewRequest,
    ) -> tuple[DocumentTable, Partition, int]:
        document = await get_document_or_404(session, document_id)
        if document.status != DocumentStatus.READY.value:
            self._invalid_state(document.status)
        if document.confirmed_partition is None:
            raise AppError(
                "INVALID_DOCUMENT_STATE",
                "ready 文档缺少最终分区",
                409,
                {"status": document.status},
            )
        previous_partition = Partition(document.confirmed_partition)
        chunks = await self._chunks(session, document_id)
        if not chunks:
            raise AppError("PREVIEW_NOT_READY", "文档尚未产生可审核 Chunk", 409)
        rows = self._index_rows(document, chunks)
        hierarchy_nodes = await self._nodes_for_document(
            session, document, chunks, previous_partition
        )
        old_review = (
            document.reviewed_by,
            document.review_note,
            document.reviewed_at,
        )
        await self._claim(
            session,
            document_id,
            DocumentStatus.READY.value,
            DocumentStatus.REINDEXING,
        )

        reviewed_at = datetime.now(UTC)
        try:
            await self._clear_indexes([chunk.id for chunk in chunks], hierarchy_nodes)
            await session.execute(
                update(ChunkCandidateTable)
                .where(ChunkCandidateTable.document_id == document_id)
                .values(indexed_at=None)
            )
            if hierarchy_nodes:
                await self.hierarchy_builder.remove_persisted_nodes(session, document_id)
            updated = await session.execute(
                update(DocumentTable)
                .where(
                    DocumentTable.id == document_id,
                    DocumentTable.status == DocumentStatus.REINDEXING.value,
                )
                .values(
                    confirmed_partition=None,
                    status=DocumentStatus.PENDING_REVIEW.value,
                    reviewed_by=request.reviewer_name,
                    review_note=request.note,
                    reviewed_at=reviewed_at,
                    error_code=None,
                    error_message=None,
                )
            )
            if updated.rowcount != 1:
                raise RuntimeError("reopen review claim was lost")
            await session.commit()
        except Exception as exc:
            await session.rollback()
            compensation = await self._restore_partition(
                previous_partition,
                rows,
                hierarchy_nodes,
            )
            if compensation:
                await session.execute(
                    update(DocumentTable)
                    .where(DocumentTable.id == document_id)
                    .values(
                        confirmed_partition=previous_partition.value,
                        status=DocumentStatus.READY.value,
                        reviewed_by=old_review[0],
                        review_note=old_review[1],
                        reviewed_at=old_review[2],
                        error_code=None,
                        error_message=None,
                    )
                )
            else:
                await session.execute(
                    update(DocumentTable)
                    .where(DocumentTable.id == document_id)
                    .values(
                        status=DocumentStatus.FAILED.value,
                        error_code="REOPEN_REVIEW_FAILED",
                        error_message="重新审核失败且索引恢复未完成",
                    )
                )
            await session.commit()
            raise AppError(
                "REOPEN_REVIEW_FAILED",
                "退回重新审核失败",
                500,
                {
                    "compensation": (
                        "compensation_succeeded"
                        if compensation
                        else "compensation_failed"
                    )
                },
            ) from exc

        await session.refresh(document)
        return document, previous_partition, len(chunks)

    async def _claim(
        self,
        session: AsyncSession,
        document_id: str,
        current_status: str,
        next_status: DocumentStatus,
    ) -> None:
        claimed = await session.execute(
            update(DocumentTable)
            .where(
                DocumentTable.id == document_id,
                DocumentTable.status == current_status,
            )
            .values(status=next_status.value)
        )
        if claimed.rowcount != 1:
            await session.rollback()
            raise AppError(
                "INVALID_DOCUMENT_STATE",
                "文档已被其他管理请求处理",
                409,
            )
        await session.commit()

    async def _chunks(
        self,
        session: AsyncSession,
        document_id: str,
    ) -> list[ChunkCandidateTable]:
        return list(
            (
                await session.scalars(
                    select(ChunkCandidateTable)
                    .where(ChunkCandidateTable.document_id == document_id)
                    .order_by(ChunkCandidateTable.chunk_index)
                )
            ).all()
        )

    async def _nodes_for_document(
        self,
        session: AsyncSession,
        document: DocumentTable,
        chunks: list[ChunkCandidateTable],
        partition: Partition | None = None,
    ) -> list:
        resolved_partition = partition or (
            Partition(document.confirmed_partition)
            if document.confirmed_partition is not None
            else None
        )
        if resolved_partition is None:
            return []
        persisted = await self.hierarchy_builder.persisted_nodes_for_document(
            session, document.id
        )
        if persisted and all(node.partition == resolved_partition for node in persisted):
            return persisted
        return self.hierarchy_builder.nodes_for_document(
            document, chunks, resolved_partition
        )

    def _tree_nodes(
        self,
        document: DocumentTable,
        chunks: list[ChunkCandidateTable],
        partition: Partition,
    ) -> list:
        return self.hierarchy_builder.nodes_for_document(document, chunks, partition)

    def _index_rows(
        self,
        document: DocumentTable,
        chunks: list[ChunkCandidateTable],
    ) -> list[dict]:
        partition = Partition(document.confirmed_partition)
        return self.hierarchy_builder.chunk_rows_for_document(
            document, chunks, partition
        )

    async def _make_authoritative(
        self,
        partition: Partition,
        rows: list[dict],
        hierarchy_nodes: list,
    ) -> None:
        partition_rows = [dict(row, partition=partition.value) for row in rows]
        chunk_ids = [row["id"] for row in rows]
        await to_thread.run_sync(
            self.tree_index_registry.upsert_chunks_and_save,
            partition,
            partition_rows,
        )
        verified = await to_thread.run_sync(
            self.tree_index_registry.verify_chunks,
            partition,
            chunk_ids,
        )
        if not verified:
            raise RuntimeError("target chunk index verification failed")
        await self._upsert_hierarchy(hierarchy_nodes)
        for other in Partition:
            if other == partition:
                continue
            await to_thread.run_sync(
                self.tree_index_registry.delete_chunks_and_save,
                other,
                chunk_ids,
            )
            absent = await to_thread.run_sync(
                self.tree_index_registry.verify_chunks_absent,
                other,
                chunk_ids,
            )
            if not absent:
                raise RuntimeError("old chunk index cleanup verification failed")
        await self._clear_hierarchy_from_other_partitions(partition, hierarchy_nodes)

    async def _clear_indexes(self, chunk_ids: list[str], hierarchy_nodes: list) -> None:
        for partition in Partition:
            await to_thread.run_sync(
                self.tree_index_registry.delete_chunks_and_save,
                partition,
                chunk_ids,
            )
            absent = await to_thread.run_sync(
                self.tree_index_registry.verify_chunks_absent,
                partition,
                chunk_ids,
            )
            if not absent:
                raise RuntimeError("chunk index cleanup verification failed")
        await self._clear_hierarchy_from_all_partitions(hierarchy_nodes)

    async def _upsert_hierarchy(self, nodes: list) -> None:
        if not nodes:
            return
        for level, level_nodes in self.hierarchy_builder.by_level(nodes).items():
            partition = level_nodes[0].partition
            node_ids = [node.id for node in level_nodes]
            await to_thread.run_sync(
                self.tree_index_registry.upsert_and_save,
                partition,
                level,
                level_nodes,
            )
            verified = await to_thread.run_sync(
                self.tree_index_registry.verify,
                partition,
                level,
                node_ids,
            )
            if not verified:
                raise RuntimeError("target hierarchy index verification failed")

    async def _clear_hierarchy_from_other_partitions(
        self,
        target: Partition,
        nodes: list,
    ) -> None:
        if not nodes:
            return
        for partition in Partition:
            if partition == target:
                continue
            await self._delete_hierarchy(partition, nodes)

    async def _clear_hierarchy_from_all_partitions(self, nodes: list) -> None:
        for partition in Partition:
            await self._delete_hierarchy(partition, nodes)

    async def _delete_hierarchy(self, partition: Partition, nodes: list) -> None:
        for level, level_nodes in self.hierarchy_builder.by_level(nodes).items():
            node_ids = [node.id for node in level_nodes]
            await to_thread.run_sync(
                self.tree_index_registry.delete_and_save,
                partition,
                level,
                node_ids,
            )
            absent = await to_thread.run_sync(
                self.tree_index_registry.verify_absent,
                partition,
                level,
                node_ids,
            )
            if not absent:
                raise RuntimeError("hierarchy index cleanup verification failed")

    async def _restore_partition(
        self,
        partition: Partition,
        rows: list[dict],
        hierarchy_nodes: list,
    ) -> bool:
        try:
            await self._make_authoritative(partition, rows, hierarchy_nodes)
        except Exception:  # noqa: BLE001
            return False
        return True

    @staticmethod
    async def _mark_failed(
        session: AsyncSession,
        document_id: str,
        current_status: DocumentStatus,
        error_code: str,
        error_message: str,
    ) -> None:
        await session.execute(
            update(DocumentTable)
            .where(
                DocumentTable.id == document_id,
                DocumentTable.status == current_status.value,
            )
            .values(
                status=DocumentStatus.FAILED.value,
                error_code=error_code,
                error_message=error_message,
            )
        )
        await session.commit()

    @staticmethod
    def _invalid_state(current_status: str) -> None:
        raise AppError(
            "INVALID_DOCUMENT_STATE",
            "当前文档状态不允许此操作",
            409,
            {"status": current_status},
        )
