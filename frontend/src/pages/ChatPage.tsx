import { Database } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError, ApiTimeoutError, knowledgeApi } from "../api/client";
import type { ChatResponse, Partition, RouteMode } from "../api/types";
import { PartitionSelector } from "../components/PartitionSelector";
import { ChatComposer } from "../features/chat/ChatComposer";
import {
  type ChatMessage,
  useChatSession,
} from "../features/chat/ChatSessionContext";
import { MessageList } from "../features/chat/MessageList";

let messageSequence = 0;

function messageId() {
  return `message-${Date.now()}-${messageSequence++}`;
}

function responseText(response: ChatResponse) {
  if (response.code === "ROUTE_CLARIFICATION_REQUIRED") {
    return "当前问题可能涉及多个分区，请选择一个最相关的分区继续。";
  }
  if (response.answer) return response.answer;
  switch (response.code) {
    case "NO_INTERNAL_EVIDENCE":
      return "当前内部知识库中没有足够依据回答这个问题。";
    case "SENSITIVE_INPUT_BLOCKED":
      return "问题中可能包含敏感信息。请删除账号、密钥或个人敏感值后重新提交。";
    default:
      return "知识库暂时无法生成回答。";
  }
}

function errorText(error: unknown) {
  if (error instanceof ApiTimeoutError) return error.message;
  if (error instanceof ApiError) {
    switch (error.body.code) {
      case "SENSITIVE_INPUT_BLOCKED":
        return "问题中可能包含敏感信息，请删除敏感值后重试。";
      case "LLM_TIMEOUT":
        return "知识检索超时，问题已保留，请手动重试。";
      case "SERVICE_UNAVAILABLE":
        return "知识库服务暂不可用，请稍后重试。";
      default:
        return `${error.body.message}（请求 ID：${error.body.request_id}）`;
    }
  }
  return "无法连接知识库服务，请检查服务状态后重试。";
}

function isPartition(value: string | null): value is Partition {
  return value === "finance" || value === "hr" || value === "tech";
}

export function ChatPage() {
  const [searchParams] = useSearchParams();
  const hintedPartition = searchParams.get("partition");
  const [routeMode, setRouteMode] = useState<RouteMode>(
    isPartition(hintedPartition) ? hintedPartition : null,
  );
  const [allowWebFallback, setAllowWebFallback] = useState(false);
  const {
    activeConversation,
    appendMessage,
    startRequest,
    finishRequest,
    failRequest,
    getConversationRuntime,
  } = useChatSession();
  const runtime = getConversationRuntime(activeConversation.id);
  const loading = runtime.pendingRequestIds.length > 0;
  const hasMessages = activeConversation.messages.length > 0;

  useEffect(() => {
    if (isPartition(hintedPartition)) setRouteMode(hintedPartition);
  }, [hintedPartition]);

  async function ask(question: string, partition = routeMode): Promise<boolean> {
    if (loading) return false;
    const requestContext = {
      requestId: messageId(),
      conversationId: activeConversation.id,
      userMessageId: messageId(),
      assistantMessageId: messageId(),
    };
    appendMessage(requestContext.conversationId, {
      id: requestContext.userMessageId,
      role: "user",
      content: question,
    });
    startRequest(requestContext.conversationId, requestContext.requestId);

    try {
      const response = await knowledgeApi.chat({
        question,
        partition_hint: partition,
        allow_web_fallback: allowWebFallback,
      });
      const assistantMessage: ChatMessage = {
        id: requestContext.assistantMessageId,
        role: "assistant",
        content: responseText(response),
        citations: response.citations,
        webCitations: response.web_citations,
        code: response.code,
        answerSource: response.answer_source,
        route: response.route,
        searchedPartitions: response.searched_partitions,
        suggestedPartitions: response.suggested_partitions,
        requestId: response.request_id,
        warning: response.warning,
        timing: response.timing,
      };
      appendMessage(requestContext.conversationId, assistantMessage);
      finishRequest(requestContext.conversationId, requestContext.requestId);
      return true;
    } catch (error) {
      failRequest(
        requestContext.conversationId,
        requestContext.requestId,
        errorText(error),
        question,
      );
      return false;
    }
  }

  function chooseSuggestedPartition(partition: Partition) {
    setRouteMode(partition);
    const lastQuestion = [...activeConversation.messages]
      .reverse()
      .find((message) => message.role === "user")?.content;
    if (lastQuestion) void ask(lastQuestion, partition);
  }

  return (
    <div className={`chat-page ${hasMessages ? "chat-page--active" : ""}`}>
      {hasMessages ? (
        <div className="chat-thread">
          <MessageList
            loading={loading}
            messages={activeConversation.messages}
            onChoosePartition={chooseSuggestedPartition}
          />
          {runtime.error && (
            <div className="page-alert" role="alert">
              {runtime.error}
            </div>
          )}
          <div className="thread-controls">
            <PartitionSelector
              includeAuto
              legend="切换问答路由模式"
              onChange={setRouteMode}
              value={routeMode}
            />
            <ChatComposer
              allowWebFallback={allowWebFallback}
              compact
              restoreValue={runtime.retryQuestion}
              loading={loading}
              onAllowWebFallbackChange={setAllowWebFallback}
              onSubmit={ask}
            />
          </div>
        </div>
      ) : (
        <div className="chat-empty-state">
          <div className="chat-title">
            <span className="chat-title-icon">
              <Database aria-hidden="true" size={23} strokeWidth={1.8} />
            </span>
            <h1>从企业知识开始提问</h1>
          </div>
          <PartitionSelector
            includeAuto
            legend="选择问答路由模式"
            onChange={setRouteMode}
            value={routeMode}
          />
          <ChatComposer
            allowWebFallback={allowWebFallback}
            loading={loading}
            onAllowWebFallbackChange={setAllowWebFallback}
            onSubmit={ask}
            restoreValue={runtime.retryQuestion}
          />
          {runtime.error && (
            <div className="page-alert empty-page-alert" role="alert">
              {runtime.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
