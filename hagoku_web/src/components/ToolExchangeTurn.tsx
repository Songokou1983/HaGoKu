import { useState } from "react";
import { ChevronDown, ChevronRight, Wrench, AlertTriangle } from "lucide-react";
import type { ToolCallItem } from "../types/events";

export interface ToolExchangeTurnProps {
  stage: string;
  tool_calls: ToolCallItem[];
  assistant_pre_text?: string | null;
  timestamp?: string;
}

/** CO-13: Renders a single tool exchange block — the core of HaGoKu transparency. */
export function ToolExchangeTurn({
  tool_calls,
  assistant_pre_text,
}: ToolExchangeTurnProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggle = (id: string) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  if (!tool_calls || tool_calls.length === 0) return null;

  return (
    <div className="border border-app-border/60 rounded-md overflow-hidden bg-app-bg-secondary/50 my-1">
      {/* Assistant pre-text (流出的 prose，在 tool 调用前) */}
      {assistant_pre_text && (
        <div className="px-3 py-2 text-ui-xs text-app-text-muted italic border-b border-app-border/40 whitespace-pre-wrap">
          {assistant_pre_text}
        </div>
      )}

      {/* Tool call items */}
      {tool_calls.map((tc) => {
        const isExpanded = !!expanded[tc.id];
        const hasError = !!tc.error;
        return (
          <div
            key={tc.id}
            className={`border-b border-app-border/30 last:border-b-0 ${
              hasError ? "bg-app-error/5" : ""
            }`}
          >
            <button
              onClick={() => toggle(tc.id)}
              className="w-full flex items-center gap-2 px-3 py-2 text-left
                hover:bg-app-bg-tertiary transition-colors duration-150 cursor-pointer"
            >
              {isExpanded ? (
                <ChevronDown size={12} className="text-app-text-muted shrink-0" />
              ) : (
                <ChevronRight size={12} className="text-app-text-muted shrink-0" />
              )}
              <Wrench size={12} className="text-app-accent shrink-0" />
              <span
                className={`text-ui-xs font-mono font-medium ${
                  hasError ? "text-app-error" : "text-app-accent"
                }`}
              >
                {tc.name}
              </span>
              <span className="text-ui-xs text-app-text-muted truncate flex-1">
                {hasError ? (
                  <span className="inline-flex items-center gap-1 text-app-error">
                    <AlertTriangle size={10} />
                    {tc.error}
                  </span>
                ) : (
                  tc.result_summary || tc.arguments_summary || ""
                )}
              </span>
            </button>

            {isExpanded && (
              <div className="px-3 pb-2 space-y-1">
                {tc.arguments_summary && (
                  <div className="text-ui-xs text-app-text-muted">
                    <span className="text-app-text-muted/60">入参: </span>
                    <code className="text-app-accent font-mono break-all">
                      {tc.arguments_summary}
                    </code>
                  </div>
                )}
                {tc.result_summary && (
                  <div className="text-ui-xs text-app-text-muted">
                    <span className="text-app-text-muted/60">结果: </span>
                    <code className="text-app-text font-mono break-all">
                      {tc.result_summary}
                    </code>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
