import { useRef, useEffect } from "react";
import { EmptyState } from "./EmptyState";

export interface LogLine {
  id: string;
  text: string;
  type: "user" | "system" | "event";
  timestamp: string;
}

interface LogViewProps {
  lines: LogLine[];
}

function LogRow({ line }: { line: LogLine }) {
  const color =
    line.type === "user"
      ? "text-[#569cd6]"
      : line.type === "event"
        ? "text-[#6a9955]"
        : "text-[#ce9178]";

  return (
    <div className={`${color} mb-1`}>
      <span className="text-[#555] text-[11px] mr-2">
        {new Date(line.timestamp).toLocaleTimeString()}
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
    <div className="flex-1 overflow-auto px-3 py-2 font-mono text-[13px] leading-relaxed">
      {lines.length === 0 && (
        <EmptyState message="Send a query to start analysis" />
      )}
      {lines.map((l) => (
        <LogRow key={l.id} line={l} />
      ))}
      <div ref={tailRef} />
    </div>
  );
}