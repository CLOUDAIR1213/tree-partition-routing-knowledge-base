import {
  createContext,
  type ReactNode,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ChatResponse, Citation, Partition } from "../../api/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  code?: ChatResponse["code"];
  route?: Partition | "clarify";
  suggestedPartitions?: Partition[];
  requestId?: string;
  warning?: string | null;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
}

interface ChatSessionValue {
  conversations: Conversation[];
  activeConversation: Conversation;
  newConversation: () => void;
  selectConversation: (id: string) => void;
  appendMessage: (message: ChatMessage) => void;
}

const ChatSessionContext = createContext<ChatSessionValue | null>(null);

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const sequence = useRef(1);
  const [conversations, setConversations] = useState<Conversation[]>([
    { id: "conversation-0", title: "新对话", messages: [] },
  ]);
  const [activeId, setActiveId] = useState("conversation-0");

  const activeConversation =
    conversations.find((conversation) => conversation.id === activeId) ??
    conversations[0];

  const value = useMemo<ChatSessionValue>(
    () => ({
      conversations,
      activeConversation,
      newConversation() {
        const id = `conversation-${sequence.current++}`;
        setConversations((current) => [
          ...current,
          { id, title: "新对话", messages: [] },
        ]);
        setActiveId(id);
      },
      selectConversation: setActiveId,
      appendMessage(message) {
        setConversations((current) =>
          current.map((conversation) => {
            if (conversation.id !== activeId) return conversation;
            const isFirstQuestion =
              message.role === "user" && conversation.messages.length === 0;
            return {
              ...conversation,
              title: isFirstQuestion
                ? message.content.trim().slice(0, 24)
                : conversation.title,
              messages: [...conversation.messages, message],
            };
          }),
        );
      },
    }),
    [activeConversation, activeId, conversations],
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
