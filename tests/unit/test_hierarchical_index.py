from threading import RLock

import pytest

from app.models.enums import Partition
from app.services.hierarchical_index import (
    CHUNK_LEVEL,
    DOCUMENT_LEVEL,
    LEVELS,
    SECTION_LEVEL,
    HierarchicalIndexRegistry,
    HierarchyNode,
)


class RecordingEmbeddings:
    def __init__(self, rows: list[dict], population: int) -> None:
        self.rows = rows
        self.population = population
        self.calls: list[tuple[str, int | None, dict[str, object] | None]] = []

    def count(self) -> int:
        return self.population

    def search(
        self,
        query: str,
        limit: int | None = None,
        parameters: dict[str, object] | None = None,
    ) -> list[dict]:
        self.calls.append((query, limit, parameters))
        return self.rows


def make_registry(level: str, index: RecordingEmbeddings) -> HierarchicalIndexRegistry:
    registry = object.__new__(HierarchicalIndexRegistry)
    registry._indexes = {(Partition.TECH, level): index}
    registry._locks = {
        (partition, candidate_level): RLock()
        for partition in Partition
        for candidate_level in LEVELS
    }
    registry._populated = {
        (partition, candidate_level): (
            partition == Partition.TECH and candidate_level == level
        )
        for partition in Partition
        for candidate_level in LEVELS
    }
    registry._nodes = {}
    registry._errors = {}
    return registry


def test_chunk_search_uses_bound_exact_document_section_pairs():
    index = RecordingEmbeddings([{"id": "chunk-1", "score": 0.9}], population=23)
    registry = make_registry(CHUNK_LEVEL, index)

    rows = registry.search_chunks(
        Partition.TECH,
        "查找目标",
        4,
        section_constraints={
            ("document-a", "第一章"),
            ("document-b", "(未分节)"),
        },
    )

    assert rows == [{"id": "chunk-1", "score": 0.9}]
    statement, limit, parameters = index.calls[0]
    assert "similar(:query, :candidates)" in statement
    assert "document_id = :document_id_0 and section = :section_0" in statement
    assert "document_id = :document_id_1" in statement
    assert "section is null" in statement
    assert "document_id in" not in statement
    assert limit == 4
    assert parameters == {
        "query": "查找目标",
        "candidates": 23,
        "limit": 4,
        "document_id_0": "document-a",
        "section_0": "第一章",
        "document_id_1": "document-b",
        "section_1": "(未分节)",
    }


def test_section_search_uses_bound_selected_document_metadata():
    node = HierarchyNode(
        id="hsec:document-b:example",
        level=SECTION_LEVEL,
        partition=Partition.TECH,
        document_id="document-b",
        section="第一章",
        text="目标章节",
    )
    index = RecordingEmbeddings([{"id": node.id, "score": 0.8}], population=7)
    registry = make_registry(SECTION_LEVEL, index)
    registry._nodes = {node.id: node}

    hits = registry.search(
        Partition.TECH,
        SECTION_LEVEL,
        "查找目标",
        3,
        document_ids={"document-a", "document-b"},
    )

    assert [hit.node.id for hit in hits] == [node.id]
    statement, limit, parameters = index.calls[0]
    assert "similar(:query, :candidates)" in statement
    assert "document_id in (:document_id_0, :document_id_1)" in statement
    assert limit == 3
    assert parameters == {
        "query": "查找目标",
        "candidates": 7,
        "limit": 3,
        "document_id_0": "document-a",
        "document_id_1": "document-b",
    }


def test_empty_metadata_scopes_skip_index_queries():
    chunk_index = RecordingEmbeddings([], population=10)
    chunk_registry = make_registry(CHUNK_LEVEL, chunk_index)
    section_index = RecordingEmbeddings([], population=10)
    section_registry = make_registry(SECTION_LEVEL, section_index)

    assert (
        chunk_registry.search_chunks(
            Partition.TECH,
            "查找目标",
            section_constraints=set(),
            limit=5,
        )
        == []
    )
    assert (
        section_registry.search(
            Partition.TECH,
            SECTION_LEVEL,
            "查找目标",
            3,
            document_ids=set(),
        )
        == []
    )
    assert chunk_index.calls == []
    assert section_index.calls == []


def test_health_reports_all_partitions_and_tree_levels():
    registry = object.__new__(HierarchicalIndexRegistry)
    registry._indexes = {
        (partition, level): object()
        for partition in Partition
        for level in LEVELS
        if not (partition == Partition.HR and level == CHUNK_LEVEL)
    }

    health = registry.health()

    assert health["finance"] == {
        DOCUMENT_LEVEL: "ready",
        SECTION_LEVEL: "ready",
        CHUNK_LEVEL: "ready",
    }
    assert health["hr"][CHUNK_LEVEL] == "error"
    assert health["tech"][DOCUMENT_LEVEL] == "ready"


def test_unknown_tree_level_is_rejected():
    registry = object.__new__(HierarchicalIndexRegistry)

    try:
        registry._key(Partition.TECH, "flat")
    except ValueError as exc:
        assert str(exc) == "unknown hierarchy level: flat"
    else:
        raise AssertionError("unknown tree level must be rejected")


def test_document_level_is_part_of_tree_registry_contract():
    assert LEVELS == (DOCUMENT_LEVEL, SECTION_LEVEL, CHUNK_LEVEL)


def test_load_failure_reports_the_partition_level_and_preserves_the_cause(tmp_path):
    class FailingEmbeddings:
        def __init__(self, _config) -> None:
            pass

        def load(self, _path: str) -> None:
            raise OSError("simulated load failure")

    target = tmp_path / "finance" / DOCUMENT_LEVEL
    target.mkdir(parents=True)
    (target / "marker").write_text("persisted", encoding="utf-8")
    registry = HierarchicalIndexRegistry(tmp_path, "test-model")
    registry._embeddings_type = FailingEmbeddings

    registry.load_all()

    with pytest.raises(
        RuntimeError,
        match=r"finance/document \(OSError\)",
    ) as error:
        registry.ensure_all_ready()

    assert isinstance(error.value.__cause__, OSError)


@pytest.mark.parametrize("operation", ["search", "delete", "verify_absent"])
def test_unloaded_chunk_level_never_looks_like_an_empty_index(operation: str):
    registry = object.__new__(HierarchicalIndexRegistry)
    registry._indexes = {}
    registry._locks = {
        (partition, level): RLock()
        for partition in Partition
        for level in LEVELS
    }
    registry._populated = {
        (partition, level): False
        for partition in Partition
        for level in LEVELS
    }

    with pytest.raises(RuntimeError, match="hierarchical index is not ready"):
        if operation == "search":
            registry.search_chunks(Partition.TECH, "query", 5)
        elif operation == "delete":
            registry.delete_chunks_and_save(Partition.TECH, ["chunk-1"])
        else:
            registry.verify_chunks_absent(Partition.TECH, ["chunk-1"])
