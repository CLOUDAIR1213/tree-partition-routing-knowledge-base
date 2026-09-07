from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock

from app.models.enums import Partition

DOCUMENT_LEVEL = "document"
SECTION_LEVEL = "section"
CHUNK_LEVEL = "chunk"
LEVELS = (DOCUMENT_LEVEL, SECTION_LEVEL, CHUNK_LEVEL)


def normalize_section(section: str | None) -> str:
    return section or "(未分节)"


@dataclass(frozen=True)
class HierarchyNode:
    id: str
    level: str
    partition: Partition
    document_id: str
    section: str | None
    text: str


@dataclass(frozen=True)
class HierarchySearchHit:
    node: HierarchyNode
    score: float


def document_node_id(document_id: str) -> str:
    return f"hdoc:{document_id}"


def section_node_id(document_id: str, section: str) -> str:
    digest = sha256(section.encode("utf-8")).hexdigest()[:16]
    return f"hsec:{document_id}:{digest}"


class HierarchicalIndexRegistry:
    """Partitioned txtai indexes for document, section and chunk tree levels."""

    def __init__(self, root: Path, embedding_model: str) -> None:
        from txtai import Embeddings

        self.root = root
        self.embedding_model = embedding_model
        self._embeddings_type = Embeddings
        self._indexes: dict[tuple[Partition, str], object] = {}
        self._locks = {
            (partition, level): RLock()
            for partition in Partition
            for level in LEVELS
        }
        self._populated = {
            (partition, level): False
            for partition in Partition
            for level in LEVELS
        }
        self._nodes: dict[str, HierarchyNode] = {}
        self._errors: dict[tuple[Partition, str], Exception] = {}

    def load_all(self) -> None:
        for partition in Partition:
            for level in LEVELS:
                key = (partition, level)
                path = self.root / partition.value / level
                path.mkdir(parents=True, exist_ok=True)
                try:
                    index = self._embeddings_type(
                        {"path": self.embedding_model, "content": True}
                    )
                    persisted = any(item.name != ".gitkeep" for item in path.iterdir())
                    if persisted:
                        index.load(str(path))
                    self._indexes[key] = index
                    self._populated[key] = persisted
                    self._errors.pop(key, None)
                except Exception as exc:  # noqa: BLE001
                    self._indexes.pop(key, None)
                    self._populated[key] = False
                    self._errors[key] = exc

    def ensure_all_ready(self) -> None:
        """Fail startup with the original loading context before any index writes."""
        if not self._errors:
            return

        failures = sorted(
            self._errors.items(),
            key=lambda item: (item[0][0].value, item[0][1]),
        )
        summary = ", ".join(
            f"{partition.value}/{level} ({type(error).__name__})"
            for (partition, level), error in failures
        )
        raise RuntimeError(f"hierarchical index initialization failed: {summary}") from (
            failures[0][1]
        )

    def get(self, partition: Partition, level: str):
        key = self._key(partition, level)
        if key not in self._indexes:
            raise RuntimeError(
                f"hierarchical index is not ready: {partition.value}/{level}"
            )
        return self._indexes[key]

    def upsert_and_save(
        self,
        partition: Partition,
        level: str,
        nodes: list[HierarchyNode],
    ) -> None:
        if not nodes:
            return
        key = self._key(partition, level)
        with self._locks[key]:
            index = self.get(partition, level)
            documents = [
                (
                    node.id,
                    {
                        "text": node.text,
                        "document_id": node.document_id,
                        "section": node.section,
                        "level": node.level,
                    },
                    None,
                )
                for node in nodes
            ]
            if self._populated[key]:
                index.upsert(documents)
            else:
                index.index(documents)
                self._populated[key] = True
            index.save(str(self.root / partition.value / level))
            self._nodes.update({node.id: node for node in nodes})

    def upsert_chunks_and_save(
        self,
        partition: Partition,
        rows: list[dict],
    ) -> None:
        if not rows:
            return
        key = self._key(partition, CHUNK_LEVEL)
        with self._locks[key]:
            index = self.get(partition, CHUNK_LEVEL)
            documents = [
                (
                    row["id"],
                    {key: value for key, value in row.items() if key != "id"},
                    None,
                )
                for row in rows
            ]
            if self._populated[key]:
                index.upsert(documents)
            else:
                index.index(documents)
                self._populated[key] = True
            index.save(str(self.root / partition.value / CHUNK_LEVEL))

    def delete_and_save(
        self,
        partition: Partition,
        level: str,
        node_ids: list[str],
    ) -> None:
        if not node_ids:
            return
        key = self._key(partition, level)
        with self._locks[key]:
            index = self.get(partition, level)
            if not self._populated[key]:
                return
            index.delete(node_ids)
            index.save(str(self.root / partition.value / level))
            for node_id in node_ids:
                node = self._nodes.get(node_id)
                if node is not None and node.partition == partition:
                    self._nodes.pop(node_id, None)

    def delete_chunks_and_save(
        self,
        partition: Partition,
        chunk_ids: list[str],
    ) -> None:
        if not chunk_ids:
            return
        key = self._key(partition, CHUNK_LEVEL)
        with self._locks[key]:
            index = self.get(partition, CHUNK_LEVEL)
            if not self._populated[key]:
                return
            index.delete(chunk_ids)
            index.save(str(self.root / partition.value / CHUNK_LEVEL))

    def verify(
        self,
        partition: Partition,
        level: str,
        node_ids: list[str],
    ) -> bool:
        if not node_ids:
            return True
        key = self._key(partition, level)
        with self._locks[key]:
            index = self.get(partition, level)
            return all(self._contains(index, node_id) for node_id in node_ids)

    def verify_absent(
        self,
        partition: Partition,
        level: str,
        node_ids: list[str],
    ) -> bool:
        if not node_ids:
            return True
        key = self._key(partition, level)
        with self._locks[key]:
            index = self.get(partition, level)
            if not self._populated[key]:
                return True
            return not any(self._contains(index, node_id) for node_id in node_ids)

    def verify_chunks(self, partition: Partition, chunk_ids: list[str]) -> bool:
        return self.verify(partition, CHUNK_LEVEL, chunk_ids)

    def verify_chunks_absent(
        self,
        partition: Partition,
        chunk_ids: list[str],
    ) -> bool:
        return self.verify_absent(partition, CHUNK_LEVEL, chunk_ids)

    def load_nodes(self, nodes: list[HierarchyNode]) -> None:
        self._nodes = {node.id: node for node in nodes}

    def search(
        self,
        partition: Partition,
        level: str,
        query: str,
        limit: int,
        *,
        document_ids: Collection[str] | None = None,
    ) -> list[HierarchySearchHit]:
        key = self._key(partition, level)
        normalized_document_ids = (
            frozenset(document_ids) if document_ids is not None else None
        )
        if normalized_document_ids is not None and not normalized_document_ids:
            return []
        with self._locks[key]:
            index = self.get(partition, level)
            if not self._populated[key]:
                return []
            if normalized_document_ids is None:
                raw_hits = index.search(query, limit)
            else:
                population = index.count()
                if population <= 0:
                    return []
                statement, parameters = self._document_constraint_query(
                    query,
                    limit,
                    population,
                    normalized_document_ids,
                )
                raw_hits = index.search(statement, limit=limit, parameters=parameters)

        results: list[HierarchySearchHit] = []
        for hit in raw_hits:
            node_id, score = self._normalize_hit(hit)
            node = self._nodes.get(node_id)
            if (
                node is not None
                and node.partition == partition
                and node.level == level
                and (
                    normalized_document_ids is None
                    or node.document_id in normalized_document_ids
                )
            ):
                results.append(HierarchySearchHit(node=node, score=score))
        return results

    def search_chunks(
        self,
        partition: Partition,
        query: str,
        limit: int,
        *,
        section_constraints: Collection[tuple[str, str]] | None = None,
    ) -> list[dict]:
        key = self._key(partition, CHUNK_LEVEL)
        normalized_constraints = (
            frozenset(section_constraints)
            if section_constraints is not None
            else None
        )
        if normalized_constraints is not None and not normalized_constraints:
            return []

        with self._locks[key]:
            index = self.get(partition, CHUNK_LEVEL)
            if not self._populated[key]:
                return []
            if normalized_constraints is None:
                return index.search(query, limit)
            population = index.count()
            if population <= 0:
                return []
            statement, parameters = self._section_constraint_query(
                query,
                limit,
                population,
                normalized_constraints,
            )
            return index.search(statement, limit=limit, parameters=parameters)

    @staticmethod
    def _document_constraint_query(
        query: str,
        limit: int,
        population: int,
        document_ids: Collection[str],
    ) -> tuple[str, dict[str, object]]:
        parameters: dict[str, object] = {
            "query": query,
            "candidates": population,
            "limit": limit,
        }
        placeholders: list[str] = []
        for position, document_id in enumerate(sorted(set(document_ids))):
            key = f"document_id_{position}"
            parameters[key] = document_id
            placeholders.append(f":{key}")

        return (
            (
                "select id, score from txtai "
                "where similar(:query, :candidates) "
                f"and document_id in ({', '.join(placeholders)}) limit :limit"
            ),
            parameters,
        )

    @staticmethod
    def _section_constraint_query(
        query: str,
        limit: int,
        population: int,
        section_constraints: Collection[tuple[str, str]],
    ) -> tuple[str, dict[str, object]]:
        parameters: dict[str, object] = {
            "query": query,
            "candidates": population,
            "limit": limit,
        }
        clauses: list[str] = []
        for position, (document_id, section) in enumerate(
            sorted(set(section_constraints))
        ):
            document_key = f"document_id_{position}"
            section_key = f"section_{position}"
            parameters[document_key] = document_id
            parameters[section_key] = section
            section_match = f"section = :{section_key}"
            if section == normalize_section(None):
                section_match = f"({section_match} or section is null)"
            clauses.append(
                f"(document_id = :{document_key} and {section_match})"
            )

        return (
            (
                "select id, score from txtai "
                "where similar(:query, :candidates) "
                f"and ({' or '.join(clauses)}) limit :limit"
            ),
            parameters,
        )

    def health(self) -> dict[str, dict[str, str]]:
        return {
            partition.value: {
                level: "ready" if (partition, level) in self._indexes else "error"
                for level in LEVELS
            }
            for partition in Partition
        }

    def close_all(self) -> None:
        self._indexes.clear()
        self._nodes.clear()
        self._errors.clear()

    @staticmethod
    def _normalize_hit(hit: object) -> tuple[str, float]:
        if isinstance(hit, dict) and hit.get("id") is not None:
            return str(hit["id"]), float(hit.get("score", 0.0))
        if isinstance(hit, (tuple, list)) and len(hit) >= 2:
            return str(hit[0]), float(hit[1])
        raise ValueError("hierarchical index returned an invalid hit")

    @staticmethod
    def _contains(index, node_id: str) -> bool:
        wanted = node_id.replace("'", "''")
        rows = index.search(f"select id from txtai where id = '{wanted}'")
        return any(str(row.get("id")) == node_id for row in rows)

    @staticmethod
    def _key(partition: Partition, level: str) -> tuple[Partition, str]:
        if not isinstance(partition, Partition):
            raise TypeError("partition must be a Partition enum")
        if level not in LEVELS:
            raise ValueError(f"unknown hierarchy level: {level}")
        return partition, level
