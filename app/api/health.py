from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.errors import AppError
from app.models.schemas import ErrorResponse, HealthResponse, IndexHealth

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": ErrorResponse}},
)
async def health(request: Request) -> HealthResponse:
    database_status = "ok"
    try:
        async with request.app.state.database.session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database_status = "error"
    indexes = request.app.state.tree_index_registry.health()
    settings = request.app.state.settings
    router_status = "configured" if settings.router_configured else "not_configured"
    answer_status = (
        "extractive"
        if settings.answer_mode == "extractive"
        else "configured"
        if settings.answer_configured
        else "not_configured"
    )
    web_search_status = (
        "disabled"
        if not settings.web_search_enabled
        else "configured"
        if settings.web_search_configured
        else "not_configured"
    )
    payload = HealthResponse(
        status=(
            "ok"
            if database_status == "ok"
            and all(
                level_status == "ready"
                for partition_status in indexes.values()
                for level_status in partition_status.values()
            )
            else "degraded"
        ),
        metadata_database=database_status,
        indexes=IndexHealth(**indexes),
        router=router_status,
        answer=answer_status,
        web_search=web_search_status,
        request_id=request.state.request_id,
    )
    if payload.status == "degraded":
        raise AppError(
            "SERVICE_UNAVAILABLE",
            "必需组件不可用",
            503,
            {"health": payload.model_dump(mode="json")},
        )
    return payload
