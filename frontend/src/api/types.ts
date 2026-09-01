import type { components } from "./generated";

export type Partition = components["schemas"]["Partition"];
export type DocumentStatus = components["schemas"]["DocumentStatus"];
export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type UploadDocumentResponse = components["schemas"]["UploadDocumentResponse"];
export type DocumentSummaryResponse = components["schemas"]["DocumentSummaryResponse"];
export type DocumentDetailResponse = components["schemas"]["DocumentDetailResponse"];
export type DocumentListResponse = components["schemas"]["DocumentListResponse"];
export type ChunkPreviewItem = components["schemas"]["ChunkPreviewItem"];
export type ChunkPreviewResponse = components["schemas"]["ChunkPreviewResponse"];
export type ReviewRequest = components["schemas"]["ReviewRequest"];
export type ReviewResponse = components["schemas"]["ReviewResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];

export type RouteMode = Partition | null;

export interface UploadDocumentInput {
  file: File;
  partition: Partition;
  title?: string;
}

export interface ListDocumentsParams {
  status?: DocumentStatus;
  limit?: number;
  offset?: number;
}

export interface PreviewParams {
  limit?: number;
  offset?: number;
}

// The current backend OpenAPI does not expose /chat yet. These types keep the
// completed chat UI ready for the backend Phase 3/4 contract.
export interface Citation {
  chunk_id: string;
  document_id: string;
  title: string;
  section: string | null;
  page_start: number | null;
  page_end: number | null;
}

export interface ChatRequest {
  question: string;
  partition_hint: Partition | null;
}

export interface ChatResponse {
  code:
    | "OK"
    | "ROUTE_CLARIFICATION_REQUIRED"
    | "NO_INTERNAL_EVIDENCE"
    | "SENSITIVE_INPUT_BLOCKED";
  answer: string;
  route: Partition | "clarify";
  decision_source: "user_hint" | "llm" | "safety_fallback";
  answerable: boolean;
  citations: Citation[];
  suggested_partitions: Partition[];
  request_id: string;
  warning: string | null;
}
