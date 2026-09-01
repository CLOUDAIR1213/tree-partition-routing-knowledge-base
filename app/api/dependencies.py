from fastapi import Request

from app.db.session import Database


def get_database(request: Request) -> Database:
    return request.app.state.database


async def get_session(request: Request):
    database: Database = request.app.state.database
    async for session in database.session():
        yield session


def get_index_registry(request: Request):
    return request.app.state.index_registry

