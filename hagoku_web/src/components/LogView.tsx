import { useRef, useEffect, type ReactNode } from "react";
import { EmptyState } from "./EmptyState";

export interface LogLine {
  id: string;
  text: ReactNode;
  type: "user" | "system" | "event";
  timestamp: string;
}

interface LogViewProps {
  lines: LogLine[];
}

const LOG_COLOR: Record<LogLine["type"], string> = {
  user:    "text-app-accent",
  event:   "text-event-done",
  system:  "text-event-warn",
};

function LogRow({ line }: { line: LogLine }) {
  const color = LOG_COLOR[line.type];

  return (
    <div className={`${color} mb-1`}>
      <span className="text-app-text-muted text-ui-xs mr-2">
        {new Date(line.timestamp).toLocaleTimeString('zh-CN')}
      </span>
      {line.text}
    </div>
  );
}

export function LogView({ lines }: LogViewProps) {
  const tailRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    tailRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  return (
    <div className="flex-1 overflow-auto px-3 py-2 font-mono text-ui-base leading-relaxed">
      {lines.length === 0 && (
        <EmptyState message="在下方输入问题，开始分析" />
      )}
      {lines.map((l) => (
        <LogRow key={l.id} line={l} />
      ))}
      <div ref={tailRef} />
    </div>
  );
}