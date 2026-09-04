from datetime import UTC
from typing import Annotated

from anyio import to_thread
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Path,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_index_registry, get_session
from app.core.errors import AppError
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.models.schemas import (
    ChangeDocumentPartitionRequest,
    ChangeDocumentPartitionResponse,
    ChunkPreviewItem,
    ChunkPreviewResponse,
    DeleteDocumentResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentSummaryResponse,
    ErrorResponse,
    ParseQualityReport,
    ReopenDocumentReviewRequest,
    ReopenDocumentReviewResponse,
    ReviewRequest,
    ReviewResponse,
    UploadDocumentResponse,
)
from app.services.document_management import DocumentManagementService
from app.services.file_storage import FileStorage
from app.services.ingestion import IngestionService, get_document_or_404
from app.services.review import ReviewService

router = APIRouter(prefix="/documents", tags=["documents"])
DocumentId = Annotated[str, Path(pattern=r"^doc_[0-9a-f]{24}$")]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
IndexRegistryDep = Annotated[object, Depends(get_index_registry)]


def _utc(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def _summary(document: DocumentTable) -> DocumentSummaryResponse:
    return DocumentSummaryResponse(
        document_id=document.id,
        original_filename=document.original_filename,
        title=document.title,
        selected_partition=Partition(document.selected_partition),
        confirmed_partition=(
            Partition(document.confirmed_partition) if document.confirmed_partition else None
        ),
        status=DocumentStatus(document.status),
        chunk_count=document.chunk_count,
        created_at=_utc(document.created_at),
        updated_at=_utc(document.updated_at),
    )


def _load_parse_quality(settings, document_id: str) -> ParseQualityReport | None:
    storage = _file_storage(settings)
    try:
        snapshot = storage.read_parse_snapshot(document_id)
        payload = snapshot.get("parse_quality") if snapshot else None
        return ParseQualityReport.model_validate(payload) if payload else None
    except (OSError, ValueError):
        return None


def _file_storage(settings) -> FileStorage:
    return FileStorage(
        settings.raw_root,
        settings.staging_root,
        settings.max_upload_size_bytes,
        settings.allowed_file_types,
    )


ERROR_RESPONSES = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    415: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}


@router.post(
    "",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    partition: Annotated[Partition, Form()],
    session: SessionDep,
    title: Annotated[str | None, Form(max_length=200)] = None,
) -> UploadDocumentResponse:
    settings = request.app.state.settings
    content = await file.read(settings.max_upload_size_bytes + 1)
    service = IngestionService(settings)
    document, parse_quality = await service.ingest(
        session,
        original_filename=file.filename or "document",
        content=content,
        partition=partition,
        custom_title=title,
    )
    return UploadDocumentResponse(
        document_id=document.id,
        original_filename=document.original_filename,
        selected_partition=Partition(document.selected_partition),
        confirmed_partition=None,
        status=DocumentStatus(document.status),
        chunk_count=document.chunk_count,
        warnings=parse_quality.warnings,
        parse_quality=parse_quality,
        request_id=request.state.request_id,
    )


@router.get("", response_model=DocumentListResponse, responses={422: {"model": ErrorResponse}})
async def list_documents(
    request: Request,
    session: SessionDep,
    document_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    partition: Annotated[Partition | None, Query()] = None,
    query: Annotated[str | None, Query(alias="q", max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    filters = []
    if document_status:
        filters.append(DocumentTable.status == document_status.value)
    if partition:
        filters.append(
            func.coalesce(
                DocumentTable.confirmed_partition,
                DocumentTable.selected_partition,
            )
            == partition.value
        )
    normalized_query = query.strip() if query else ""
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                DocumentTable.title.ilike(pattern),
                DocumentTable.original_filename.ilike(pattern),
            )
        )
    total = int(
        await session.scalar(select(func.count()).select_from(DocumentTable).where(*filters))
        or 0
    )
    documents = list(
        (
            await session.scalars(
                select(DocumentTable)
                .where(*filters)
                .order_by(DocumentTable.created_at.desc(), DocumentTable.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return DocumentListResponse(
        items=[_summary(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
        request_id=request.state.request_id,
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse, responses=ERROR_RESPONSES)
async def get_document(
    request: Request,
    document_id: DocumentId,
    session: SessionDep,
) -> DocumentDetailResponse:
    document = await get_document_or_404(session, document_id)
    summary = _summary(document)
    parse_quality = await to_thread.run_sync(
        _load_parse_quality, request.app.state.settings, document_id
    )
    return DocumentDetailResponse(
        **summary.model_dump(),
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        reviewed_at=_utc(document.reviewed_at),
        review_note=document.review_note,
        error_code=document.error_code,
        error_message=document.error_message,
        parse_quality=parse_quality,
        request_id=request.state.request_id,
    )


@router.get(
    "/{document_id}/preview",
    response_model=ChunkPreviewResponse,
    responses=ERROR_RESPONSES,
)
async def preview_document(
    request: Request,
    document_id: DocumentId,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChunkPreviewResponse:
    document = await get_document_or_404(session, document_id)
    parse_quality = await to_thread.run_sync(
        _load_parse_quality, request.app.state.settings, document_id
    )
    total = int(
        await session.scalar(
            select(func.count()).select_from(ChunkCandidateTable).where(
                ChunkCandidateTable.document_id == document_id
            )
        )
        or 0
    )
    if total == 0:
        raise AppError("PREVIEW_NOT_READY", "文档尚未产生可预览 Chunk", 409)
    chunks = list(
        (
            await session.scalars(
                select(ChunkCandidateTable)
                .where(ChunkCandidateTable.document_id == document_id)
                .order_by(ChunkCandidateTable.chunk_index)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return ChunkPreviewResponse(
        document_id=document.id,
        title=document.title,
        selected_partition=Partition(document.selected_partition),
        confirmed_partition=(
            Partition(document.confirmed_partition) if document.confirmed_partition else None
        ),
        status=DocumentStatus(document.status),
        chunk_count=document.chunk_count,
        items=[
            ChunkPreviewItem(
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                title=chunk.title,
                section_path=chunk.section_path,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                text=chunk.text,
                preview=chunk.text[:300],
            )
            for chunk in chunks
        ],
        total=total,
        limit=limit,
        offset=offset,
        parse_quality=parse_quality,
        request_id=request.state.request_id,
    )


@router.post(
    "/{document_id}/review",
    response_model=ReviewResponse,
    responses=ERROR_RESPONSES,
)
async def review_document(
    request: Request,
    document_id: DocumentId,
    payload: ReviewRequest,
    session: SessionDep,
    index_registry: IndexRegistryDep,
) -> ReviewResponse:
    document, indexed_count = await ReviewService(index_registry).review(
        session, document_id, payload
    )
    return ReviewResponse(
        document_id=document.id,
        selected_partition=Partition(document.selected_partition),
        confirmed_partition=(
            Partition(document.confirmed_partition) if document.confirmed_partition else None
        ),
        status=DocumentStatus(document.status),
        indexed_chunk_count=indexed_count,
        reviewed_at=_utc(document.reviewed_at),
        review_note=document.review_note,
        request_id=request.state.request_id,
    )


@router.post(
    "/{document_id}/partition",
    response_model=ChangeDocumentPartitionResponse,
    responses=ERROR_RESPONSES,
)
async def change_document_partition(
    request: Request,
    document_id: DocumentId,
    payload: ChangeDocumentPartitionRequest,
    session: SessionDep,
    index_registry: IndexRegistryDep,
) -> ChangeDocumentPartitionResponse:
    service = DocumentManagementService(
        index_registry,
        _file_storage(request.app.state.settings),
    )
    document, previous_partition, reindexed_count = await service.change_partition(
        session,
        document_id,
        payload,
    )
    return ChangeDocumentPartitionResponse(
        document_id=document.id,
        previous_partition=previous_partition,
        confirmed_partition=Partition(document.confirmed_partition),
        status=DocumentStatus(document.status),
        reindexed_chunk_count=reindexed_count,
        reviewed_at=_utc(document.reviewed_at),
        review_note=document.review_note,
        request_id=request.state.request_id,
    )


@router.post(
    "/{document_id}/reopen-review",
    response_model=ReopenDocumentReviewResponse,
    responses=ERROR_RESPONSES,
)
async def reopen_document_review(
    request: Request,
    document_id: DocumentId,
    payload: ReopenDocumentReviewRequest,
    session: SessionDep,
    index_registry: IndexRegistryDep,
) -> ReopenDocumentReviewResponse:
    service = DocumentManagementService(
        index_registry,
        _file_storage(request.app.state.settings),
    )
    document, previous_partition, removed_count = await service.reopen_review(
        session,
        document_id,
        payload,
    )
    return ReopenDocumentReviewResponse(
        document_id=document.id,
        previous_partition=previous_partition,
        confirmed_partition=None,
        status=DocumentStatus(document.status),
        removed_indexed_chunk_count=removed_count,
        reviewed_at=_utc(document.reviewed_at),
        review_note=document.review_note,
        request_id=request.state.request_id,
    )


@router.delete(
    "/{document_id}",
    response_model=DeleteDocumentResponse,
    responses=ERROR_RESPONSES,
)
async def delete_document(
    request: Request,
    document_id: DocumentId,
    session: SessionDep,
    index_registry: IndexRegistryDep,
) -> DeleteDocumentResponse:
    service = DocumentManagementService(
        index_registry,
        _file_storage(request.app.state.settings),
    )
    removed_count = await service.delete_document(session, document_id)
    return DeleteDocumentResponse(
        document_id=document_id,
        deleted=True,
        removed_chunk_count=removed_count,
        request_id=request.state.request_id,
    )
