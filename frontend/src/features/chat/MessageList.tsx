import { BookOpen, Database, ShieldAlert } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Partition } from "../../api/types";
import { getRouteLabel, partitionLabels } from "../../constants/partitions";
import type { ChatMessage } from "./ChatSessionContext";

interface MessageListProps {
  messages: ChatMessage[];
  loading: boolean;
  onChoosePartition: (partition: Partition) => void;
}

function pageLabel(start: number | null, end: number | null) {
  if (start === null) return null;
  if (end === null || end === start) return `第 ${start} 页`;
  return `第 ${start}-${end} 页`;
}

export function MessageList({
  messages,
  loading,
  onChoosePartition,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [loading, messages.length]);

  return (
    <div className="message-list" aria-live="polite">
      {messages.map((message) => (
        <article className={`message message--${message.role}`} key={message.id}>
          {message.role === "assistant" && (
            <div className="assistant-mark" aria-hidden="true">
              {message.code === "SENSITIVE_INPUT_BLOCKED" ? (
                <ShieldAlert size={16} />
              ) : (
                <Database size={15} />
              )}
            </div>
          )}
          <div className="message-body">
            {message.role === "assistant" && message.route && (
              <div className="message-meta">
                {getRouteLabel(message.route)}分区
              </div>
            )}
            <p>{message.content}</p>
            {message.warning && <p className="message-warning">{message.warning}</p>}

            {!!message.suggestedPartitions?.length && (
              <div className="clarify-actions" aria-label="选择检索分区">
                {message.suggestedPartitions.map((partition) => (
                  <button
                    key={partition}
                    onClick={() => onChoosePartition(partition)}
                    type="button"
                  >
                    {partitionLabels[partition]}
                  </button>
                ))}
              </div>
            )}

            {!!message.citations?.length && (
              <section className="citations" aria-label="回答来源">
                <h3>
                  <BookOpen aria-hidden="true" size={14} />
                  来源
                </h3>
                <ol>
                  {message.citations.map((citation) => {
                    const page = pageLabel(citation.page_start, citation.page_end);
                    return (
                      <li key={citation.chunk_id}>
                        <span className="citation-title">{citation.title}</span>
                        <span className="citation-detail">
                          {[citation.section, page, citation.chunk_id]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              </section>
            )}
          </div>
        </article>
      ))}
      {loading && (
        <div className="message message--assistant message--loading" role="status">
          <div className="assistant-mark" aria-hidden="true">
            <Database size={15} />
          </div>
          <div className="thinking-dots" aria-label="正在检索知识库">
            <span />
            <span />
            <span />
          </div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
