import type {
  ChatRequest,
  ChatResponse,
  ChunkPreviewResponse,
  DocumentDetailResponse,
  DocumentListResponse,
  ErrorResponse,
  HealthResponse,
  ListDocumentsParams,
  Partition,
  PreviewParams,
  ReviewRequest,
  ReviewResponse,
  UploadDocumentInput,
  UploadDocumentResponse,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const DEFAULT_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ErrorResponse,
  ) {
    super(body.message);
    this.name = "ApiError";
  }
}

export class ApiTimeoutError extends Error {
  constructor() {
    super("请求超时，请稍后重试");
    this.name = "ApiTimeoutError";
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  if (!value || typeof value !== "object") return false;
  const body = value as Record<string, unknown>;
  return (
    typeof body.code === "string" &&
    typeof body.message === "string" &&
    typeof body.request_id === "string" &&
    (body.details === undefined ||
      body.details === null ||
      typeof body.details === "object")
  );
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const headers = new Headers(init.headers);

  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
    const payload: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      const body: ErrorResponse = isErrorResponse(payload)
        ? payload
        : {
            code: "INVALID_ERROR_RESPONSE",
            message: "服务返回了无法识别的错误",
            request_id: response.headers.get("x-request-id") ?? "unknown",
            details: null,
          };
      throw new ApiError(response.status, body);
    }

    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiTimeoutError();
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

const validCodes = new Set([
  "OK",
  "ROUTE_CLARIFICATION_REQUIRED",
  "NO_INTERNAL_EVIDENCE",
  "SENSITIVE_INPUT_BLOCKED",
]);
const validRoutes = new Set<Partition | "clarify">([
  "finance",
  "hr",
  "tech",
  "clarify",
]);

function assertChatContract(response: ChatResponse): ChatResponse {
  if (!validCodes.has(response.code) || !validRoutes.has(response.route)) {
    throw new Error("后端返回了前端尚未支持的问答状态");
  }
  return response;
}

export const knowledgeApi = {
  async chat(input: ChatRequest): Promise<ChatResponse> {
    const response = await apiFetch<ChatResponse>("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(input),
    });
    return assertChatContract(response);
  },
};

function queryString(params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) query.set(key, String(value));
  });
  const value = query.toString();
  return value ? `?${value}` : "";
}

export const documentsApi = {
  upload(input: UploadDocumentInput): Promise<UploadDocumentResponse> {
    const body = new FormData();
    body.append("file", input.file);
    body.append("partition", input.partition);
    if (input.title) body.append("title", input.title);
    return apiFetch<UploadDocumentResponse>(
      "/api/v1/documents",
      { method: "POST", body },
      120_000,
    );
  },

  list(params: ListDocumentsParams = {}): Promise<DocumentListResponse> {
    return apiFetch<DocumentListResponse>(
      `/api/v1/documents${queryString({
        status: params.status,
        limit: params.limit,
        offset: params.offset,
      })}`,
    );
  },

  get(documentId: string): Promise<DocumentDetailResponse> {
    return apiFetch<DocumentDetailResponse>(
      `/api/v1/documents/${encodeURIComponent(documentId)}`,
    );
  },

  preview(
    documentId: string,
    params: PreviewParams = {},
  ): Promise<ChunkPreviewResponse> {
    return apiFetch<ChunkPreviewResponse>(
      `/api/v1/documents/${encodeURIComponent(documentId)}/preview${queryString({
        limit: params.limit,
        offset: params.offset,
      })}`,
    );
  },

  review(documentId: string, input: ReviewRequest): Promise<ReviewResponse> {
    return apiFetch<ReviewResponse>(
      `/api/v1/documents/${encodeURIComponent(documentId)}/review`,
      { method: "POST", body: JSON.stringify(input) },
      120_000,
    );
  },
};

export const systemApi = {
  health(): Promise<HealthResponse> {
    return apiFetch<HealthResponse>("/api/v1/health");
  },
};
