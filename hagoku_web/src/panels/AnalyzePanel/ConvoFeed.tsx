import { useRef, useLayoutEffect } from "react";
import type { ConvoMessage } from "./types";
import { FieldReviewTable } from "./FieldReviewTable";
import { CleaningReviewTable } from "./CleaningReviewTable";
import { AnalystReviewTable } from "./AnalystReviewTable";

export function ConvoFeed({
  messages,
  scrollFieldTableId,
  scrollFieldTableNonce,
}: {
  messages: ConvoMessage[];
  scrollFieldTableId: string | null;
  scrollFieldTableNonce: number;
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
    const el = root.querySelector(`[data-workflow-id="${scrollFieldTableId}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  }, [scrollFieldTableId, scrollFieldTableNonce]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
      {messages.map((m) => {
        if (m.role === "workflow" && m.fieldReview) {
          return (
            <div key={m.id} data-workflow-id={m.id} className="flex justify-start w-full">
              <div className="w-full max-w-full">
                <FieldReviewTable data={m.fieldReview} />
              </div>
            </div>
          );
        }
        if (m.role === "workflow" && m.cleaningReview) {
          return (
            <div key={m.id} className="flex justify-start w-full">
              <div className="w-full max-w-full">
                <CleaningReviewTable data={m.cleaningReview} />
              </div>
            </div>
          );
        }
        if (m.role === "workflow" && m.analystReview) {
          return (
            <div key={m.id} className="flex justify-start w-full">
              <div className="w-full max-w-full">
                <AnalystReviewTable data={m.analystReview} />
              </div>
            </div>
          );
        }
        return (
          <div
            key={m.id}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] px-3 py-2 rounded-lg text-ui-sm leading-relaxed
                ${m.role === "user"
                  ? "bg-app-accent text-white rounded-br-sm"
                  : m.role === "agent"
                  ? "bg-app-bg-secondary border border-app-border text-app-text rounded-bl-sm whitespace-pre-wrap"
                  : "bg-transparent text-app-text-muted text-ui-xs italic whitespace-pre-wrap"
                }`}
            >
              {m.html ? <span dangerouslySetInnerHTML={{ __html: m.html }} /> : m.text}
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
