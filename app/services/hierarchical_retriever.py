from __future__ import annotations

import logging

from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import Partition
from app.models.schemas import RetrievalHit
from app.services.hierarchical_index import (
    DOCUMENT_LEVEL,
    SECTION_LEVEL,
    HierarchySearchHit,
    normalize_section,
)
from app.services.retriever import Retriever

logger = logging.getLogger(__name__)


class HierarchicalRetriever(Retriever):
    """Coarse-to-fine retrieval over document, section and existing chunk indexes."""

    def __init__(
        self,
        tree_index_registry,
        min_score: float,
        document_beam_width: int,
        section_beam_width: int,
        leaf_candidate_limit: int,
    ) -> None:
        super().__init__(tree_index_registry, min_score)
        self.tree_index_registry = tree_index_registry
        self.document_beam_width = document_beam_width
        self.section_beam_width = section_beam_width
        self.leaf_candidate_limit = leaf_candidate_limit

    async def search(
        self,
        session: AsyncSession,
        partition: Partition,
        query: str,
        limit: int,
    ) -> list[RetrievalHit]:
        document_hits = await self._search_nodes(
            partition, DOCUMENT_LEVEL, query, self.document_beam_width
        )
        if not document_hits:
            return []

        document_scores = {
            hit.node.document_id: hit.score for hit in document_hits
        }
        selected_document_ids = set(document_scores)
        section_candidates = await self._search_nodes(
            partition,
            SECTION_LEVEL,
            query,
            max(
                self.leaf_candidate_limit,
                self.document_beam_width * self.section_beam_width,
            ),
            document_ids=selected_document_ids,
        )
        selected_sections = self._select_sections(
            section_candidates, selected_document_ids
        )
        if not selected_sections:
            return []

        section_scores = {
            (hit.node.document_id, normalize_section(hit.node.section)): hit.score
            for hit in selected_sections
        }
        leaf_hits = await super().search(
            session,
            partition,
            query,
            self.leaf_candidate_limit,
            section_constraints=set(section_scores),
        )
        if not leaf_hits:
            return []

        rescored = [
            hit.model_copy(
                update={
                    "score": round(
                        hit.score * 0.60
                        + section_scores[(hit.document_id, normalize_section(hit.section))]
                        * 0.25
                        + document_scores[hit.document_id] * 0.15,
                        6,
                    )
                }
            )
            for hit in leaf_hits
        ]
        return sorted(rescored, key=lambda hit: hit.score, reverse=True)[:limit]

    async def _search_nodes(
        self,
        partition: Partition,
        level: str,
        query: str,
        limit: int,
        *,
        document_ids: set[str] | None = None,
    ) -> list[HierarchySearchHit]:
        try:
            raw_hits = await to_thread.run_sync(
                lambda: self.tree_index_registry.search(
                    partition,
                    level,
                    query,
                    limit,
                    document_ids=document_ids,
                )
            )
        except RuntimeError as exc:
            raise AppError(
                "INDEX_NOT_READY",
                f"{partition.value} 分区 {level} 层索引不可用",
                503,
                {"partition": partition.value, "level": level},
            ) from exc
        top_score = max((hit.score for hit in raw_hits), default=None)
        logger.info(
            "tree_retrieval_layer partition=%s level=%s candidate_count=%d "
            "max_score=%s threshold_filtered_count=0",
            partition.value,
            level,
            len(raw_hits),
            None if top_score is None else round(top_score, 6),
        )

        # Parent nodes select a Beam branch only. Their score scale is not
        # interchangeable with Chunk evidence scores, so this threshold does not
        # apply before the leaf search.
        return raw_hits

    def _select_sections(
        self,
        candidates: list[HierarchySearchHit],
        selected_document_ids: set[str],
    ) -> list[HierarchySearchHit]:
        selected: list[HierarchySearchHit] = []
        remaining = {
            document_id: self.section_beam_width
            for document_id in selected_document_ids
        }
        for hit in candidates:
            document_id = hit.node.document_id
            if remaining.get(document_id, 0) <= 0:
                continue
            selected.append(hit)
            remaining[document_id] -= 1
        return selected
