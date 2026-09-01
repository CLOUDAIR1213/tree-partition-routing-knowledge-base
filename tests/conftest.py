from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class FakeIndexRegistry:
    def __init__(self) -> None:
        self.rows = {name: {} for name in ("finance", "hr", "tech")}
        self.upsert_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.fail_after_upsert = False

    def load_all(self) -> None:
        pass

    def upsert_and_save(self, partition, rows: list[dict]) -> None:
        self.upsert_calls.append(partition.value)
        self.rows[partition.value].update({row["id"]: row for row in rows})
        if self.fail_after_upsert:
            raise RuntimeError("simulated index save failure")

    def delete_and_save(self, partition, chunk_ids: list[str]) -> None:
        self.delete_calls.append(partition.value)
        for chunk_id in chunk_ids:
            self.rows[partition.value].pop(chunk_id, None)

    def verify(self, partition, chunk_ids: list[str]) -> bool:
        return all(chunk_id in self.rows[partition.value] for chunk_id in chunk_ids)

    def health(self) -> dict[str, str]:
        return {name: "ready" for name in self.rows}

    def close_all(self) -> None:
        pass


@pytest.fixture
def fake_registry() -> FakeIndexRegistry:
    return FakeIndexRegistry()


@pytest.fixture
def client(tmp_path: Path, fake_registry: FakeIndexRegistry) -> Iterator[TestClient]:
    data_root = tmp_path / "data"
    settings = Settings(
        data_root=data_root,
        raw_root=data_root / "raw",
        staging_root=data_root / "staging",
        index_root=data_root / "indexes",
        fixture_root=data_root / "fixtures",
        metadata_database_url=f"sqlite+aiosqlite:///{(data_root / 'metadata' / 'knowledge.db').as_posix()}",
    )
    with TestClient(create_app(settings, index_registry=fake_registry)) as test_client:
        yield test_client
