import { useRef, useLayoutEffect } from "react";
import type { ConvoMessage } from "./types";
import { CleaningReviewTable } from "./CleaningReviewTable";
import { AnalystReviewTable } from "./AnalystReviewTable";
import { ToolExchangeTurn } from "../../components/ToolExchangeTurn";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AskUserPrompt } from "../../components/AskUserPrompt";
import { sanitizeHtml } from "../../utils/sanitize";

export function ConvoFeed({
  messages,
  scrollFieldTableId,
  scrollFieldTableNonce,
  onAskReply,
}: {
  messages: ConvoMessage[];
  scrollFieldTableId: string | null;
  scrollFieldTableNonce: number;
  /** Callback when AskUserPrompt sends a reply */
  onAskReply?: (answer: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  useLayoutEffect(() => {
    if (!scrollFieldTableId || scrollFieldTableNonce === 0) return;
    const root = containerRef.current;
    if (!root) return;
    const el = root.querySelector(
      `[data-workflow-id="${scrollFieldTableId}"]`,
    );
    el?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "nearest",
    });
  }, [scrollFieldTableId, scrollFieldTableNonce]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-4 py-3 space-y-2"
    >
      {messages.map((m) => {
      // Workflow: FieldReview table — removed, now handled by markdown rendering
      if (m.role === "workflow" && m.fieldReview) {
          return null;
      }
      // Workflow: CleaningReview table
        if (m.role === "workflow" && m.cleaningReview) {
          return (
            <div key={m.id} className="flex justify-start w-full">
              <div className="w-full max-w-full">
                <CleaningReviewTable data={m.cleaningReview} />
              </div>
            </div>
          );
        }
        // Workflow: AnalystReview table
        if (m.role === "workflow" && m.analystReview) {
          return (
            <div key={m.id} className="flex justify-start w-full">
              <div className="w-full max-w-full">
                <AnalystReviewTable data={m.analystReview} />
              </div>
            </div>
          );
        }
        // CO-13: Tool exchange block
        if (m.toolExchange) {
          return (
            <div key={m.id} className="flex justify-start w-full">
              <div className="w-full max-w-full">
                <ToolExchangeTurn
                  stage={m.toolExchange.stage}
                  tool_calls={m.toolExchange.tool_calls}
                  assistant_pre_text={m.toolExchange.assistant_pre_text}
                />
              </div>
            </div>
          );
        }
        // CO-14: Ask user — delegate to AskUserPrompt component (handles yes_no / choice / free_text)
        if (m.askUser && onAskReply) {
          return (
            <div key={m.id} className="flex justify-start">
              <div className="max-w-[85%]">
                <AskUserPrompt
                  question={m.askUser.question}
                  options={m.askUser.options}
                  expected_format={m.askUser.expected_format}
                  onReply={onAskReply}
                />
              </div>
            </div>
          );
        }
        // Text message (system/user/agent/workflow gate)
        return (
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
              {m.html ? (
                <span dangerouslySetInnerHTML={{ __html: sanitizeHtml(m.html) }} />
              ) : m.role !== "user" && typeof m.text === "string" && m.text && !m.streaming ? (
                <div className="kb-detail-html">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                </div>
              ) : (
                <>
                  {typeof m.text === "string" ? m.text : JSON.stringify(m.text)}
                  {/* CO-19: 流式光标 */}
                  {m.streaming && (
                    <span className="inline-block w-2 h-4 bg-app-accent ml-0.5 align-text-bottom animate-pulse" />
                  )}
                </>
              )}
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
