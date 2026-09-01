from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    DecisionSource,
    DocumentStatus,
    Partition,
    ReviewAction,
    RouteName,
    SafetyAction,
)


class StrictApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReviewRequest(StrictApiRequest):
    action: ReviewAction
    confirmed_partition: Partition | None = None
    reviewer_name: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class ChatRequest(StrictApiRequest):
    question: str = Field(min_length=1, max_length=2000)
    partition_hint: Partition | None = None


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    section: str | None
    page_start: int | None
    page_end: int | None


class ChatResponse(BaseModel):
    code: Literal[
        "OK",
        "ROUTE_CLARIFICATION_REQUIRED",
        "NO_INTERNAL_EVIDENCE",
        "SENSITIVE_INPUT_BLOCKED",
    ]
    answer: str
    route: RouteName
    decision_source: DecisionSource
    answerable: bool
    citations: list[Citation]
    suggested_partitions: list[Partition]
    request_id: str
    warning: str | None


class SafetyDecision(BaseModel):
    action: SafetyAction
    safe_question: str | None
    detected_types: list[str]
    message: str | None = None


class RetrievalHit(BaseModel):
    chunk_id: str
    document_id: str
    partition: Partition
    text: str
    score: float
    title: str
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class UploadDocumentResponse(BaseModel):
    document_id: str
    original_filename: str
    selected_partition: Partition
    confirmed_partition: Partition | None
    status: DocumentStatus
    chunk_count: int
    warnings: list[str]
    request_id: str


class DocumentSummaryResponse(BaseModel):
    document_id: str
    original_filename: str
    title: str | None
    selected_partition: Partition
    confirmed_partition: Partition | None
    status: DocumentStatus
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class DocumentDetailResponse(DocumentSummaryResponse):
    mime_type: str
    size_bytes: int
    reviewed_at: datetime | None
    review_note: str | None
    error_code: str | None
    error_message: str | None
    request_id: str


class DocumentListResponse(BaseModel):
    items: list[DocumentSummaryResponse]
    total: int
    limit: int
    offset: int
    request_id: str


class ChunkPreviewItem(BaseModel):
    chunk_id: str
    chunk_index: int
    title: str | None
    section_path: str | None
    page_start: int | None
    page_end: int | None
    preview: str


class ChunkPreviewResponse(BaseModel):
    document_id: str
    title: str | None
    selected_partition: Partition
    confirmed_partition: Partition | None
    status: DocumentStatus
    chunk_count: int
    items: list[ChunkPreviewItem]
    total: int
    limit: int
    offset: int
    request_id: str


class ReviewResponse(BaseModel):
    document_id: str
    selected_partition: Partition
    confirmed_partition: Partition | None
    status: DocumentStatus
    indexed_chunk_count: int
    reviewed_at: datetime
    review_note: str | None
    request_id: str


class IndexHealth(BaseModel):
    finance: Literal["ready", "error"]
    hr: Literal["ready", "error"]
    tech: Literal["ready", "error"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    metadata_database: Literal["ok", "error"]
    indexes: IndexHealth
    router: Literal["configured", "not_configured"]
    request_id: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, object] | None = None


class ExtractedSection(BaseModel):
    order: int
    text: str
    title: str | None = None
    section_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class ChunkCandidateData(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    embedding_text: str
    title: str | None = None
    section_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    checksum_sha256: str
