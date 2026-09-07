from fastapi import Request

from app.db.session import Database


def get_database(request: Request) -> Database:
    return request.app.state.database


async def get_session(request: Request):
    database: Database = request.app.state.database
    async for session in database.session():
        yield session


def get_tree_index_registry(request: Request):
    return request.app.state.tree_index_registry


def get_llm_provider(request: Request):
    return request.app.state.llm_provider


def get_web_search_provider(request: Request):
    return request.app.state.web_search_provider
