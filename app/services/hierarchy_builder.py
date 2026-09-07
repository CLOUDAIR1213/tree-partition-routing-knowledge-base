from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256

from anyio import to_thread
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import ChunkCandidateTable, DocumentTable, HierarchyNodeTable
from app.models.enums import DocumentStatus, Partition
from app.services.hierarchical_index import (
    DOCUMENT_LEVEL,
    SECTION_LEVEL,
    HierarchyNode,
    document_node_id,
    normalize_section,
    section_node_id,
)


class HierarchyIndexBuilder:
    """Derives deterministic routing nodes and keeps their SQLite records aligned."""

    def __init__(self, registry=None, *, max_node_characters: int = 2400) -> None:
        self.registry = registry
        self.max_node_characters = max_node_characters

    def nodes_for_document(
        self,
        document: DocumentTable,
        chunks: list[ChunkCandidateTable],
        partition: Partition,
    ) -> list[HierarchyNode]:
        title = document.title or document.original_filename
        sections: dict[str, list[ChunkCandidateTable]] = defaultdict(list)
        for chunk in chunks:
            sections[normalize_section(chunk.section_path)].append(chunk)

        section_names = "\n".join(f"- {section}" for section in sections)
        document_text = self._truncate(
            f"文档标题：{title}\n章节：\n{section_names}\n内容摘要：\n"
            + "\n".join(chunk.embedding_text for chunk in chunks)
        )
        document_id = document_node_id(document.id)
        nodes = [
            HierarchyNode(
                id=document_id,
                level=DOCUMENT_LEVEL,
                partition=partition,
                document_id=document.id,
                section=None,
                text=document_text,
            )
        ]
        for section, section_chunks in sections.items():
            section_text = self._truncate(
                f"文档标题：{title}\n章节：{section}\n内容：\n"
                + "\n".join(chunk.embedding_text for chunk in section_chunks)
            )
            nodes.append(
                HierarchyNode(
                    id=section_node_id(document.id, section),
                    level=SECTION_LEVEL,
                    partition=partition,
                    document_id=document.id,
                    section=section,
                    text=section_text,
                )
            )
        return nodes

    @staticmethod
    def chunk_rows_for_document(
        document: DocumentTable,
        chunks: list[ChunkCandidateTable],
        partition: Partition,
    ) -> list[dict]:
        return [
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

    async def replace_persisted_nodes(
        self,
        session: AsyncSession,
        document_id: str,
        nodes: list[HierarchyNode],
        *,
        indexed_at: datetime | None,
    ) -> None:
        await session.execute(
            delete(HierarchyNodeTable).where(HierarchyNodeTable.document_id == document_id)
        )
        session.add_all(
            [
                HierarchyNodeTable(
                    id=node.id,
                    parent_id=(
                        None
                        if node.level == DOCUMENT_LEVEL
                        else document_node_id(node.document_id)
                    ),
                    level=node.level,
                    partition=node.partition.value,
                    document_id=node.document_id,
                    section_path=node.section,
                    retrieval_text=node.text,
                    checksum_sha256=self.node_checksum(node),
                    indexed_at=indexed_at,
                )
                for node in nodes
            ]
        )

    async def remove_persisted_nodes(
        self,
        session: AsyncSession,
        document_id: str,
    ) -> None:
        await session.execute(
            delete(HierarchyNodeTable).where(HierarchyNodeTable.document_id == document_id)
        )

    async def persisted_nodes_for_document(
        self,
        session: AsyncSession,
        document_id: str,
    ) -> list[HierarchyNode]:
        rows = list(
            (
                await session.scalars(
                    select(HierarchyNodeTable)
                    .where(HierarchyNodeTable.document_id == document_id)
                    .order_by(HierarchyNodeTable.level, HierarchyNodeTable.id)
                )
            ).all()
        )
        return [self.node_from_record(row) for row in rows]

    async def sync_ready_documents(self, session: AsyncSession) -> None:
        if self.registry is None:
            return
        all_documents = list((await session.scalars(select(DocumentTable))).all())
        all_chunks = list(
            (
                await session.scalars(
                    select(ChunkCandidateTable).order_by(
                        ChunkCandidateTable.document_id,
                        ChunkCandidateTable.chunk_index,
                    )
                )
            ).all()
        )
        chunks_by_document: dict[str, list[ChunkCandidateTable]] = defaultdict(list)
        for chunk in all_chunks:
            chunks_by_document[chunk.document_id].append(chunk)

        documents: dict[str, tuple[DocumentTable, list[ChunkCandidateTable]]] = {}
        for document in all_documents:
            if document.status != DocumentStatus.READY.value:
                continue
            if document.confirmed_partition is None:
                raise RuntimeError(
                    f"ready document is missing confirmed partition: {document.id}"
                )
            chunks = chunks_by_document.get(document.id, [])
            if not chunks:
                raise RuntimeError(f"ready document has no chunks: {document.id}")
            documents[document.id] = (document, chunks)

        existing = list((await session.scalars(select(HierarchyNodeTable))).all())
        expected_by_document = {
            document_id: self.nodes_for_document(
                document,
                chunks,
                Partition(document.confirmed_partition),
            )
            for document_id, (document, chunks) in documents.items()
        }
        expected = [node for nodes in expected_by_document.values() for node in nodes]
        expected_by_id = {node.id: node for node in expected}
        stale = [
            self.node_from_record(row)
            for row in existing
            if (
                (node := expected_by_id.get(row.id)) is None
                or node.partition.value != row.partition
                or node.level != row.level
            )
        ]

        for nodes in expected_by_document.values():
            await self._upsert_and_verify(nodes)
        for document_id, (document, chunks) in documents.items():
            partition = Partition(document.confirmed_partition)
            rows = self.chunk_rows_for_document(document, chunks, partition)
            chunk_ids = [row["id"] for row in rows]
            await to_thread.run_sync(
                self.registry.upsert_chunks_and_save,
                partition,
                rows,
            )
            verified = await to_thread.run_sync(
                self.registry.verify_chunks,
                partition,
                chunk_ids,
            )
            if not verified:
                raise RuntimeError(
                    f"tree chunk verification failed during startup sync: {document_id}"
                )
            await self._delete_chunks_from_partitions(
                chunk_ids,
                [candidate for candidate in Partition if candidate != partition],
            )

        non_ready_chunk_ids = [
            chunk.id
            for document in all_documents
            if document.id not in documents
            for chunk in chunks_by_document.get(document.id, [])
        ]
        await self._delete_chunks_from_partitions(non_ready_chunk_ids, list(Partition))
        await self._delete_and_verify(stale)

        indexed_at = datetime.now(UTC)
        for document_id, nodes in expected_by_document.items():
            await self.replace_persisted_nodes(
                session,
                document_id,
                nodes,
                indexed_at=indexed_at,
            )
        stale_document_ids = {
            row.document_id
            for row in existing
            if row.document_id not in expected_by_document
        }
        for document_id in stale_document_ids:
            await self.remove_persisted_nodes(session, document_id)
        await session.commit()
        self.registry.load_nodes(expected)

    async def _delete_chunks_from_partitions(
        self,
        chunk_ids: list[str],
        partitions: list[Partition],
    ) -> None:
        if not chunk_ids:
            return
        for partition in partitions:
            await to_thread.run_sync(
                self.registry.delete_chunks_and_save,
                partition,
                chunk_ids,
            )
            absent = await to_thread.run_sync(
                self.registry.verify_chunks_absent,
                partition,
                chunk_ids,
            )
            if not absent:
                raise RuntimeError(
                    "tree chunk cross-partition cleanup verification failed"
                )

    async def _upsert_and_verify(self, nodes: list[HierarchyNode]) -> None:
        for level, level_nodes in self.by_level(nodes).items():
            partition = level_nodes[0].partition
            await to_thread.run_sync(
                self.registry.upsert_and_save,
                partition,
                level,
                level_nodes,
            )
            verified = await to_thread.run_sync(
                self.registry.verify,
                partition,
                level,
                [node.id for node in level_nodes],
            )
            if not verified:
                raise RuntimeError("hierarchy index verification failed during startup sync")

    async def _delete_and_verify(self, nodes: list[HierarchyNode]) -> None:
        for (partition, level), level_nodes in self.by_partition_and_level(nodes).items():
            node_ids = [node.id for node in level_nodes]
            await to_thread.run_sync(
                self.registry.delete_and_save,
                partition,
                level,
                node_ids,
            )
            absent = await to_thread.run_sync(
                self.registry.verify_absent,
                partition,
                level,
                node_ids,
            )
            if not absent:
                raise RuntimeError("hierarchy stale-node cleanup verification failed")

    @staticmethod
    def by_level(nodes: list[HierarchyNode]) -> dict[str, list[HierarchyNode]]:
        grouped: dict[str, list[HierarchyNode]] = defaultdict(list)
        for node in nodes:
            grouped[node.level].append(node)
        return dict(grouped)

    @staticmethod
    def by_partition_and_level(
        nodes: list[HierarchyNode],
    ) -> dict[tuple[Partition, str], list[HierarchyNode]]:
        grouped: dict[tuple[Partition, str], list[HierarchyNode]] = defaultdict(list)
        for node in nodes:
            grouped[(node.partition, node.level)].append(node)
        return dict(grouped)

    @staticmethod
    def node_checksum(node: HierarchyNode) -> str:
        payload = "\n".join(
            (
                node.id,
                node.level,
                node.partition.value,
                node.document_id,
                node.section or "",
                node.text,
            )
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def node_from_record(record: HierarchyNodeTable) -> HierarchyNode:
        return HierarchyNode(
            id=record.id,
            level=record.level,
            partition=Partition(record.partition),
            document_id=record.document_id,
            section=record.section_path,
            text=record.retrieval_text,
        )

    def _truncate(self, text: str) -> str:
        return text[: self.max_node_characters]
