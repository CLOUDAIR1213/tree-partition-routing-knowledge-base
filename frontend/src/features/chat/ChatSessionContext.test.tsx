import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ChatSessionProvider,
  type Conversation,
  useChatSession,
} from "./ChatSessionContext";
import { CHAT_SESSION_STORAGE_KEY } from "./chatSessionStorage";

function SessionHarness() {
  const {
    conversations,
    activeConversation,
    appendMessage,
    newConversation,
    deleteConversation,
    clearConversations,
  } = useChatSession();
  return (
    <div>
      <p data-testid="conversation-title">{activeConversation.title}</p>
      <p data-testid="conversation-count">{conversations.length}</p>
      {activeConversation.messages.map((message) => (
        <p key={message.id}>{message.content}</p>
      ))}
      {conversations.map((conversation) => (
        <button
          key={conversation.id}
          onClick={() => deleteConversation(conversation.id)}
          type="button"
        >
          删除状态 {conversation.title}
        </button>
      ))}
      <button
        onClick={() =>
          appendMessage(activeConversation.id, {
            id: "message-1",
            role: "user",
            content: "需要跨刷新保留的问题",
          })
        }
        type="button"
      >
        添加消息
      </button>
      <button onClick={clearConversations} type="button">
        清空状态
      </button>
      <button onClick={newConversation} type="button">
        新建状态
      </button>
    </div>
  );
}

function storedConversation(id: string, title: string): Conversation {
  return {
    id,
    title,
    messages: [{ id: `message-${id}`, role: "user", content: title }],
  };
}

function storeSession(
  conversations: ReturnType<typeof storedConversation>[],
  activeId: string,
) {
  window.localStorage.setItem(
    CHAT_SESSION_STORAGE_KEY,
    JSON.stringify({ version: 1, conversations, activeId }),
  );
}

describe("ChatSessionProvider", () => {
  it("restores conversations from local storage after remounting", async () => {
    const user = userEvent.setup();
    const firstRender = render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );

    await user.click(screen.getByRole("button", { name: "添加消息" }));
    await waitFor(() => {
      expect(window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY)).toContain(
        "需要跨刷新保留的问题",
      );
    });
    firstRender.unmount();

    render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );

    expect(screen.getAllByText("需要跨刷新保留的问题")).toHaveLength(2);
    expect(screen.getByTestId("conversation-title")).toHaveTextContent(
      "需要跨刷新保留的问题",
    );
  });

  it("falls back to an empty conversation for invalid stored data", () => {
    window.localStorage.setItem(CHAT_SESSION_STORAGE_KEY, "{invalid-json");

    render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );

    expect(screen.getByText("新对话")).toBeInTheDocument();
  });

  it("falls back to an empty conversation for invalid stored timing", () => {
    storeSession(
      [
        {
          id: "conversation-invalid-timing",
          title: "损坏计时",
          messages: [
            {
              id: "message-invalid-timing",
              role: "assistant",
              content: "不应恢复",
              timing: {
                retrieval: [{ partition: "tech", elapsed_ms: -1 }],
                router_llm_ms: null,
                answer_llm_ms: null,
              },
            },
          ],
        },
      ],
      "conversation-invalid-timing",
    );

    render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );

    expect(screen.getByText("新对话")).toBeInTheDocument();
  });

  it("does not accumulate hidden empty conversations", async () => {
    const user = userEvent.setup();
    render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );

    await user.click(screen.getByRole("button", { name: "新建状态" }));
    await user.click(screen.getByRole("button", { name: "新建状态" }));

    expect(screen.getByTestId("conversation-title")).toHaveTextContent("新对话");
    expect(screen.getByTestId("conversation-count")).toHaveTextContent("1");
  });

  it("selects the next adjacent conversation after deleting the active one", async () => {
    storeSession(
      [
        storedConversation("conversation-1", "第一条会话"),
        storedConversation("conversation-2", "第二条会话"),
        storedConversation("conversation-3", "第三条会话"),
      ],
      "conversation-2",
    );
    const user = userEvent.setup();
    render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );

    await user.click(screen.getByRole("button", { name: "删除状态 第二条会话" }));

    expect(screen.getByTestId("conversation-title")).toHaveTextContent("第三条会话");
    expect(screen.getByTestId("conversation-count")).toHaveTextContent("2");
    expect(screen.queryByRole("button", { name: "删除状态 第二条会话" })).not.toBeInTheDocument();
  });

  it("creates an empty conversation after deleting the only conversation", async () => {
    storeSession(
      [storedConversation("conversation-4", "唯一会话")],
      "conversation-4",
    );
    const user = userEvent.setup();
    render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );

    await user.click(screen.getByRole("button", { name: "删除状态 唯一会话" }));

    expect(screen.getByTestId("conversation-title")).toHaveTextContent("新对话");
    expect(screen.getByTestId("conversation-count")).toHaveTextContent("1");
  });

  it("clears every conversation and persists the empty replacement", async () => {
    storeSession(
      [
        storedConversation("conversation-5", "待清空一"),
        storedConversation("conversation-6", "待清空二"),
      ],
      "conversation-5",
    );
    const user = userEvent.setup();
    const firstRender = render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );

    await user.click(screen.getByRole("button", { name: "清空状态" }));
    await waitFor(() => {
      const stored = window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY);
      expect(stored).not.toContain("待清空一");
      expect(stored).not.toContain("待清空二");
    });
    firstRender.unmount();

    render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );
    expect(screen.getByTestId("conversation-title")).toHaveTextContent("新对话");
    expect(screen.getByTestId("conversation-count")).toHaveTextContent("1");
  });

  it("does not restore a deleted inactive conversation after remounting", async () => {
    storeSession(
      [
        storedConversation("conversation-7", "保留会话"),
        storedConversation("conversation-8", "删除会话"),
      ],
      "conversation-7",
    );
    const user = userEvent.setup();
    const firstRender = render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );

    await user.click(screen.getByRole("button", { name: "删除状态 删除会话" }));
    await waitFor(() => {
      expect(window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY)).not.toContain(
        "删除会话",
      );
    });
    firstRender.unmount();

    render(
      <ChatSessionProvider>
        <SessionHarness />
      </ChatSessionProvider>,
    );
    expect(screen.getByTestId("conversation-title")).toHaveTextContent("保留会话");
    expect(screen.queryByRole("button", { name: "删除状态 删除会话" })).not.toBeInTheDocument();
  });
});
