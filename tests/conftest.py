from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.hierarchical_index import (
    CHUNK_LEVEL,
    DOCUMENT_LEVEL,
    SECTION_LEVEL,
    HierarchyNode,
    HierarchySearchHit,
    normalize_section,
)


class FakeTreeIndexRegistry:
    def __init__(self) -> None:
        self.rows = {
            **{name: {} for name in ("finance", "hr", "tech")},
            **{
                (partition, level): {}
                for partition in ("finance", "hr", "tech")
                for level in (DOCUMENT_LEVEL, SECTION_LEVEL)
            },
        }
        self.upsert_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.search_calls: list[str] = []
        self.node_upsert_calls: list[tuple[str, str]] = []
        self.node_delete_calls: list[tuple[str, str]] = []
        self.node_search_calls: list[tuple[str, str]] = []
        self.search_section_constraints: list[
            frozenset[tuple[str, str]] | None
        ] = []
        self.search_document_constraints: list[frozenset[str] | None] = []
        self.search_results: dict[object, list] = {
            name: [] for name in ("finance", "hr", "tech")
        }
        self.nodes: dict[str, HierarchyNode] = {}
        self.fail_after_upsert = False
        self.fail_next_upsert = False
        self.fail_next_node_upsert = False
        self.fail_next_node_search = False

    def load_all(self) -> None:
        pass

    def ensure_all_ready(self) -> None:
        pass

    def upsert_chunks_and_save(self, partition, rows: list[dict]) -> None:
        self.upsert_calls.append(partition.value)
        self.rows[partition.value].update({row["id"]: row for row in rows})
        if self.fail_next_upsert:
            self.fail_next_upsert = False
            raise RuntimeError("simulated one-time index save failure")
        if self.fail_after_upsert:
            raise RuntimeError("simulated index save failure")

    def delete_chunks_and_save(self, partition, chunk_ids: list[str]) -> None:
        self.delete_calls.append(partition.value)
        for chunk_id in chunk_ids:
            self.rows[partition.value].pop(chunk_id, None)

    def verify_chunks(self, partition, chunk_ids: list[str]) -> bool:
        return all(chunk_id in self.rows[partition.value] for chunk_id in chunk_ids)

    def verify_chunks_absent(self, partition, chunk_ids: list[str]) -> bool:
        return all(chunk_id not in self.rows[partition.value] for chunk_id in chunk_ids)

    def search_chunks(
        self,
        partition,
        query: str,
        limit: int = 5,
        *,
        section_constraints=None,
    ) -> list[dict]:
        self.search_calls.append(partition.value)
        scope = (
            frozenset(section_constraints)
            if section_constraints is not None
            else None
        )
        self.search_section_constraints.append(scope)
        results = self.search_results[partition.value]
        if scope is not None:
            rows = self.rows[partition.value]
            results = [
                hit
                for hit in results
                if (
                    row := rows.get(str(hit.get("id")))
                ) is not None
                and (row["document_id"], normalize_section(row.get("section")))
                in scope
            ]
        return results[:limit]

    def upsert_and_save(self, partition, level: str, nodes: list[HierarchyNode]) -> None:
        self.node_upsert_calls.append((partition.value, level))
        self.rows[(partition.value, level)].update(
            {node.id: node for node in nodes}
        )
        self.nodes.update({node.id: node for node in nodes})
        if self.fail_next_node_upsert:
            self.fail_next_node_upsert = False
            raise RuntimeError("simulated one-time hierarchy index save failure")

    def delete_and_save(self, partition, level: str, node_ids: list[str]) -> None:
        self.node_delete_calls.append((partition.value, level))
        rows = self.rows[(partition.value, level)]
        for node_id in node_ids:
            rows.pop(node_id, None)
            node = self.nodes.get(node_id)
            if node is not None and node.partition == partition:
                self.nodes.pop(node_id, None)

    def verify(self, partition, level: str, node_ids: list[str]) -> bool:
        rows = self.rows[(partition.value, level)]
        return all(node_id in rows for node_id in node_ids)

    def verify_absent(self, partition, level: str, node_ids: list[str]) -> bool:
        rows = self.rows[(partition.value, level)]
        return all(node_id not in rows for node_id in node_ids)

    def load_nodes(self, nodes: list[HierarchyNode]) -> None:
        self.nodes = {node.id: node for node in nodes}

    def search(
        self,
        partition,
        level: str,
        query: str,
        limit: int,
        *,
        document_ids=None,
    ):
        if self.fail_next_node_search:
            self.fail_next_node_search = False
            raise RuntimeError("simulated unavailable tree level")
        self.node_search_calls.append((partition.value, level))
        scope = frozenset(document_ids) if document_ids is not None else None
        self.search_document_constraints.append(scope)
        results = self.search_results.get((partition.value, level))
        if results is None:
            results = [
                HierarchySearchHit(node=node, score=0.9)
                for node in self.rows[(partition.value, level)].values()
            ]
        if scope is not None:
            results = [hit for hit in results if hit.node.document_id in scope]
        return results[:limit]

    def health(self) -> dict[str, dict[str, str]]:
        return {
            partition: {
                DOCUMENT_LEVEL: "ready",
                SECTION_LEVEL: "ready",
                CHUNK_LEVEL: "ready",
            }
            for partition in ("finance", "hr", "tech")
        }

    def close_all(self) -> None:
        pass


@pytest.fixture
def fake_registry() -> FakeTreeIndexRegistry:
    return FakeTreeIndexRegistry()


@pytest.fixture
def fake_hierarchy_registry(fake_registry: FakeTreeIndexRegistry) -> FakeTreeIndexRegistry:
    return fake_registry


@pytest.fixture
def client(tmp_path: Path, fake_registry: FakeTreeIndexRegistry) -> Iterator[TestClient]:
    data_root = tmp_path / "data"
    settings = Settings(
        data_root=data_root,
        raw_root=data_root / "raw",
        staging_root=data_root / "staging",
        hierarchical_index_root=data_root / "indexes-hierarchical",
        fixture_root=data_root / "fixtures",
        metadata_database_url=f"sqlite+aiosqlite:///{(data_root / 'metadata' / 'knowledge.db').as_posix()}",
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        router_llm_model="",
        answer_llm_model="",
        answer_mode="llm",
        web_search_enabled=False,
        web_search_api_key="",
    )
    with TestClient(create_app(settings, tree_index_registry=fake_registry)) as test_client:
        yield test_client


@pytest.fixture
def hierarchical_client(
    tmp_path: Path,
    fake_registry: FakeTreeIndexRegistry,
    fake_hierarchy_registry: FakeTreeIndexRegistry,
) -> Iterator[TestClient]:
    data_root = tmp_path / "hierarchical-data"
    settings = Settings(
        data_root=data_root,
        raw_root=data_root / "raw",
        staging_root=data_root / "staging",
        hierarchical_index_root=data_root / "indexes-hierarchical",
        fixture_root=data_root / "fixtures",
        metadata_database_url=f"sqlite+aiosqlite:///{(data_root / 'metadata' / 'knowledge.db').as_posix()}",
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        router_llm_model="",
        answer_llm_model="",
        answer_mode="llm",
        web_search_enabled=False,
        web_search_api_key="",
    )
    app = create_app(
        settings,
        tree_index_registry=fake_registry,
    )
    with TestClient(app) as test_client:
        yield test_client
