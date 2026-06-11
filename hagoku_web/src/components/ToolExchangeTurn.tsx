import React, { useState } from "react";

interface ToolCallItem {
  id: string;
  name: string;
  arguments_summary?: string;
  result_summary?: string;
  error?: string | null;
  duration_ms?: number;
}

interface ToolExchangeTurnProps {
  stage: string;
  tool_calls: ToolCallItem[];
  assistant_pre_text?: string | null;
  timestamp?: string;
}

/** Renders a single tool exchange block — the core of HaGoKu transparency. */
const ToolExchangeTurn: React.FC<ToolExchangeTurnProps> = ({
  stage,
  tool_calls,
  assistant_pre_text,
}) => {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggle = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  if (!tool_calls || tool_calls.length === 0) return null;

  return (
    <div className="tool-exchange-turn">
      {assistant_pre_text && (
        <div className="tool-exchange-pre-text">{assistant_pre_text}</div>
      )}
      {tool_calls.map((tc) => (
        <div
          key={tc.id}
          className={`tool-call-item ${tc.error ? "tool-call-error" : ""}`}
        >
          <div className="tool-call-header" onClick={() => toggle(tc.id)}>
            <span className="tool-call-icon">{tc.error ? "❌" : "→"}</span>
            <span className="tool-call-name">{tc.name}</span>
            <span className="tool-call-summary">
              {tc.error ? tc.error : tc.result_summary || "✓"}
            </span>
          </div>
          {expanded[tc.id] && (
            <div className="tool-call-detail">
              {tc.arguments_summary && (
                <div className="tool-call-args">
                  入参: {tc.arguments_summary}
                </div>
              )}
              {tc.result_summary && (
                <div className="tool-call-result">
                  结果: {tc.result_summary}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

export default ToolExchangeTurn;
