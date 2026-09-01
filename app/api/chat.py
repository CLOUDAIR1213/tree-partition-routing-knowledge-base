from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_index_registry, get_session
from app.models.schemas import ChatRequest, ChatResponse, ErrorResponse
from app.services.chat import ChatService

router = APIRouter(tags=["chat"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
IndexRegistryDep = Annotated[object, Depends(get_index_registry)]


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def chat(
    request: Request,
    payload: ChatRequest,
    session: SessionDep,
    index_registry: IndexRegistryDep,
) -> ChatResponse:
    service = ChatService(
        index_registry=index_registry,
        retrieval_top_k=request.app.state.settings.retrieval_top_k,
    )
    return await service.answer(session, payload, request.state.request_id)

