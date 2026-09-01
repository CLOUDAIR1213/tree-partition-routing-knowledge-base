import { apiFetch, documentsApi, knowledgeApi } from "./client";

const successResponse = {
  code: "OK",
  answer: "请按费用制度提交发票。",
  route: "finance",
  decision_source: "llm",
  answerable: true,
  citations: [],
  suggested_partitions: [],
  request_id: "req-success",
  warning: null,
};

describe("API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts snake_case chat fields as JSON", async () => {
    const fetchSpy = vi
      .spyOn(window, "fetch")
      .mockResolvedValue(new Response(JSON.stringify(successResponse), { status: 200 }));

    const response = await knowledgeApi.chat({
      question: "如何报销？",
      partition_hint: null,
    });

    expect(response.request_id).toBe("req-success");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/chat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ question: "如何报销？", partition_hint: null }),
        headers: expect.any(Headers),
      }),
    );
    const headers = fetchSpy.mock.calls[0][1]?.headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("does not set a multipart content type for FormData", async () => {
    const fetchSpy = vi
      .spyOn(window, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 201 }));
    const body = new FormData();
    body.append("partition", "finance");

    await apiFetch("/api/v1/documents", { method: "POST", body });

    const headers = fetchSpy.mock.calls[0][1]?.headers as Headers;
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("preserves typed backend errors and request ids", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "SERVICE_UNAVAILABLE",
          message: "服务暂不可用",
          request_id: "req-error",
          details: null,
        }),
        { status: 503 },
      ),
    );

    await expect(apiFetch("/api/v1/health")).rejects.toMatchObject({
      status: 503,
      body: { request_id: "req-error" },
    });
  });

  it("keeps HTTP 200 clarification as a business response", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ...successResponse,
          code: "ROUTE_CLARIFICATION_REQUIRED",
          answer: "请选择分区",
          route: "clarify",
          answerable: false,
          suggested_partitions: ["finance", "hr", "tech"],
        }),
        { status: 200 },
      ),
    );

    const response = await knowledgeApi.chat({
      question: "制度是什么？",
      partition_hint: null,
    });

    expect(response.code).toBe("ROUTE_CLARIFICATION_REQUIRED");
    expect(response.suggested_partitions).toEqual(["finance", "hr", "tech"]);
  });

  it("uploads the exact multipart fields without overriding the boundary", async () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          document_id: "doc_0123456789abcdef01234567",
          original_filename: "policy.md",
          selected_partition: "finance",
          confirmed_partition: null,
          status: "pending_review",
          chunk_count: 2,
          warnings: [],
          request_id: "req-upload",
        }),
        { status: 201 },
      ),
    );
    const file = new File(["# Policy"], "policy.md", { type: "text/markdown" });

    const result = await documentsApi.upload({
      file,
      partition: "finance",
      title: "Policy",
    });

    expect(result.status).toBe("pending_review");
    const request = fetchSpy.mock.calls[0][1];
    const body = request?.body as FormData;
    const headers = request?.headers as Headers;
    expect(body.get("file")).toBe(file);
    expect(body.get("partition")).toBe("finance");
    expect(body.get("title")).toBe("Policy");
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("uses backend pagination and review field names", async () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          document_id: "doc_0123456789abcdef01234567",
          selected_partition: "finance",
          confirmed_partition: "tech",
          status: "ready",
          indexed_chunk_count: 3,
          reviewed_at: "2026-09-01T08:00:00Z",
          review_note: null,
          request_id: "req-review",
        }),
        { status: 200 },
      ),
    );

    await documentsApi.review("doc_0123456789abcdef01234567", {
      action: "approve",
      confirmed_partition: "tech",
      reviewer_name: null,
      note: null,
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/documents/doc_0123456789abcdef01234567/review",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          action: "approve",
          confirmed_partition: "tech",
          reviewer_name: null,
          note: null,
        }),
      }),
    );
  });
});
