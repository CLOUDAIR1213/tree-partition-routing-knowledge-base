from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_index_registry,
    get_llm_provider,
    get_session,
    get_web_search_provider,
)
from app.models.schemas import ChatRequest, ChatResponse, ErrorResponse
from app.services.answering import LLMAnswerer, LLMWebAnswerer
from app.services.chat import ChatService
from app.services.routing import LLMRouter

router = APIRouter(tags=["chat"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
IndexRegistryDep = Annotated[object, Depends(get_index_registry)]
LLMProviderDep = Annotated[object | None, Depends(get_llm_provider)]
WebSearchProviderDep = Annotated[object | None, Depends(get_web_search_provider)]


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
    llm_provider: LLMProviderDep,
    web_search_provider: WebSearchProviderDep,
) -> ChatResponse:
    settings = request.app.state.settings
    llm_router = (
        LLMRouter(
            llm_provider,
            settings.resolved_router_llm_model,
            settings.router_retry_count,
            settings.max_question_length,
            settings.composite_max_partitions,
        )
        if llm_provider is not None and settings.router_configured
        else None
    )
    answerer = (
        LLMAnswerer(llm_provider, settings.resolved_answer_llm_model)
        if llm_provider is not None and settings.answer_configured
        else None
    )
    web_answerer = (
        LLMWebAnswerer(llm_provider, settings.resolved_answer_llm_model)
        if llm_provider is not None and settings.answer_configured
        else None
    )
    service = ChatService(
        index_registry=index_registry,
        retrieval_top_k=settings.retrieval_top_k,
        retrieval_min_score=settings.retrieval_min_score,
        composite_top_k=settings.composite_top_k_per_partition,
        router=llm_router,
        answerer=answerer,
        web_search_provider=web_search_provider,
        web_answerer=web_answerer,
        web_search_max_results=settings.web_search_max_results,
        answer_mode=settings.answer_mode,
    )
    return await service.answer(session, payload, request.state.request_id)
