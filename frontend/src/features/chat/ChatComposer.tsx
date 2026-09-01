import { ArrowUp, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { RouteMode } from "../../api/types";
import { getRouteLabel } from "../../constants/partitions";

interface ChatComposerProps {
  routeMode: RouteMode;
  loading: boolean;
  onSubmit: (question: string) => Promise<boolean>;
  compact?: boolean;
}

const MAX_QUESTION_LENGTH = 2000;

export function ChatComposer({
  routeMode,
  loading,
  onSubmit,
  compact = false,
}: ChatComposerProps) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const trimmed = value.trim();

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, compact ? 144 : 180)}px`;
  }, [compact, value]);

  async function submit() {
    if (loading || !trimmed) return;
    if (trimmed.length > MAX_QUESTION_LENGTH) {
      setError(`问题不能超过 ${MAX_QUESTION_LENGTH} 个字符`);
      return;
    }
    setError(null);
    const succeeded = await onSubmit(trimmed);
    if (succeeded) setValue("");
  }

  return (
    <div className="composer-wrap">
      <div className="chat-composer" data-compact={compact}>
        <label className="sr-only" htmlFor="chat-question">
          输入知识库问题
        </label>
        <textarea
          aria-describedby={error ? "question-error" : "route-mode-note"}
          disabled={loading}
          id="chat-question"
          maxLength={MAX_QUESTION_LENGTH + 1}
          onChange={(event) => {
            setValue(event.target.value);
            if (error) setError(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder="向企业知识库提问"
          ref={textareaRef}
          rows={1}
          value={value}
        />
        <div className="composer-footer">
          <span id="route-mode-note">
            当前：<strong>{getRouteLabel(routeMode)}</strong>
          </span>
          <button
            aria-label={loading ? "正在发送" : "发送问题"}
            className="send-button"
            disabled={!trimmed || loading}
            onClick={() => void submit()}
            type="button"
          >
            {loading ? (
              <LoaderCircle aria-hidden="true" className="spin" size={18} />
            ) : (
              <ArrowUp aria-hidden="true" size={19} strokeWidth={2.1} />
            )}
          </button>
        </div>
      </div>
      {error && (
        <p className="field-error" id="question-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
