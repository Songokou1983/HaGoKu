import { useRef, useLayoutEffect } from "react";
import type { ConvoMessage } from "./types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { sanitizeHtml } from "../../utils/sanitize";

export function ConvoFeed({
  messages,
}: {
  messages: ConvoMessage[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [messages.length]);

  return (
    <div ref={containerRef} className="h-full overflow-y-auto">
      {messages.map((m) => (
        <div
          key={m.id}
          className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[85%] px-3 py-2 rounded-lg text-ui-sm leading-relaxed
              ${
                m.role === "user"
                  ? "bg-app-accent text-white rounded-br-sm"
                  : m.role === "agent"
                    ? "bg-app-bg-secondary border border-app-border text-app-text rounded-bl-sm"
                    : "bg-transparent text-app-text-muted text-ui-xs italic whitespace-pre-wrap"
              }`}
          >
            {m.role !== "user" && typeof m.text === "string" && m.text && !m.streaming ? (
              <div className="kb-detail-html">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
              </div>
            ) : (
              <>
                {typeof m.text === "string" ? m.text : JSON.stringify(m.text)}
                {m.streaming && (
                  <span className="inline-block w-2 h-4 bg-app-accent ml-0.5 align-text-bottom animate-pulse" />
                )}
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
