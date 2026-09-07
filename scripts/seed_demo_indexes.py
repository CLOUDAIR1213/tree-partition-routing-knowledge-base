import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.db.session import Database
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.services.hierarchical_index import HierarchicalIndexRegistry
from app.services.hierarchy_builder import HierarchyIndexBuilder


def load_fixtures(root: Path, partition: Partition) -> list[dict]:
    return [
        json.loads(line)
        for line in (root / f"{partition.value}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def seed() -> None:
    settings = get_settings()
    settings.ensure_directories()
    database = Database(settings.metadata_database_url)
    await database.initialize()
    registry = HierarchicalIndexRegistry(
        settings.hierarchical_index_root,
        settings.embedding_model,
    )
    registry.load_all()
    now = datetime.now(UTC)
    try:
        async with database.session_factory() as session:
            for partition in Partition:
                for fixture in load_fixtures(settings.fixture_root, partition):
                    document_id = fixture["document_id"]
                    document = await session.get(DocumentTable, document_id)
                    if document is None:
                        document = DocumentTable(
                            id=document_id,
                            original_filename=f"{document_id}.md",
                            stored_path=f"fixture://{document_id}",
                            mime_type="text/markdown",
                            size_bytes=sum(len(item["text"].encode("utf-8")) for item in fixture["chunks"]),
                            checksum_sha256=hashlib.sha256(document_id.encode()).hexdigest(),
                            selected_partition=partition.value,
                            confirmed_partition=partition.value,
                            title=fixture["title"],
                            status=DocumentStatus.READY.value,
                            chunk_count=len(fixture["chunks"]),
                            reviewed_by="seed-script",
                            review_note="虚构演示数据",
                            reviewed_at=now,
                        )
                        session.add(document)
                        await session.flush()
                    for index, item in enumerate(fixture["chunks"]):
                        chunk_id = f"{document_id}:v1:{index:05d}"
                        embedding_text = (
                            f"文档：{fixture['title']}\n章节：{item['section']}\n正文：{item['text']}"
                        )
                        existing = await session.get(ChunkCandidateTable, chunk_id)
                        if existing is None:
                            session.add(
                                ChunkCandidateTable(
                                    id=chunk_id,
                                    document_id=document_id,
                                    chunk_index=index,
                                    text=item["text"],
                                    embedding_text=embedding_text,
                                    title=fixture["title"],
                                    section_path=item["section"],
                                    checksum_sha256=hashlib.sha256(embedding_text.encode()).hexdigest(),
                                    indexed_at=now,
                                )
                            )
            await session.commit()
            await HierarchyIndexBuilder(registry).sync_ready_documents(session)
            print("seeded document, section and chunk tree indexes")
    finally:
        registry.close_all()
        await database.close()


if __name__ == "__main__":
    asyncio.run(seed())
