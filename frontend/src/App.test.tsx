import { render, screen, waitFor, within } from "@testing-library/react";
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
      timing: {
        retrieval: [{ partition: "tech", elapsed_ms: 12 }],
        router_llm_ms: null,
        answer_llm_ms: 38,
      },
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

  it("keeps recent conversations flexible and places knowledge above the user", () => {
    renderApp();

    const sidebar = screen.getByRole("complementary", { name: "会话导航" });
    const sidebarQueries = within(sidebar);
    expect(
      sidebarQueries.getByRole("button", { name: "返回问答首页" }),
    ).toHaveTextContent("树索分区知识库");
    const recent = sidebarQueries.getByRole("region", { name: "最近会话" });
    const knowledge = sidebarQueries.getByRole("button", { name: "知识库" });
    const user = sidebarQueries.getByText("演示用户").closest(".sidebar-user");

    expect(user).not.toBeNull();
    expect(
      recent.compareDocumentPosition(knowledge) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      knowledge.compareDocumentPosition(user!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
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
          timing: {
            retrieval: [{ partition: "finance", elapsed_ms: 14 }],
            router_llm_ms: null,
            answer_llm_ms: 42,
          },
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
    expect(screen.getByText("索引 财务 14 ms")).toBeInTheDocument();
    expect(screen.getByText("模型 回答 42 ms")).toBeInTheDocument();
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

  it("renders clarification choices as one group and resends with the chosen partition", async () => {
    vi.spyOn(window, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            code: "ROUTE_CLARIFICATION_REQUIRED",
            answer: "请确认要查询的知识分区。",
            route: "clarify",
            decision_source: "router",
            answerable: false,
            answer_source: "none",
            searched_partitions: [],
            citations: [],
            web_citations: [],
            suggested_partitions: ["finance", "hr", "tech"],
            request_id: "req-clarify",
            warning: null,
            timing: {
              retrieval: [],
              router_llm_ms: 21,
              answer_llm_ms: null,
            },
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(chatResponse("财务分区的回答。", "req-finance"));
    const user = userEvent.setup();
    renderApp();

    await user.type(screen.getByLabelText("输入知识库问题"), "这个流程由哪个部门负责？");
    await user.click(screen.getByRole("button", { name: "发送问题" }));

    const choices = await screen.findByRole("group", { name: "选择检索分区" });
    expect(choices).toHaveClass("clarify-actions");
    expect(screen.getByText("待确认分区")).toBeInTheDocument();
    expect(
      screen.getByText("当前问题可能涉及多个分区，请选择一个最相关的分区继续。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "财务" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "人事" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "技术" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "财务" }));

    await waitFor(() => {
      expect(window.fetch).toHaveBeenLastCalledWith(
        "/api/v1/chat",
        expect.objectContaining({
          body: JSON.stringify({
            question: "这个流程由哪个部门负责？",
            partition_hint: "finance",
            allow_web_fallback: false,
          }),
        }),
      );
    });
  });

  it("renders assistant Markdown and ignores raw HTML", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue(
      chatResponse(
        "## 处理结论\n\n1. **需要登记资产**\n2. 使用 `asset-id` 留存记录\n\n[流程说明](https://example.com/process)\n\n![不应加载](https://example.com/tracker.png)\n\n<script>不应渲染</script>",
        "req-markdown",
      ),
    );
    const user = userEvent.setup();
    renderApp();

    await user.type(screen.getByLabelText("输入知识库问题"), "设备丢失如何处理？");
    await user.click(screen.getByRole("button", { name: "发送问题" }));

    expect(await screen.findByRole("heading", { name: "处理结论" })).toBeInTheDocument();
    expect(screen.getByText("需要登记资产").tagName).toBe("STRONG");
    expect(screen.getByText("asset-id").tagName).toBe("CODE");
    expect(screen.getByRole("link", { name: "流程说明" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(screen.queryByText("不应渲染")).not.toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.queryByRole("img", { name: "不应加载" })).not.toBeInTheDocument();
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
          timing: {
            retrieval: [{ partition: "tech", elapsed_ms: 16 }],
            router_llm_ms: null,
            answer_llm_ms: 51,
          },
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
      parse_quality: {
        source_format: "markdown",
        section_count: 2,
        titled_section_count: 2,
        heading_recognition_rate: 1,
        page_count: 0,
        blank_page_numbers: [],
        table_count: 0,
        chunk_count: 1,
        min_chunk_tokens: 16,
        max_chunk_tokens: 16,
        average_chunk_tokens: 16,
        short_chunk_count: 1,
        near_limit_chunk_count: 0,
        over_limit_chunk_count: 0,
        partition_suggestion: {
          partition: "finance",
          confidence: 0.8,
          reasons: ["命中finance关键词：报销（2）"],
        },
        warnings: ["有 1 个 Chunk 少于最小长度 100。"],
      },
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
          text: "测试 Chunk 内容",
          preview: "测试 Chunk 内容",
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
      parse_quality: null,
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
    expect(screen.getByText("初选分区")).toBeInTheDocument();
    expect(screen.getByText("解析质量")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批准入库" })).toBeDisabled();
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

  it("reconciles a timed-out approval until indexing becomes ready", async () => {
    const documentId = "doc_0123456789abcdef01234567";
    const pendingDetail = {
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
      parse_quality: null,
      request_id: "req-detail",
    };
    const preview = {
      document_id: documentId,
      title: "费用制度",
      selected_partition: "finance",
      confirmed_partition: null,
      status: "pending_review",
      chunk_count: 1,
      items: [{
        chunk_id: "chunk-1",
        chunk_index: 0,
        title: "报销",
        section_path: "费用 > 报销",
        page_start: null,
        page_end: null,
        text: "测试 Chunk 内容",
        preview: "测试 Chunk 内容",
      }],
      total: 1,
      limit: 20,
      offset: 0,
      parse_quality: null,
      request_id: "req-preview",
    };
    let detailReads = 0;
    let reviewWrites = 0;
    vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/preview")) {
        return new Response(JSON.stringify(preview), { status: 200 });
      }
      if (url.endsWith("/review") && init?.method === "POST") {
        reviewWrites += 1;
        throw new DOMException("request timed out", "AbortError");
      }
      detailReads += 1;
      if (detailReads === 1) {
        return new Response(JSON.stringify(pendingDetail), { status: 200 });
      }
      const status = detailReads === 2 ? "indexing" : "ready";
      return new Response(JSON.stringify({
        ...pendingDetail,
        status,
        confirmed_partition: "finance",
        reviewed_at: "2026-09-01T09:00:00Z",
        updated_at: "2026-09-01T09:00:00Z",
      }), { status: 200 });
    });

    const user = userEvent.setup();
    renderApp(`/knowledge/documents/${documentId}`);

    const approveButton = await screen.findByRole("button", { name: "批准入库" });
    await user.click(screen.getByRole("radio", { name: /财务/ }));
    await user.click(approveButton);

    expect(await screen.findByText("入库中")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("正在自动确认入库结果");
    expect(await screen.findByText("已入库", {}, { timeout: 2_500 })).toBeInTheDocument();
    expect(reviewWrites).toBe(1);
    expect(screen.queryByText(/请手动重试/)).not.toBeInTheDocument();
  });

  it("blocks approval when the Chunk preview cannot be loaded", async () => {
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
      parse_quality: null,
      request_id: "req-detail",
    };
    vi.spyOn(window, "fetch").mockImplementation(async (input) => {
      if (String(input).includes("/preview")) {
        return new Response(JSON.stringify({
          code: "PREVIEW_NOT_READY",
          message: "文档尚未产生可预览 Chunk",
          request_id: "req-preview",
          details: null,
        }), { status: 409 });
      }
      return new Response(JSON.stringify(detail), { status: 200 });
    });
    const user = userEvent.setup();
    renderApp(`/knowledge/documents/${documentId}`);

    expect(await screen.findByText(/Chunk 完整预览不可用/)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /财务/ }));
    expect(screen.getByRole("button", { name: "批准入库" })).toBeDisabled();
  });

  it("lists knowledge documents with effective partitions and opens details", async () => {
    const documentId = "doc_0123456789abcdef01234567";
    vi.spyOn(window, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/preview")) {
        return new Response(
          JSON.stringify({
            code: "PREVIEW_NOT_READY",
            message: "文档尚未产生可预览 Chunk",
            request_id: "req-preview",
            details: null,
          }),
          { status: 409 },
        );
      }
      if (url.includes(`/documents/${documentId}`)) {
        return new Response(
          JSON.stringify({
            document_id: documentId,
            original_filename: "vpn-guide.md",
            title: "VPN 访问指南",
            selected_partition: "finance",
            confirmed_partition: "tech",
            status: "ready",
            chunk_count: 2,
            created_at: "2026-09-02T08:00:00Z",
            updated_at: "2026-09-02T08:00:00Z",
            mime_type: "text/markdown",
            size_bytes: 100,
            reviewed_at: "2026-09-02T08:05:00Z",
            review_note: null,
            error_code: null,
            error_message: null,
            request_id: "req-detail",
          }),
          { status: 200 },
        );
      }
      return new Response(
        JSON.stringify({
          items: [
            {
              document_id: documentId,
              original_filename: "vpn-guide.md",
              title: "VPN 访问指南",
              selected_partition: "finance",
              confirmed_partition: "tech",
              status: "ready",
              chunk_count: 2,
              created_at: "2026-09-02T08:00:00Z",
              updated_at: "2026-09-02T08:00:00Z",
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
          request_id: "req-list",
        }),
        { status: 200 },
      );
    });
    const user = userEvent.setup();
    renderApp("/knowledge?status=ready&partition=tech");

    expect(await screen.findByRole("heading", { name: "文档目录" })).toBeInTheDocument();
    expect(await screen.findByText("VPN 访问指南")).toBeInTheDocument();
    expect(screen.getByText("技术", { selector: ".knowledge-partition" })).toBeInTheDocument();
    expect(screen.getByText("已入库", { selector: ".document-status" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "查看 VPN 访问指南 详情" }));
    expect(await screen.findByRole("heading", { name: "VPN 访问指南" })).toBeInTheDocument();
  });

  it("changes a ready document partition after confirmation", async () => {
    const documentId = "doc_0123456789abcdef01234567";
    let partition = "finance";
    const detail = () => ({
      document_id: documentId,
      original_filename: "policy.md",
      title: "分区调整测试",
      selected_partition: "finance",
      confirmed_partition: partition,
      status: "ready",
      chunk_count: 1,
      created_at: "2026-09-01T08:00:00Z",
      updated_at: "2026-09-01T08:00:00Z",
      mime_type: "text/markdown",
      size_bytes: 100,
      reviewed_at: "2026-09-01T08:05:00Z",
      review_note: null,
      error_code: null,
      error_message: null,
      parse_quality: null,
      request_id: "req-detail",
    });
    const fetchSpy = vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/partition") && init?.method === "POST") {
        partition = "tech";
        return new Response(JSON.stringify({
          document_id: documentId,
          previous_partition: "finance",
          confirmed_partition: "tech",
          status: "ready",
          reindexed_chunk_count: 1,
          reviewed_at: "2026-09-01T09:00:00Z",
          review_note: "调整为技术",
          request_id: "req-partition",
        }), { status: 200 });
      }
      if (url.includes("/preview")) {
        return new Response(JSON.stringify({
          document_id: documentId,
          title: "分区调整测试",
          selected_partition: "finance",
          confirmed_partition: partition,
          status: "ready",
          chunk_count: 1,
          items: [{
            chunk_id: "chunk-1",
            chunk_index: 0,
            title: null,
            section_path: null,
            page_start: null,
            page_end: null,
            text: "测试内容",
            preview: "测试内容",
          }],
          total: 1,
          limit: 20,
          offset: 0,
          parse_quality: null,
          request_id: "req-preview",
        }), { status: 200 });
      }
      return new Response(JSON.stringify(detail()), { status: 200 });
    });
    const user = userEvent.setup();
    renderApp(`/knowledge/documents/${documentId}`);

    await screen.findByRole("heading", { name: "分区调整测试" });
    await user.click(screen.getByRole("button", { name: "更改分区" }));
    const dialog = screen.getByRole("dialog", { name: "更改文档分区" });
    await user.click(within(dialog).getByRole("radio", { name: /技术/ }));
    await user.type(within(dialog).getByLabelText(/操作备注/), "调整为技术");
    await user.click(within(dialog).getByRole("button", { name: "确认更改" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const call = fetchSpy.mock.calls.find(([input]) => String(input).endsWith("/partition"));
    expect(call?.[1]?.body).toBe(JSON.stringify({
      confirmed_partition: "tech",
      reviewer_name: null,
      note: "调整为技术",
    }));
    expect(screen.getByText("技术", { selector: ".partition-comparison strong" })).toBeInTheDocument();
  });

  it("reopens a ready document for review", async () => {
    const documentId = "doc_0123456789abcdef01234567";
    let status = "ready";
    let confirmedPartition: string | null = "finance";
    vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/reopen-review") && init?.method === "POST") {
        status = "pending_review";
        confirmedPartition = null;
        return new Response(JSON.stringify({
          document_id: documentId,
          previous_partition: "finance",
          confirmed_partition: null,
          status,
          removed_indexed_chunk_count: 1,
          reviewed_at: "2026-09-01T09:00:00Z",
          review_note: null,
          request_id: "req-reopen",
        }), { status: 200 });
      }
      if (url.includes("/preview")) {
        return new Response(JSON.stringify({
          document_id: documentId,
          title: "重新审核测试",
          selected_partition: "finance",
          confirmed_partition: confirmedPartition,
          status,
          chunk_count: 1,
          items: [{
            chunk_id: "chunk-1",
            chunk_index: 0,
            title: null,
            section_path: null,
            page_start: null,
            page_end: null,
            text: "测试内容",
            preview: "测试内容",
          }],
          total: 1,
          limit: 20,
          offset: 0,
          parse_quality: null,
          request_id: "req-preview",
        }), { status: 200 });
      }
      return new Response(JSON.stringify({
        document_id: documentId,
        original_filename: "policy.md",
        title: "重新审核测试",
        selected_partition: "finance",
        confirmed_partition: confirmedPartition,
        status,
        chunk_count: 1,
        created_at: "2026-09-01T08:00:00Z",
        updated_at: "2026-09-01T08:00:00Z",
        mime_type: "text/markdown",
        size_bytes: 100,
        reviewed_at: "2026-09-01T08:05:00Z",
        review_note: null,
        error_code: null,
        error_message: null,
        parse_quality: null,
        request_id: "req-detail",
      }), { status: 200 });
    });
    const user = userEvent.setup();
    renderApp(`/knowledge/documents/${documentId}`);

    await screen.findByRole("heading", { name: "重新审核测试" });
    await user.click(screen.getByRole("button", { name: "重新审核" }));
    const dialog = screen.getByRole("dialog", { name: "退回重新审核？" });
    await user.click(within(dialog).getByRole("button", { name: "确认重新审核" }));

    expect(await screen.findByText("待审核", { selector: ".document-status" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批准入库" })).toBeDisabled();
  });

  it("deletes a document after destructive confirmation", async () => {
    const documentId = "doc_0123456789abcdef01234567";
    vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith(`/documents/${documentId}`) && init?.method === "DELETE") {
        return new Response(JSON.stringify({
          document_id: documentId,
          deleted: true,
          removed_chunk_count: 1,
          request_id: "req-delete",
        }), { status: 200 });
      }
      if (url.includes("/preview")) {
        return new Response(JSON.stringify({
          document_id: documentId,
          title: "删除测试",
          selected_partition: "finance",
          confirmed_partition: null,
          status: "pending_review",
          chunk_count: 1,
          items: [{
            chunk_id: "chunk-1",
            chunk_index: 0,
            title: null,
            section_path: null,
            page_start: null,
            page_end: null,
            text: "测试内容",
            preview: "测试内容",
          }],
          total: 1,
          limit: 20,
          offset: 0,
          parse_quality: null,
          request_id: "req-preview",
        }), { status: 200 });
      }
      if (
        url.endsWith("/api/v1/documents") ||
        url.includes("/api/v1/documents?")
      ) {
        return new Response(JSON.stringify({
          items: [], total: 0, limit: 20, offset: 0, request_id: "req-list",
        }), { status: 200 });
      }
      return new Response(JSON.stringify({
        document_id: documentId,
        original_filename: "delete.md",
        title: "删除测试",
        selected_partition: "finance",
        confirmed_partition: null,
        status: "pending_review",
        chunk_count: 1,
        created_at: "2026-09-01T08:00:00Z",
        updated_at: "2026-09-01T08:00:00Z",
        mime_type: "text/markdown",
        size_bytes: 100,
        reviewed_at: null,
        review_note: null,
        error_code: null,
        error_message: null,
        parse_quality: null,
        request_id: "req-detail",
      }), { status: 200 });
    });
    const user = userEvent.setup();
    renderApp(`/knowledge/documents/${documentId}`);

    await screen.findByRole("heading", { name: "删除测试" });
    await user.click(screen.getByRole("button", { name: "删除文档" }));
    const dialog = screen.getByRole("dialog", { name: "删除这份文档？" });
    expect(within(dialog).getByText(/无法撤销/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));

    expect(await screen.findByRole("heading", { name: "文档目录" })).toBeInTheDocument();
    expect(await screen.findByText("上传第一份知识文档后，它会显示在这里。")).toBeInTheDocument();
  });
});
