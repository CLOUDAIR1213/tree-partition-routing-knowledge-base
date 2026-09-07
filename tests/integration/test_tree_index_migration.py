import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db.session import Database
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.services.hierarchical_index import LEVELS
from scripts.migrate_tree_only_indexes import (
    MigrationError,
    run_migration,
    validate_paths,
)


class FakeMigrationRegistry:
    fail_chunk_verification = False

    def __init__(self, root: Path, _embedding_model: str) -> None:
        self.root = root
        self.chunks = {partition: set() for partition in Partition}
        self.nodes = {
            (partition, level): set()
            for partition in Partition
            for level in LEVELS
        }

    def load_all(self) -> None:
        for partition in Partition:
            for level in LEVELS:
                path = self.root / partition.value / level
                path.mkdir(parents=True, exist_ok=True)
                (path / "index.marker").write_text("test", encoding="utf-8")

    def upsert_chunks_and_save(self, partition, rows) -> None:
        self.chunks[partition].update(row["id"] for row in rows)

    def verify_chunks(self, partition, chunk_ids) -> bool:
        return not self.fail_chunk_verification and all(
            chunk_id in self.chunks[partition] for chunk_id in chunk_ids
        )

    def verify_chunks_absent(self, partition, chunk_ids) -> bool:
        return all(chunk_id not in self.chunks[partition] for chunk_id in chunk_ids)

    def upsert_and_save(self, partition, level, nodes) -> None:
        self.nodes[(partition, level)].update(node.id for node in nodes)

    def verify(self, partition, level, node_ids) -> bool:
        return all(node_id in self.nodes[(partition, level)] for node_id in node_ids)

    def verify_absent(self, partition, level, node_ids) -> bool:
        return all(
            node_id not in self.nodes[(partition, level)] for node_id in node_ids
        )

    def health(self):
        return {
            partition.value: {level: "ready" for level in LEVELS}
            for partition in Partition
        }

    def close_all(self) -> None:
        pass


async def create_source_database(path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{path.as_posix()}")
    await database.initialize()
    now = datetime.now(UTC)
    async with database.session_factory() as session:
        session.add(
            DocumentTable(
                id="document-tech",
                original_filename="tech.md",
                stored_path="fixture://tech.md",
                mime_type="text/markdown",
                size_bytes=12,
                checksum_sha256=hashlib.sha256(b"document-tech").hexdigest(),
                selected_partition=Partition.TECH.value,
                confirmed_partition=Partition.TECH.value,
                title="技术制度",
                status=DocumentStatus.READY.value,
                chunk_count=2,
            )
        )
        for index, section in enumerate(("发布", None)):
            text = f"测试正文 {index}"
            session.add(
                ChunkCandidateTable(
                    id=f"document-tech:v1:{index:05d}",
                    document_id="document-tech",
                    chunk_index=index,
                    text=text,
                    embedding_text=f"文档：技术制度\n正文：{text}",
                    title="技术制度",
                    section_path=section,
                    checksum_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    indexed_at=now,
                )
            )
        await session.commit()
    await database.close()


def test_migration_rejects_active_flat_and_nonempty_targets(tmp_path: Path):
    source = tmp_path / "knowledge.db"
    source.touch()
    active = tmp_path / "tree"
    legacy = tmp_path / "indexes"
    active.mkdir()
    legacy.mkdir()

    with pytest.raises(MigrationError, match="active tree root"):
        validate_paths(source, active, active, legacy)
    with pytest.raises(MigrationError, match="legacy Flat root"):
        validate_paths(source, legacy / "temporary", active, legacy)

    target = tmp_path / "temporary"
    target.mkdir()
    (target / "unexpected").write_text("occupied", encoding="utf-8")
    with pytest.raises(MigrationError, match="absent or empty"):
        validate_paths(source, target, active, legacy)


async def test_migration_rejects_report_inside_target(tmp_path: Path):
    source = tmp_path / "knowledge.db"
    await create_source_database(source)
    target = tmp_path / "candidate"

    with pytest.raises(MigrationError, match="outside target root"):
        await run_migration(
            source,
            target,
            target / "report.json",
            tmp_path / "active",
            tmp_path / "indexes",
            "test-model",
            registry_factory=FakeMigrationRegistry,
        )


async def test_migration_builds_three_levels_and_writes_safe_report(tmp_path: Path):
    source = tmp_path / "knowledge.db"
    await create_source_database(source)
    active = tmp_path / "indexes-hierarchical"
    active.mkdir()
    legacy = tmp_path / "indexes"
    legacy.mkdir()
    target = tmp_path / "indexes-tree-candidate"
    report_path = tmp_path / "migration-report.json"

    report = await run_migration(
        source,
        target,
        report_path,
        active,
        legacy,
        "test-model",
        registry_factory=FakeMigrationRegistry,
    )

    assert report["status"] == "verified"
    assert report["levels"] == ["document", "section", "chunk"]
    assert report["partitions"]["tech"]["documents"] == 1
    assert report["partitions"]["tech"]["sections"] == 2
    assert report["partitions"]["tech"]["chunks"] == 2
    report_text = report_path.read_text(encoding="utf-8")
    assert str(tmp_path.resolve()) not in report_text
    assert "测试正文" not in report_text
    assert not (active / "tech" / "chunk").exists()
    assert (target / "tech" / "chunk" / "index.marker").is_file()


async def test_failed_verification_never_switches_active_tree(tmp_path: Path):
    source = tmp_path / "knowledge.db"
    await create_source_database(source)
    active = tmp_path / "indexes-hierarchical"
    active.mkdir()
    (active / "active.marker").write_text("old", encoding="utf-8")
    legacy = tmp_path / "indexes"
    legacy.mkdir()
    target = tmp_path / "indexes-tree-candidate"
    backup = tmp_path / "indexes-tree-backup"

    class FailingRegistry(FakeMigrationRegistry):
        fail_chunk_verification = True

    report = await run_migration(
        source,
        target,
        tmp_path / "migration-report.json",
        active,
        legacy,
        "test-model",
        activate=True,
        backup_root=backup,
        registry_factory=FailingRegistry,
    )

    assert report["status"] == "failed"
    assert report["activation_error"] == "verification_failed"
    assert (active / "active.marker").is_file()
    assert target.is_dir()
    assert not backup.exists()


async def test_verified_target_switch_preserves_previous_tree_as_backup(
    tmp_path: Path,
):
    source = tmp_path / "knowledge.db"
    await create_source_database(source)
    active = tmp_path / "indexes-hierarchical"
    active.mkdir()
    (active / "active.marker").write_text("old", encoding="utf-8")
    legacy = tmp_path / "indexes"
    legacy.mkdir()
    (legacy / "flat.marker").write_text("untouched", encoding="utf-8")
    target = tmp_path / "indexes-tree-candidate"
    backup = tmp_path / "indexes-tree-backup"

    report = await run_migration(
        source,
        target,
        tmp_path / "migration-report.json",
        active,
        legacy,
        "test-model",
        activate=True,
        backup_root=backup,
        registry_factory=FakeMigrationRegistry,
    )

    assert report["status"] == "verified"
    assert report["activated"] is True
    assert not target.exists()
    assert (active / "tech" / "chunk" / "index.marker").is_file()
    assert (backup / "active.marker").read_text(encoding="utf-8") == "old"
    assert (legacy / "flat.marker").read_text(encoding="utf-8") == "untouched"
