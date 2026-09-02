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

function seedChatHistory() {
  window.localStorage.setItem(
    "partitioned-kb.chat-session",
    JSON.stringify({
      version: 1,
      activeId: "conversation-1",
      conversations: [
        {
          id: "conversation-1",
          title: "第一条会话",
          messages: [
            { id: "message-1", role: "user", content: "第一条会话" },
          ],
        },
        {
          id: "conversation-2",
          title: "第二条会话",
          messages: [
            { id: "message-2", role: "user", content: "第二条会话" },
          ],
        },
      ],
    }),
  );
}

function chatResponse(answer: string, requestId: string) {
  return new Response(
    JSON.stringify({
      code: "OK",
      answer,
      route: "tech",
      decision_source: "user_hint",
      answerable: true,
      answer_source: "internal",
      searched_partitions: ["tech"],
      citations: [
        {
          partition: "tech",
          chunk_id: `chunk-${requestId}`,
          document_id: "doc-tech",
          title: "技术规范",
          section: "流程",
          page_start: null,
          page_end: null,
        },
      ],
      web_citations: [],
      suggested_partitions: [],
      request_id: requestId,
      warning: null,
    }),
    { status: 200 },
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
          answer_source: "internal",
          searched_partitions: ["finance"],
          citations: [
            {
              partition: "finance",
              chunk_id: "chunk-7",
              document_id: "doc-1",
              title: "费用报销制度",
              section: "差旅报销",
              page_start: 3,
              page_end: 4,
            },
          ],
          web_citations: [],
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
          allow_web_fallback: false,
        }),
      }),
    );
  });

  it("opts in to web fallback and displays public web sources", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "OK",
          answer: "装饰器用于包装函数或类并扩展其行为。",
          route: "tech",
          decision_source: "user_hint",
          answerable: true,
          answer_source: "web",
          searched_partitions: ["tech"],
          citations: [],
          web_citations: [
            {
              title: "Python decorators",
              url: "https://docs.python.org/3/glossary.html#term-decorator",
              domain: "docs.python.org",
            },
          ],
          suggested_partitions: [],
          request_id: "req-web",
          warning: "内部知识库无可用依据，以下内容来自公开网络信息。",
        }),
        { status: 200 },
      ),
    );
    const user = userEvent.setup();
    renderApp();

    expect(screen.queryByText("当前：自动路由")).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "技术" }));
    const webFallbackToggle = screen.getByRole("button", {
      name: "未命中时联网",
    });
    expect(webFallbackToggle).toHaveAttribute("aria-pressed", "false");
    expect(webFallbackToggle).toHaveAttribute("title", "未命中时联网");
    await user.click(webFallbackToggle);
    expect(webFallbackToggle).toHaveAttribute("aria-pressed", "true");
    expect(webFallbackToggle).toHaveAttribute(
      "title",
      "已开启：知识库未命中时联网搜索",
    );
    await user.type(screen.getByLabelText("输入知识库问题"), "Python 装饰器是什么？");
    await user.click(screen.getByRole("button", { name: "发送问题" }));

    expect(await screen.findByText("公开网络信息")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Python decorators/ })).toHaveAttribute(
      "href",
      "https://docs.python.org/3/glossary.html#term-decorator",
    );
    expect(window.fetch).toHaveBeenCalledWith(
      "/api/v1/chat",
      expect.objectContaining({
        body: JSON.stringify({
          question: "Python 装饰器是什么？",
          partition_hint: "tech",
          allow_web_fallback: true,
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
    expect(screen.getByLabelText("输入知识库问题")).toHaveValue("保留这个问题");
  });

  it("keeps an in-flight response bound to its original conversation", async () => {
    seedChatHistory();
    let resolveRequest: (response: Response) => void;
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveRequest = resolve;
    });
    vi.spyOn(window, "fetch").mockReturnValue(pendingResponse);
    const user = userEvent.setup();
    renderApp();

    await user.type(screen.getByLabelText("输入知识库问题"), "会话 A 的问题");
    await user.click(screen.getByRole("button", { name: "发送问题" }));
    expect(screen.getByText("会话 A 的问题", { selector: ".message-body p" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "第二条会话" }));
    expect(screen.getByRole("button", { name: "第二条会话" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    resolveRequest!(chatResponse("会话 A 的回答", "request-a"));
    await waitFor(() => {
      expect(screen.queryByText("会话 A 的回答")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "第一条会话" }));
    expect(await screen.findByText("会话 A 的回答")).toBeInTheDocument();
  });

  it("creates and preserves a new conversation when its first request is in flight", async () => {
    seedChatHistory();
    let resolveRequest: (response: Response) => void;
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveRequest = resolve;
    });
    vi.spyOn(window, "fetch").mockReturnValue(pendingResponse);
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("button", { name: "开启新对话" }));
    await user.type(screen.getByLabelText("输入知识库问题"), "新会话的首个问题");
    await user.click(screen.getByRole("button", { name: "发送问题" }));
    await user.click(screen.getByRole("button", { name: "第二条会话" }));

    resolveRequest!(chatResponse("新会话的回答", "request-new"));
    await waitFor(() => {
      expect(screen.queryByText("新会话的回答")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "新会话的首个问题" }));
    expect(await screen.findByText("新会话的回答")).toBeInTheDocument();
  });

  it("keeps a request isolated through rapid conversation switching", async () => {
    seedChatHistory();
    let resolveRequest: (response: Response) => void;
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveRequest = resolve;
    });
    vi.spyOn(window, "fetch").mockReturnValue(pendingResponse);
    const user = userEvent.setup();
    renderApp();

    await user.type(screen.getByLabelText("输入知识库问题"), "快速切换时的问题");
    await user.click(screen.getByRole("button", { name: "发送问题" }));
    await user.click(screen.getByRole("button", { name: "第二条会话" }));
    await user.click(screen.getByRole("button", { name: "第一条会话" }));
    await user.click(screen.getByRole("button", { name: "第二条会话" }));

    resolveRequest!(chatResponse("快速切换时的回答", "request-rapid"));
    await waitFor(() => {
      expect(screen.queryByText("快速切换时的回答")).not.toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "第一条会话" }));
    expect(await screen.findByText("快速切换时的回答")).toBeInTheDocument();
  });

  it("keeps concurrent requests and their loading states isolated by conversation", async () => {
    seedChatHistory();
    let resolveA: (response: Response) => void;
    let resolveB: (response: Response) => void;
    const pendingA = new Promise<Response>((resolve) => {
      resolveA = resolve;
    });
    const pendingB = new Promise<Response>((resolve) => {
      resolveB = resolve;
    });
    vi.spyOn(window, "fetch")
      .mockReturnValueOnce(pendingA)
      .mockReturnValueOnce(pendingB);
    const user = userEvent.setup();
    renderApp();

    await user.type(screen.getByLabelText("输入知识库问题"), "A 的并发问题");
    await user.click(screen.getByRole("button", { name: "发送问题" }));
    await user.click(screen.getByRole("button", { name: "第二条会话" }));
    await user.type(screen.getByLabelText("输入知识库问题"), "B 的并发问题");
    await user.click(screen.getByRole("button", { name: "发送问题" }));

    resolveB!(chatResponse("B 的并发回答", "request-b"));
    expect(await screen.findByText("B 的并发回答")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "第一条会话" }));
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("B 的并发回答")).not.toBeInTheDocument();

    resolveA!(chatResponse("A 的并发回答", "request-a"));
    expect(await screen.findByText("A 的并发回答")).toBeInTheDocument();
  });

  it("keeps a request failure on the conversation that sent it", async () => {
    seedChatHistory();
    let rejectRequest: (error: Error) => void;
    const pendingResponse = new Promise<Response>((_resolve, reject) => {
      rejectRequest = reject;
    });
    vi.spyOn(window, "fetch")
      .mockReturnValueOnce(pendingResponse)
      .mockResolvedValueOnce(chatResponse("A 的重试回答", "request-a-retry"));
    const user = userEvent.setup();
    renderApp();

    await user.type(screen.getByLabelText("输入知识库问题"), "A 的失败问题");
    await user.click(screen.getByRole("button", { name: "发送问题" }));
    await user.click(screen.getByRole("button", { name: "第二条会话" }));
    rejectRequest!(new TypeError("network failed"));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "第一条会话" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("无法连接知识库服务");
    expect(screen.getByLabelText("输入知识库问题")).toHaveValue("A 的失败问题");

    await user.click(screen.getByRole("button", { name: "发送问题" }));
    expect(await screen.findByText("A 的重试回答")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "第二条会话" }));
    expect(screen.queryByText("A 的重试回答")).not.toBeInTheDocument();
  });

  it("opens a conversation menu with the keyboard and confirms deletion", async () => {
    seedChatHistory();
    const user = userEvent.setup();
    renderApp();
    const moreButton = screen.getByRole("button", {
      name: "更多操作：第一条会话",
    });

    moreButton.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("menu", { name: "第一条会话的操作" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu", { name: "第一条会话的操作" })).not.toBeInTheDocument();

    await user.click(moreButton);
    await user.click(screen.getByRole("menuitem", { name: "删除会话" }));
    expect(screen.getByRole("dialog", { name: "删除这个会话？" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.getByRole("button", { name: "第一条会话" })).toBeInTheDocument();

    await user.click(moreButton);
    await user.click(screen.getByRole("menuitem", { name: "删除会话" }));
    await user.click(screen.getByRole("button", { name: "确认删除" }));

    expect(screen.queryByRole("button", { name: "第一条会话" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "第二条会话" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await waitFor(() => {
      expect(window.localStorage.getItem("partitioned-kb.chat-session")).not.toContain(
        "第一条会话",
      );
    });
  });

  it("requires confirmation before clearing every conversation", async () => {
    seedChatHistory();
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("button", { name: "清空全部会话" }));
    expect(screen.getByRole("dialog", { name: "清空全部会话？" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "第一条会话" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "清空全部会话" }));
    await user.click(screen.getByRole("button", { name: "确认清空" }));

    expect(screen.getByText("提问后，会话将显示在这里")).toBeInTheDocument();
    await waitFor(() => {
      const stored = window.localStorage.getItem("partitioned-kb.chat-session");
      expect(stored).not.toContain("第一条会话");
      expect(stored).not.toContain("第二条会话");
    });
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
