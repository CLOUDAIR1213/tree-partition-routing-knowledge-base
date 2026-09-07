from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.request_id import REQUEST_ID_PATTERN, new_request_id
from app.db.session import Database
from app.models.schemas import ErrorResponse


def create_app(
    settings: Settings | None = None,
    *,
    tree_index_registry=None,
    llm_provider=None,
    web_search_provider=None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_directories()
        database = Database(settings.metadata_database_url)
        registry = None
        try:
            await database.initialize()
            if tree_index_registry is None:
                from app.services.hierarchical_index import HierarchicalIndexRegistry

                registry = HierarchicalIndexRegistry(
                    settings.hierarchical_index_root,
                    settings.embedding_model,
                )
            else:
                registry = tree_index_registry
            registry.load_all()
            registry.ensure_all_ready()
            from app.services.hierarchy_builder import HierarchyIndexBuilder

            async with database.session_factory() as hierarchy_session:
                await HierarchyIndexBuilder(registry).sync_ready_documents(
                    hierarchy_session
                )
            if llm_provider is None:
                from app.services.llm import build_llm_provider

                provider = build_llm_provider(settings)
            else:
                provider = llm_provider
            if web_search_provider is None:
                from app.services.web_search import build_web_search_provider

                search_provider = build_web_search_provider(settings)
            else:
                search_provider = web_search_provider
            app.state.settings = settings
            app.state.database = database
            app.state.tree_index_registry = registry
            app.state.llm_provider = provider
            app.state.web_search_provider = search_provider
            yield
        finally:
            if registry is not None:
                registry.close_all()
            await database.close()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else new_request_id()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        body = ErrorResponse(
            code=exc.code,
            message=exc.message,
            request_id=request.state.request_id,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        partition_fields = {"partition", "confirmed_partition", "partition_hint"}
        invalid_partition = any(
            any(str(part) in partition_fields for part in error.get("loc", ()))
            for error in exc.errors()
        )
        code = "INVALID_PARTITION" if invalid_partition else "VALIDATION_ERROR"
        message = (
            "分区必须是 finance、hr 或 tech"
            if invalid_partition
            else "请求参数校验失败"
        )
        details = {
            "errors": [
                {
                    "field": ".".join(str(part) for part in error.get("loc", ())[1:]),
                    "type": error.get("type", "validation_error"),
                    "message": error.get("msg", "invalid value"),
                }
                for error in exc.errors()
            ]
        }
        body = ErrorResponse(
            code=code,
            message=message,
            request_id=request.state.request_id,
            details=details,
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "METHOD_NOT_ALLOWED"
        message = "接口不存在" if exc.status_code == 404 else "请求方法不允许"
        body = ErrorResponse(
            code=code,
            message=message,
            request_id=request.state.request_id,
            details=None,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, _exc: Exception) -> JSONResponse:
        body = ErrorResponse(
            code="INTERNAL_ERROR",
            message="服务发生未分类错误",
            request_id=request.state.request_id,
            details=None,
        )
        return JSONResponse(status_code=500, content=body.model_dump())

    from app.api.chat import router as chat_router
    from app.api.documents import router as documents_router
    from app.api.health import router as health_router

    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")

    if settings.serve_frontend:
        index_path = settings.frontend_dist_dir / "index.html"
        assets_path = settings.frontend_dist_dir / "assets"
        if not index_path.is_file() or not assets_path.is_dir():
            raise RuntimeError(
                "SERVE_FRONTEND=true requires a frontend production build in "
                f"{settings.frontend_dist_dir}"
            )

        app.mount(
            "/assets",
            StaticFiles(directory=assets_path),
            name="frontend-assets",
        )

        @app.get("/{frontend_path:path}", include_in_schema=False)
        async def frontend_application(frontend_path: str) -> FileResponse:
            if frontend_path.startswith("api/"):
                raise StarletteHTTPException(status_code=404)
            return FileResponse(index_path)

    return app


app = create_app()
