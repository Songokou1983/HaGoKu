import { useState } from "react";
import { Send } from "lucide-react";

export interface AskUserPromptProps {
  question: string;
  options?: string[];
  expected_format?: string;
  onReply: (answer: string) => void;
}

/** CO-14: 按 expected_format 分 3 种渲染：yes_no / choice / free_text */
export function AskUserPrompt({
  question,
  options,
  expected_format,
  onReply,
}: AskUserPromptProps) {
  const fmt = expected_format || "free_text";

  if (fmt === "yes_no") {
    return (
      <div className="border border-app-border/60 rounded-md p-3 bg-app-bg-secondary/50 my-1">
        <p className="text-ui-sm text-app-text mb-2 leading-relaxed">{question}</p>
        <div className="flex gap-2">
          <button
            onClick={() => onReply("是")}
            className="px-4 py-1.5 rounded text-ui-xs font-medium bg-app-accent text-white
              hover:bg-app-accent-hover transition-colors duration-150 cursor-pointer"
          >
            是
          </button>
          <button
            onClick={() => onReply("否")}
            className="px-4 py-1.5 rounded text-ui-xs font-medium border border-app-border
              text-app-text hover:border-app-accent hover:text-app-accent
              transition-colors duration-150 cursor-pointer"
          >
            否
          </button>
        </div>
      </div>
    );
  }

  if (fmt === "choice" && options && options.length > 0) {
    return (
      <div className="border border-app-border/60 rounded-md p-3 bg-app-bg-secondary/50 my-1">
        <p className="text-ui-sm text-app-text mb-2 leading-relaxed">{question}</p>
        <div className="flex flex-wrap gap-2">
          {options.map((opt) => (
            <button
              key={opt}
              onClick={() => onReply(opt)}
              className="px-3 py-1.5 rounded text-ui-xs font-medium border border-app-border
                text-app-text hover:border-app-accent hover:text-app-accent
                transition-colors duration-150 cursor-pointer"
            >
              {opt}
            </button>
          ))}
        </div>
      </div>
    );
  }

  // free_text (default)
  return <FreeTextAsk question={question} onReply={onReply} />;
}

function FreeTextAsk({
  question,
  onReply,
}: {
  question: string;
  onReply: (answer: string) => void;
}) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onReply(trimmed);
    setText("");
  };

  return (
    <div className="border border-app-border/60 rounded-md p-3 bg-app-bg-secondary/50 my-1">
      <p className="text-ui-sm text-app-text mb-2 leading-relaxed">{question}</p>
      <div className="flex gap-2 items-end">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder="输入回复…"
          autoFocus
          className="flex-1 bg-app-bg border border-app-border rounded px-3 py-1.5
            text-ui-sm text-app-text placeholder-app-text-muted
            focus:outline-none focus:border-app-accent transition-colors"
        />
        <button
          onClick={handleSubmit}
          disabled={!text.trim()}
          className="px-3 py-1.5 rounded text-ui-xs font-medium bg-app-accent text-white
            hover:bg-app-accent-hover transition-colors duration-150 cursor-pointer
            disabled:opacity-50 disabled:cursor-not-allowed shrink-0
            flex items-center gap-1"
        >
          <Send size={12} />
          发送
        </button>
      </div>
    </div>
  );
}
