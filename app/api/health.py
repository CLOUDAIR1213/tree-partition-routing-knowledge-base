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
    indexes = request.app.state.index_registry.health()
    router_status = (
        "configured"
        if request.app.state.settings.llm_model
        and request.app.state.settings.llm_base_url
        and request.app.state.settings.llm_api_key
        else "not_configured"
    )
    payload = HealthResponse(
        status=(
            "ok"
            if database_status == "ok" and all(value == "ready" for value in indexes.values())
            else "degraded"
        ),
        metadata_database=database_status,
        indexes=IndexHealth(**indexes),
        router=router_status,
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
