import logging
from collections.abc import Collection
from time import perf_counter

from anyio import to_thread
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, PartitionIsolationError
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.models.schemas import (
    PartitionTiming,
    RetrievalGroup,
    RetrievalHit,
    RoutedSubquery,
)
from app.services.hierarchical_index import normalize_section

logger = logging.getLogger(__name__)


class Retriever:
    def __init__(self, tree_index_registry, min_score: float = 0) -> None:
        self.tree_index_registry = tree_index_registry
        self.min_score = min_score

    async def search(
        self,
        session: AsyncSession,
        partition: Partition,
        query: str,
        limit: int,
        *,
        section_constraints: Collection[tuple[str, str]] | None = None,
    ) -> list[RetrievalHit]:
        normalized_constraints = (
            frozenset(section_constraints)
            if section_constraints is not None
            else None
        )
        if normalized_constraints is not None and not normalized_constraints:
            return []
        try:
            raw_hits = await to_thread.run_sync(
                lambda: self.tree_index_registry.search_chunks(
                    partition,
                    query,
                    limit,
                    section_constraints=normalized_constraints,
                )
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
        threshold_filtered_count = sum(
            score < self.min_score for _chunk_id, score in ordered
        )
        top_score = max((score for _chunk_id, score in ordered), default=None)
        if not ordered:
            logger.info(
                "tree_retrieval_layer partition=%s level=chunk candidate_count=0 "
                "max_score=None threshold_filtered_count=0 sqlite_rejected_count=0 "
                "accepted_count=0",
                partition.value,
            )
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
        sqlite_rejected_count = 0
        for chunk_id, score in ordered:
            if score < self.min_score:
                continue
            record = by_id.get(chunk_id)
            if record is None:
                sqlite_rejected_count += 1
                continue
            chunk, document = record
            if document.status != DocumentStatus.READY.value:
                sqlite_rejected_count += 1
                continue
            if document.confirmed_partition != partition.value:
                raise PartitionIsolationError(partition.value)
            if normalized_constraints is not None and (
                document.id,
                normalize_section(chunk.section_path),
            ) not in normalized_constraints:
                sqlite_rejected_count += 1
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
        logger.info(
            "tree_retrieval_layer partition=%s level=chunk candidate_count=%d "
            "max_score=%s threshold_filtered_count=%d sqlite_rejected_count=%d "
            "accepted_count=%d",
            partition.value,
            len(ordered),
            None if top_score is None else round(top_score, 6),
            threshold_filtered_count,
            sqlite_rejected_count,
            len(results),
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

    async def search_groups_with_timings(
        self,
        session: AsyncSession,
        subqueries: list[RoutedSubquery],
        limit: int,
    ) -> tuple[list[RetrievalGroup], list[PartitionTiming]]:
        groups: list[RetrievalGroup] = []
        timings: list[PartitionTiming] = []
        for subquery in subqueries:
            started_at = perf_counter()
            hits = await self.search(
                session,
                subquery.partition,
                subquery.query,
                limit,
            )
            timings.append(
                PartitionTiming(
                    partition=subquery.partition,
                    elapsed_ms=round((perf_counter() - started_at) * 1000),
                )
            )
            groups.append(
                RetrievalGroup(
                    partition=subquery.partition,
                    query=subquery.query,
                    hits=hits,
                )
            )
        return groups, timings

    @staticmethod
    def _normalize_hit(hit: object) -> tuple[str, float] | None:
        if isinstance(hit, dict) and hit.get("id") is not None:
            return str(hit["id"]), float(hit.get("score", 0.0))
        if isinstance(hit, (tuple, list)) and len(hit) >= 2:
            return str(hit[0]), float(hit[1])
        return None
