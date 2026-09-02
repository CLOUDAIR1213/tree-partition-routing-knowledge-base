from anyio import to_thread
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, PartitionIsolationError
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.models.schemas import RetrievalGroup, RetrievalHit, RoutedSubquery


class Retriever:
    def __init__(self, index_registry, min_score: float = 0) -> None:
        self.index_registry = index_registry
        self.min_score = min_score

    async def search(
        self,
        session: AsyncSession,
        partition: Partition,
        query: str,
        limit: int,
    ) -> list[RetrievalHit]:
        try:
            raw_hits = await to_thread.run_sync(
                lambda: self.index_registry.search(partition, query, limit)
            )
        except RuntimeError as exc:
            raise AppError(
                "INDEX_NOT_READY",
                f"{partition.value} 分区索引不可用",
                503,
                {"partition": partition.value},
            ) from exc

        ordered = [self._normalize_hit(hit) for hit in raw_hits]
        ordered = [hit for hit in ordered if hit is not None]
        if not ordered:
            return []

        chunk_ids = [chunk_id for chunk_id, _score in ordered]
        records = (
            await session.execute(
                select(ChunkCandidateTable, DocumentTable)
                .join(DocumentTable, DocumentTable.id == ChunkCandidateTable.document_id)
                .where(ChunkCandidateTable.id.in_(chunk_ids))
            )
        ).all()
        by_id = {chunk.id: (chunk, document) for chunk, document in records}

        results: list[RetrievalHit] = []
        for chunk_id, score in ordered:
            if score < self.min_score:
                continue
            record = by_id.get(chunk_id)
            if record is None:
                continue
            chunk, document = record
            if (
                document.confirmed_partition is not None
                and document.confirmed_partition != partition.value
            ):
                raise PartitionIsolationError(partition.value)
            if (
                document.status != DocumentStatus.READY.value
                or document.confirmed_partition != partition.value
            ):
                continue
            results.append(
                RetrievalHit(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    partition=partition,
                    text=chunk.text,
                    score=score,
                    title=chunk.title or document.title or document.original_filename,
                    section=chunk.section_path,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                )
            )
        return results

    async def search_groups(
        self,
        session: AsyncSession,
        subqueries: list[RoutedSubquery],
        limit: int,
    ) -> list[RetrievalGroup]:
        groups: list[RetrievalGroup] = []
        for subquery in subqueries:
            hits = await self.search(
                session,
                subquery.partition,
                subquery.query,
                limit,
            )
            groups.append(
                RetrievalGroup(
                    partition=subquery.partition,
                    query=subquery.query,
                    hits=hits,
                )
            )
        return groups

    @staticmethod
    def _normalize_hit(hit: object) -> tuple[str, float] | None:
        if isinstance(hit, dict) and hit.get("id") is not None:
            return str(hit["id"]), float(hit.get("score", 0.0))
        if isinstance(hit, (tuple, list)) and len(hit) >= 2:
            return str(hit[0]), float(hit[1])
        return None
