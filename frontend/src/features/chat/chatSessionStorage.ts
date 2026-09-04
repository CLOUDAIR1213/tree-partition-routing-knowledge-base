import type { Citation, Partition, WebCitation } from "../../api/types";
import type { ChatMessage, Conversation } from "./ChatSessionContext";

export const CHAT_SESSION_STORAGE_KEY = "partitioned-kb.chat-session";

const STORAGE_VERSION = 1;
const PARTITIONS = new Set<Partition>(["finance", "hr", "tech"]);
const ROUTES = new Set(["finance", "hr", "tech", "composite", "clarify"]);
const RESPONSE_CODES = new Set([
  "OK",
  "ROUTE_CLARIFICATION_REQUIRED",
  "NO_INTERNAL_EVIDENCE",
  "SENSITIVE_INPUT_BLOCKED",
]);
const ANSWER_SOURCES = new Set(["internal", "web", "none"]);

export interface ChatSessionSnapshot {
  conversations: Conversation[];
  activeId: string;
}

interface StoredChatSession extends ChatSessionSnapshot {
  version: typeof STORAGE_VERSION;
}

export function createEmptyChatSession(): ChatSessionSnapshot {
  return {
    conversations: [{ id: "conversation-0", title: "新对话", messages: [] }],
    activeId: "conversation-0",
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isPartition(value: unknown): value is Partition {
  return typeof value === "string" && PARTITIONS.has(value as Partition);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isCitation(value: unknown): value is Citation {
  return (
    isRecord(value) &&
    isPartition(value.partition) &&
    typeof value.chunk_id === "string" &&
    typeof value.document_id === "string" &&
    typeof value.title === "string" &&
    isNullableString(value.section) &&
    isNullableNumber(value.page_start) &&
    isNullableNumber(value.page_end)
  );
}

function isWebCitation(value: unknown): value is WebCitation {
  return (
    isRecord(value) &&
    typeof value.title === "string" &&
    typeof value.url === "string" &&
    typeof value.domain === "string"
  );
}

function isPartitionArray(value: unknown): value is Partition[] {
  return Array.isArray(value) && value.every(isPartition);
}

function isElapsedMilliseconds(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isChatTiming(value: unknown): value is NonNullable<ChatMessage["timing"]> {
  if (!isRecord(value) || !Array.isArray(value.retrieval)) return false;
  return (
    value.retrieval.every(
      (item) =>
        isRecord(item) &&
        isPartition(item.partition) &&
        isElapsedMilliseconds(item.elapsed_ms),
    ) &&
    (value.router_llm_ms === null ||
      isElapsedMilliseconds(value.router_llm_ms)) &&
    (value.answer_llm_ms === null ||
      isElapsedMilliseconds(value.answer_llm_ms))
  );
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (
    !isRecord(value) ||
    typeof value.id !== "string" ||
    (value.role !== "user" && value.role !== "assistant") ||
    typeof value.content !== "string"
  ) {
    return false;
  }

  return (
    (value.citations === undefined ||
      (Array.isArray(value.citations) && value.citations.every(isCitation))) &&
    (value.webCitations === undefined ||
      (Array.isArray(value.webCitations) &&
        value.webCitations.every(isWebCitation))) &&
    (value.code === undefined || RESPONSE_CODES.has(String(value.code))) &&
    (value.answerSource === undefined ||
      ANSWER_SOURCES.has(String(value.answerSource))) &&
    (value.route === undefined || ROUTES.has(String(value.route))) &&
    (value.searchedPartitions === undefined ||
      isPartitionArray(value.searchedPartitions)) &&
    (value.suggestedPartitions === undefined ||
      isPartitionArray(value.suggestedPartitions)) &&
    (value.requestId === undefined || typeof value.requestId === "string") &&
    (value.warning === undefined || isNullableString(value.warning)) &&
    (value.timing === undefined || isChatTiming(value.timing))
  );
}

function isConversation(value: unknown): value is Conversation {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    Array.isArray(value.messages) &&
    value.messages.every(isChatMessage)
  );
}

function isStoredChatSession(value: unknown): value is StoredChatSession {
  return (
    isRecord(value) &&
    value.version === STORAGE_VERSION &&
    typeof value.activeId === "string" &&
    Array.isArray(value.conversations) &&
    value.conversations.length > 0 &&
    value.conversations.every(isConversation) &&
    value.conversations.some(
      (conversation) => conversation.id === value.activeId,
    )
  );
}

export function loadChatSession(): ChatSessionSnapshot {
  try {
    const stored = window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY);
    if (!stored) return createEmptyChatSession();
    const parsed: unknown = JSON.parse(stored);
    if (!isStoredChatSession(parsed)) return createEmptyChatSession();
    return {
      conversations: parsed.conversations,
      activeId: parsed.activeId,
    };
  } catch {
    return createEmptyChatSession();
  }
}

export function saveChatSession(snapshot: ChatSessionSnapshot) {
  const stored: StoredChatSession = {
    version: STORAGE_VERSION,
    ...snapshot,
  };
  try {
    window.localStorage.setItem(
      CHAT_SESSION_STORAGE_KEY,
      JSON.stringify(stored),
    );
  } catch {
    // Browsing modes and storage quotas can disable local persistence.
  }
}
