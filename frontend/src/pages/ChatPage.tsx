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
  if (response.answer) return response.answer;
  switch (response.code) {
    case "ROUTE_CLARIFICATION_REQUIRED":
      return "这个问题可能涉及多个知识分区，请先选择最相关的分区。";
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
  const [loading, setLoading] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const { activeConversation, appendMessage } = useChatSession();
  const hasMessages = activeConversation.messages.length > 0;

  useEffect(() => {
    if (isPartition(hintedPartition)) setRouteMode(hintedPartition);
  }, [hintedPartition]);

  async function ask(question: string, partition = routeMode): Promise<boolean> {
    if (loading) return false;
    setLoading(true);
    setPageError(null);

    try {
      const response = await knowledgeApi.chat({
        question,
        partition_hint: partition,
      });
      const userMessage: ChatMessage = {
        id: messageId(),
        role: "user",
        content: question,
      };
      const assistantMessage: ChatMessage = {
        id: messageId(),
        role: "assistant",
        content: responseText(response),
        citations: response.citations,
        code: response.code,
        route: response.route,
        suggestedPartitions: response.suggested_partitions,
        requestId: response.request_id,
        warning: response.warning,
      };
      appendMessage(userMessage);
      appendMessage(assistantMessage);
      return true;
    } catch (error) {
      setPageError(errorText(error));
      return false;
    } finally {
      setLoading(false);
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
          {pageError && (
            <div className="page-alert" role="alert">
              {pageError}
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
              compact
              loading={loading}
              onSubmit={ask}
              routeMode={routeMode}
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
          <ChatComposer loading={loading} onSubmit={ask} routeMode={routeMode} />
          {pageError && (
            <div className="page-alert empty-page-alert" role="alert">
              {pageError}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
