import { ArrowUp, Globe2, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface ChatComposerProps {
  loading: boolean;
  onSubmit: (question: string) => Promise<boolean>;
  allowWebFallback: boolean;
  onAllowWebFallbackChange: (allowed: boolean) => void;
  restoreValue?: string | null;
  compact?: boolean;
}

const MAX_QUESTION_LENGTH = 2000;

export function ChatComposer({
  loading,
  onSubmit,
  allowWebFallback,
  onAllowWebFallbackChange,
  restoreValue,
  compact = false,
}: ChatComposerProps) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const trimmed = value.trim();

  useEffect(() => {
    if (restoreValue) setValue(restoreValue);
  }, [restoreValue]);

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
          aria-describedby={error ? "question-error" : undefined}
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
          <button
            aria-label={
              allowWebFallback
                ? "已开启：知识库未命中时联网搜索"
                : "未命中时联网"
            }
            aria-pressed={allowWebFallback}
            className="web-fallback-toggle"
            disabled={loading}
            onClick={() => onAllowWebFallbackChange(!allowWebFallback)}
            title={
              allowWebFallback
                ? "已开启：知识库未命中时联网搜索"
                : "未命中时联网"
            }
            type="button"
          >
            <Globe2 aria-hidden="true" size={16} />
            <span className="sr-only">未命中时联网</span>
          </button>
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
              <ArrowUp aria-hidden="true" size={17} strokeWidth={2.1} />
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
