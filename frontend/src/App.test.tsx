import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("application routes and chat", () => {
  afterEach(() => vi.restoreAllMocks());

  it("opens the upload route from the top bar", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("link", { name: "上传知识" }));

    expect(
      screen.getByRole("heading", { name: "上传知识库文档" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /返回问答/ })).toBeInTheDocument();
  });

  it("sends a question and displays citations", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "OK",
          answer: "差旅发票应在行程结束后提交。",
          route: "finance",
          decision_source: "user_hint",
          answerable: true,
          citations: [
            {
              chunk_id: "chunk-7",
              document_id: "doc-1",
              title: "费用报销制度",
              section: "差旅报销",
              page_start: 3,
              page_end: 4,
            },
          ],
          suggested_partitions: [],
          request_id: "req-chat",
          warning: null,
        }),
        { status: 200 },
      ),
    );
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("radio", { name: "财务" }));
    await user.type(screen.getByLabelText("输入知识库问题"), "差旅发票如何报销？");
    await user.click(screen.getByRole("button", { name: "发送问题" }));

    await waitFor(() => {
      expect(screen.getByText("差旅发票应在行程结束后提交。")).toBeInTheDocument();
    });
    expect(screen.getByText("费用报销制度")).toBeInTheDocument();
    expect(screen.getByText(/差旅报销 · 第 3-4 页 · chunk-7/)).toBeInTheDocument();
    expect(window.fetch).toHaveBeenCalledWith(
      "/api/v1/chat",
      expect.objectContaining({
        body: JSON.stringify({
          question: "差旅发票如何报销？",
          partition_hint: "finance",
        }),
      }),
    );
  });

  it("keeps the question when the network request fails", async () => {
    vi.spyOn(window, "fetch").mockRejectedValue(new TypeError("network failed"));
    const user = userEvent.setup();
    renderApp();
    const input = screen.getByLabelText("输入知识库问题");

    await user.type(input, "保留这个问题");
    await user.click(screen.getByRole("button", { name: "发送问题" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("无法连接知识库服务");
    expect(input).toHaveValue("保留这个问题");
  });

  it("requires a valid file and partition before upload", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/knowledge/upload");
    const submit = screen.getByRole("button", { name: "上传并解析" });

    expect(submit).toBeDisabled();
    await user.upload(
      screen.getByLabelText(/选择文件或拖放到这里/),
      new File(["content"], "invalid.exe", { type: "application/octet-stream" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("仅支持 PDF、DOCX、TXT 和 Markdown");
    expect(submit).toBeDisabled();

    await user.upload(
      screen.getByLabelText(/选择文件或拖放到这里/),
      new File(["# Policy"], "policy.md", { type: "text/markdown" }),
    );
    await user.click(screen.getByRole("radio", { name: /财务/ }));
    expect(submit).toBeEnabled();
  });

  it("loads review data and approves with the corrected partition", async () => {
    const documentId = "doc_0123456789abcdef01234567";
    const detail = {
      document_id: documentId,
      original_filename: "policy.md",
      title: "费用制度",
      selected_partition: "finance",
      confirmed_partition: null,
      status: "pending_review",
      chunk_count: 1,
      created_at: "2026-09-01T08:00:00Z",
      updated_at: "2026-09-01T08:00:00Z",
      mime_type: "text/markdown",
      size_bytes: 1024,
      reviewed_at: null,
      review_note: null,
      error_code: null,
      error_message: null,
      request_id: "req-detail",
    };
    const preview = {
      document_id: documentId,
      title: "费用制度",
      selected_partition: "finance",
      confirmed_partition: null,
      status: "pending_review",
      chunk_count: 1,
      items: [
        {
          chunk_id: "chunk-1",
          chunk_index: 0,
          title: "报销",
          section_path: "费用 > 报销",
          page_start: 1,
          page_end: 1,
          preview: "测试 Chunk 内容",
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
      request_id: "req-preview",
    };
    const fetchSpy = vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/review") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            document_id: documentId,
            selected_partition: "finance",
            confirmed_partition: "tech",
            status: "ready",
            indexed_chunk_count: 1,
            reviewed_at: "2026-09-01T09:00:00Z",
            review_note: "调整为技术",
            request_id: "req-review",
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify(url.includes("preview") ? preview : detail), {
        status: 200,
      });
    });
    const user = userEvent.setup();
    renderApp(`/knowledge/review/${documentId}`);

    expect(await screen.findByRole("heading", { name: "费用制度" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /技术/ }));
    await user.type(screen.getByLabelText(/审核备注/), "调整为技术");
    await user.click(screen.getByRole("button", { name: "批准入库" }));

    await screen.findByText("已入库");
    const reviewCall = fetchSpy.mock.calls.find(([input]) => String(input).endsWith("/review"));
    expect(reviewCall?.[1]?.body).toBe(
      JSON.stringify({
        action: "approve",
        confirmed_partition: "tech",
        reviewer_name: null,
        note: "调整为技术",
      }),
    );
  });
});
