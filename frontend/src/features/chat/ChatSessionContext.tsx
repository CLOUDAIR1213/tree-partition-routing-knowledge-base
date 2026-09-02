import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  ChatResponse,
  Citation,
  Partition,
  WebCitation,
} from "../../api/types";
import {
  loadChatSession,
  saveChatSession,
} from "./chatSessionStorage";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  webCitations?: WebCitation[];
  code?: ChatResponse["code"];
  answerSource?: ChatResponse["answer_source"];
  route?: ChatResponse["route"];
  searchedPartitions?: Partition[];
  suggestedPartitions?: Partition[];
  requestId?: string;
  warning?: string | null;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
}

export interface ConversationRuntime {
  pendingRequestIds: string[];
  error: string | null;
  retryQuestion: string | null;
}

interface ChatSessionValue {
  conversations: Conversation[];
  activeConversation: Conversation;
  newConversation: () => void;
  selectConversation: (id: string) => void;
  deleteConversation: (id: string) => void;
  clearConversations: () => void;
  appendMessage: (conversationId: string, message: ChatMessage) => void;
  startRequest: (conversationId: string, requestId: string) => void;
  finishRequest: (conversationId: string, requestId: string) => void;
  failRequest: (
    conversationId: string,
    requestId: string,
    error: string,
    retryQuestion: string,
  ) => void;
  getConversationRuntime: (conversationId: string) => ConversationRuntime;
}

const ChatSessionContext = createContext<ChatSessionValue | null>(null);
const idleRuntime: ConversationRuntime = {
  pendingRequestIds: [],
  error: null,
  retryQuestion: null,
};

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState(loadChatSession);
  const [runtimeByConversation, setRuntimeByConversation] = useState<
    Record<string, ConversationRuntime>
  >({});
  const sequence = useRef(
    session.conversations.reduce((highest, conversation) => {
      const match = /^conversation-(\d+)$/.exec(conversation.id);
      return match ? Math.max(highest, Number(match[1]) + 1) : highest;
    }, 1),
  );
  const { conversations, activeId } = session;

  const activeConversation =
    conversations.find((conversation) => conversation.id === activeId) ??
    conversations[0];

  useEffect(() => {
    saveChatSession(session);
  }, [session]);

  function createConversation(): Conversation {
    return {
      id: `conversation-${sequence.current++}`,
      title: "新对话",
      messages: [],
    };
  }

  const value = useMemo<ChatSessionValue>(
    () => ({
      conversations,
      activeConversation,
      newConversation() {
        const conversation = createConversation();
        setSession((current) => ({
          conversations: [
            ...current.conversations.filter((item) => item.messages.length > 0),
            conversation,
          ],
          activeId: conversation.id,
        }));
      },
      selectConversation(id) {
        setSession((current) =>
          current.conversations.some((conversation) => conversation.id === id)
            ? { ...current, activeId: id }
            : current,
        );
      },
      deleteConversation(id) {
        const replacement = createConversation();
        setRuntimeByConversation((current) => {
          const { [id]: _deleted, ...remaining } = current;
          return remaining;
        });
        setSession((current) => {
          const deletedIndex = current.conversations.findIndex(
            (conversation) => conversation.id === id,
          );
          if (deletedIndex < 0) return current;

          const remaining = current.conversations.filter(
            (conversation) => conversation.id !== id,
          );
          if (!remaining.length) {
            return {
              conversations: [replacement],
              activeId: replacement.id,
            };
          }

          const nextActiveId =
            current.activeId === id
              ? remaining[Math.min(deletedIndex, remaining.length - 1)].id
              : current.activeId;
          return { conversations: remaining, activeId: nextActiveId };
        });
      },
      clearConversations() {
        const replacement = createConversation();
        setRuntimeByConversation({});
        setSession({
          conversations: [replacement],
          activeId: replacement.id,
        });
      },
      appendMessage(conversationId, message) {
        setSession((current) => {
          let updated = false;
          const conversations = current.conversations.map((conversation) => {
            if (conversation.id !== conversationId) return conversation;
            updated = true;
            const isFirstQuestion =
              message.role === "user" && conversation.messages.length === 0;
            return {
              ...conversation,
              title: isFirstQuestion
                ? message.content.trim().slice(0, 24)
                : conversation.title,
              messages: [...conversation.messages, message],
            };
          });
          return updated ? { ...current, conversations } : current;
        });
      },
      startRequest(conversationId, requestId) {
        setRuntimeByConversation((current) => {
          const runtime = current[conversationId] ?? idleRuntime;
          return {
            ...current,
            [conversationId]: {
              pendingRequestIds: [...runtime.pendingRequestIds, requestId],
              error: null,
              retryQuestion: null,
            },
          };
        });
      },
      finishRequest(conversationId, requestId) {
        setRuntimeByConversation((current) => {
          const runtime = current[conversationId];
          if (!runtime) return current;
          return {
            ...current,
            [conversationId]: {
              ...runtime,
              pendingRequestIds: runtime.pendingRequestIds.filter(
                (id) => id !== requestId,
              ),
            },
          };
        });
      },
      failRequest(conversationId, requestId, error, retryQuestion) {
        setRuntimeByConversation((current) => {
          const runtime = current[conversationId];
          if (!runtime) return current;
          return {
            ...current,
            [conversationId]: {
              pendingRequestIds: runtime.pendingRequestIds.filter(
                (id) => id !== requestId,
              ),
              error,
              retryQuestion,
            },
          };
        });
      },
      getConversationRuntime(conversationId) {
        return runtimeByConversation[conversationId] ?? idleRuntime;
      },
    }),
    [activeConversation, conversations, runtimeByConversation],
  );

  return (
    <ChatSessionContext.Provider value={value}>
      {children}
    </ChatSessionContext.Provider>
  );
}

export function useChatSession() {
  const context = useContext(ChatSessionContext);
  if (!context) {
    throw new Error("useChatSession must be used within ChatSessionProvider");
  }
  return context;
}
