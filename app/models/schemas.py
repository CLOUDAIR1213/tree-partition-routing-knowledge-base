from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    AnswerSource,
    DecisionSource,
    DocumentStatus,
    Partition,
    ReviewAction,
    RouteKind,
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


class ChangeDocumentPartitionRequest(StrictApiRequest):
    confirmed_partition: Partition
    reviewer_name: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class ReopenDocumentReviewRequest(StrictApiRequest):
    reviewer_name: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class ChatRequest(StrictApiRequest):
    question: str = Field(min_length=1, max_length=2000)
    partition_hint: Partition | None = None
    allow_web_fallback: bool = False


class Citation(BaseModel):
    partition: Partition
    chunk_id: str
    document_id: str
    title: str
    section: str | None
    page_start: int | None
    page_end: int | None


class WebCitation(BaseModel):
    title: str
    url: str
    domain: str


class PartitionTiming(BaseModel):
    partition: Partition
    elapsed_ms: int = Field(ge=0)


class ChatTiming(BaseModel):
    retrieval: list[PartitionTiming]
    router_llm_ms: int | None = Field(ge=0)
    answer_llm_ms: int | None = Field(ge=0)


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
    answer_source: AnswerSource
    searched_partitions: list[Partition]
    citations: list[Citation]
    web_citations: list[WebCitation]
    suggested_partitions: list[Partition]
    request_id: str
    warning: str | None
    timing: ChatTiming = Field(
        default_factory=lambda: ChatTiming(
            retrieval=[],
            router_llm_ms=None,
            answer_llm_ms=None,
        )
    )

    @model_validator(mode="after")
    def validate_route_metadata(self) -> "ChatResponse":
        unique_partitions = set(self.searched_partitions)
        if self.route == RouteName.CLARIFY:
            if self.searched_partitions:
                raise ValueError("clarify response cannot contain searched partitions")
        elif self.route == RouteName.COMPOSITE:
            if len(self.searched_partitions) != 2 or len(unique_partitions) != 2:
                raise ValueError("composite response requires two searched partitions")
        elif self.searched_partitions != [Partition(self.route.value)]:
            raise ValueError("single route must match its searched partition")
        if any(item.partition not in unique_partitions for item in self.citations):
            raise ValueError("citation partition was not searched")
        if self.answerable != (self.answer_source != AnswerSource.NONE):
            raise ValueError("answerable must match answer source")
        if self.answer_source == AnswerSource.INTERNAL:
            if not self.citations or self.web_citations:
                raise ValueError("internal answer requires only internal citations")
        elif self.answer_source == AnswerSource.WEB:
            if self.citations or not self.web_citations:
                raise ValueError("web answer requires only web citations")
        elif self.citations or self.web_citations:
            raise ValueError("unanswerable response cannot contain citations")
        return self


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


class RoutedSubquery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    partition: Partition
    query: str = Field(min_length=1, max_length=2000)


class LLMRoutePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_kind: RouteKind
    subqueries: list[RoutedSubquery]
    needs_clarification: bool
    reason_code: Literal[
        "finance_policy",
        "hr_policy",
        "technical_operation",
        "multi_intent",
        "missing_context",
        "ambiguous_domain",
    ]

    @model_validator(mode="after")
    def validate_route_shape(self) -> "LLMRoutePlan":
        if self.route_kind == RouteKind.SINGLE:
            if len(self.subqueries) != 1 or self.needs_clarification:
                raise ValueError("single route must contain one subquery")
        elif self.route_kind == RouteKind.COMPOSITE:
            partitions = {item.partition for item in self.subqueries}
            if (
                len(self.subqueries) != 2
                or len(partitions) != 2
                or self.needs_clarification
            ):
                raise ValueError(
                    "composite route must contain two distinct partition subqueries"
                )
        elif self.subqueries or not self.needs_clarification:
            raise ValueError("clarify route cannot contain subqueries")
        return self


class RetrievalGroup(BaseModel):
    partition: Partition
    query: str
    hits: list[RetrievalHit]


class LLMAnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(min_length=1)
    citation_chunk_ids: list[str]


class LLMWebAnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(min_length=1)
    citation_urls: list[str]


class UploadDocumentResponse(BaseModel):
    document_id: str
    original_filename: str
    selected_partition: Partition
    confirmed_partition: Partition | None
    status: DocumentStatus
    chunk_count: int
    warnings: list[str]
    parse_quality: "ParseQualityReport"
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
    parse_quality: "ParseQualityReport | None" = None
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
    text: str
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
    parse_quality: "ParseQualityReport | None" = None
    request_id: str


class PartitionSuggestion(BaseModel):
    partition: Partition | None
    confidence: float = Field(ge=0, le=1)
    reasons: list[str]


class ParseQualityReport(BaseModel):
    source_format: Literal["pdf", "docx", "markdown", "text"]
    section_count: int = Field(ge=0)
    titled_section_count: int = Field(ge=0)
    heading_recognition_rate: float = Field(ge=0, le=1)
    page_count: int = Field(ge=0)
    blank_page_numbers: list[int]
    table_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    min_chunk_tokens: int = Field(ge=0)
    max_chunk_tokens: int = Field(ge=0)
    average_chunk_tokens: float = Field(ge=0)
    short_chunk_count: int = Field(ge=0)
    near_limit_chunk_count: int = Field(ge=0)
    over_limit_chunk_count: int = Field(ge=0)
    partition_suggestion: PartitionSuggestion
    warnings: list[str]


class ReviewResponse(BaseModel):
    document_id: str
    selected_partition: Partition
    confirmed_partition: Partition | None
    status: DocumentStatus
    indexed_chunk_count: int
    reviewed_at: datetime
    review_note: str | None
    request_id: str


class ChangeDocumentPartitionResponse(BaseModel):
    document_id: str
    previous_partition: Partition
    confirmed_partition: Partition
    status: DocumentStatus
    reindexed_chunk_count: int
    reviewed_at: datetime
    review_note: str | None
    request_id: str


class ReopenDocumentReviewResponse(BaseModel):
    document_id: str
    previous_partition: Partition
    confirmed_partition: None
    status: DocumentStatus
    removed_indexed_chunk_count: int
    reviewed_at: datetime
    review_note: str | None
    request_id: str


class DeleteDocumentResponse(BaseModel):
    document_id: str
    deleted: Literal[True]
    removed_chunk_count: int
    request_id: str


class IndexLevelHealth(BaseModel):
    document: Literal["ready", "error"]
    section: Literal["ready", "error"]
    chunk: Literal["ready", "error"]


class IndexHealth(BaseModel):
    finance: IndexLevelHealth
    hr: IndexLevelHealth
    tech: IndexLevelHealth


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    metadata_database: Literal["ok", "error"]
    indexes: IndexHealth
    router: Literal["configured", "not_configured"]
    answer: Literal["configured", "extractive", "not_configured"]
    web_search: Literal["configured", "disabled", "not_configured"]
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
