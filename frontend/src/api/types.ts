import type { components } from "./generated";

export type Partition = components["schemas"]["Partition"];
export type RouteName = components["schemas"]["RouteName"];
export type DocumentStatus = components["schemas"]["DocumentStatus"];
export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type UploadDocumentResponse = components["schemas"]["UploadDocumentResponse"];
export type DocumentSummaryResponse = components["schemas"]["DocumentSummaryResponse"];
export type DocumentDetailResponse = components["schemas"]["DocumentDetailResponse"];
export type DocumentListResponse = components["schemas"]["DocumentListResponse"];
export type ChunkPreviewItem = components["schemas"]["ChunkPreviewItem"];
export type ChunkPreviewResponse = components["schemas"]["ChunkPreviewResponse"];
export type ParseQualityReport = components["schemas"]["ParseQualityReport"];
export type PartitionSuggestion = components["schemas"]["PartitionSuggestion"];
export type ReviewRequest = components["schemas"]["ReviewRequest"];
export type ReviewResponse = components["schemas"]["ReviewResponse"];
export type ChangeDocumentPartitionRequest = components["schemas"]["ChangeDocumentPartitionRequest"];
export type ChangeDocumentPartitionResponse = components["schemas"]["ChangeDocumentPartitionResponse"];
export type ReopenDocumentReviewRequest = components["schemas"]["ReopenDocumentReviewRequest"];
export type ReopenDocumentReviewResponse = components["schemas"]["ReopenDocumentReviewResponse"];
export type DeleteDocumentResponse = components["schemas"]["DeleteDocumentResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type Citation = components["schemas"]["Citation"];
export type WebCitation = components["schemas"]["WebCitation"];
export type AnswerSource = components["schemas"]["AnswerSource"];
export type ChatRequest = components["schemas"]["ChatRequest"];
export type ChatResponse = components["schemas"]["ChatResponse"];

export type RouteMode = Partition | null;

export interface UploadDocumentInput {
  file: File;
  partition: Partition;
  title?: string;
}

export interface ListDocumentsParams {
  status?: DocumentStatus;
  partition?: Partition;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface PreviewParams {
  limit?: number;
  offset?: number;
}
