from collections.abc import AsyncIterator

from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base
from app.db.tables import DocumentTable
from app.models.enums import DocumentStatus


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine.sync_engine, "connect")
            def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await self.mark_interrupted_indexing_failed()

    async def mark_interrupted_indexing_failed(self) -> None:
        async with self.session_factory() as session:
            interrupted = (
                (
                    DocumentStatus.INDEXING,
                    "INDEX_RECOVERY_REQUIRED",
                    "应用启动时发现未完成的索引写入，需要人工重试",
                ),
                (
                    DocumentStatus.REINDEXING,
                    "REINDEX_RECOVERY_REQUIRED",
                    "应用启动时发现未完成的索引调整，需要人工检查",
                ),
                (
                    DocumentStatus.DELETING,
                    "DELETE_RECOVERY_REQUIRED",
                    "应用启动时发现未完成的文档删除，可重试删除",
                ),
            )
            for current_status, error_code, error_message in interrupted:
                await session.execute(
                    update(DocumentTable)
                    .where(DocumentTable.status == current_status.value)
                    .values(
                        status=DocumentStatus.FAILED.value,
                        error_code=error_code,
                        error_message=error_message,
                    )
                )
            await session.commit()

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
