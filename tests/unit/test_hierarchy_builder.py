import hashlib
from pathlib import Path

from app.db.session import Database
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.services.hierarchy_builder import HierarchyIndexBuilder
from tests.conftest import FakeTreeIndexRegistry


def document(document_id: str, status: DocumentStatus, partition: str | None):
    return DocumentTable(
        id=document_id,
        original_filename=f"{document_id}.md",
        stored_path=f"fixture://{document_id}",
        mime_type="text/markdown",
        size_bytes=10,
        checksum_sha256=hashlib.sha256(document_id.encode()).hexdigest(),
        selected_partition=Partition.TECH.value,
        confirmed_partition=partition,
        title=document_id,
        status=status.value,
        chunk_count=1,
    )


def chunk(document_id: str):
    text = f"{document_id} content"
    return ChunkCandidateTable(
        id=f"{document_id}:v1:00000",
        document_id=document_id,
        chunk_index=0,
        text=text,
        embedding_text=text,
        title=document_id,
        section_path="section",
        checksum_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


async def test_startup_sync_enforces_chunk_partition_and_ready_status(
    tmp_path: Path,
):
    database = Database(
        f"sqlite+aiosqlite:///{(tmp_path / 'knowledge.db').as_posix()}"
    )
    await database.initialize()
    async with database.session_factory() as session:
        session.add_all(
            [
                document("ready-document", DocumentStatus.READY, Partition.TECH.value),
                document("pending-document", DocumentStatus.PENDING_REVIEW, None),
            ]
        )
        await session.flush()
        session.add_all([chunk("ready-document"), chunk("pending-document")])
        await session.commit()

    registry = FakeTreeIndexRegistry()
    for partition in Partition:
        registry.rows[partition.value]["ready-document:v1:00000"] = {}
        registry.rows[partition.value]["pending-document:v1:00000"] = {}

    async with database.session_factory() as session:
        await HierarchyIndexBuilder(registry).sync_ready_documents(session)

    assert "ready-document:v1:00000" in registry.rows[Partition.TECH.value]
    assert "ready-document:v1:00000" not in registry.rows[Partition.FINANCE.value]
    assert "ready-document:v1:00000" not in registry.rows[Partition.HR.value]
    assert all(
        "pending-document:v1:00000" not in registry.rows[partition.value]
        for partition in Partition
    )
    await database.close()
