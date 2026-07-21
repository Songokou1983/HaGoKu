import { useState, useMemo } from "react";
import { ChevronDown, ChevronRight, Wrench, AlertTriangle } from "lucide-react";
import type { ToolCallItem } from "../types/events";

export interface ToolExchangeTurnProps {
  stage: string;
  tool_calls: ToolCallItem[];
  timestamp?: string;
}

/** 工具调用卡片：默认折叠，展开后逐条显示 */
export function ToolExchangeTurn({
  tool_calls,
}: ToolExchangeTurnProps) {
  const [open, setOpen] = useState(false);

  const summary = useMemo(() => {
    if (!tool_calls || tool_calls.length === 0) return "";
    const counts: Record<string, number> = {};
    for (const tc of tool_calls) {
      counts[tc.name] = (counts[tc.name] || 0) + 1;
    }
    return Object.entries(counts)
      .map(([name, n]) => (n > 1 ? `${n} 个 ${name}` : name))
      .join(", ");
  }, [tool_calls]);

  if (!tool_calls || tool_calls.length === 0) return null;

  const errors = tool_calls.filter((tc) => tc.error);

  return (
    <div className="border border-app-border/60 rounded-md overflow-hidden bg-app-bg-secondary/50 my-1">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left
          hover:bg-app-bg-tertiary transition-colors duration-150 cursor-pointer"
      >
        {open ? (
          <ChevronDown size={12} className="text-app-text-muted shrink-0" />
        ) : (
          <ChevronRight size={12} className="text-app-text-muted shrink-0" />
        )}
        <Wrench size={12} className="text-app-accent shrink-0" />
        <span className="text-ui-xs text-app-accent font-mono">
          {tool_calls.length} 个工具
        </span>
        <span className="text-ui-xs text-app-text-muted truncate flex-1">
          {summary}
        </span>
        {errors.length > 0 && (
          <AlertTriangle size={12} className="text-app-error shrink-0" />
        )}
      </button>

      {open &&
        tool_calls.map((tc) => (
          <div
            key={tc.id}
            className={`border-t border-app-border/30 px-3 py-2 ${
              tc.error ? "bg-app-error/5" : ""
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span
                className={`text-ui-xs font-mono font-medium ${
                  tc.error ? "text-app-error" : "text-app-accent"
                }`}
              >
                {tc.name}
              </span>
              {tc.error && (
                <span className="text-ui-xs text-app-error">{tc.error}</span>
              )}
            </div>
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
        ))}
    </div>
  );
}
