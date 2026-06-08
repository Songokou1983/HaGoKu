import { Loader2, CheckCircle2, X, ShieldAlert, Clock, Search, Sparkles, BarChart2, FileText } from "lucide-react";
import type { AgentKey, AgentRunState } from "./types";

const PIPELINE_AGENTS = [
  { key: "scout" as const,    label: "Scout",    icon: Search,    desc: "理解数据" },
  { key: "cleaner" as const,  label: "Cleaner",  icon: Sparkles,  desc: "清洗数据" },
  { key: "analyst" as const,  label: "Analyst",  icon: BarChart2, desc: "统计分析" },
  { key: "reporter" as const, label: "Reporter", icon: FileText,  desc: "生成报告" },
];

export function PipelineBar({ states, elapsed }: {
  states: Record<AgentKey, AgentRunState>;
  elapsed: Record<AgentKey, number>;
}) {
  return (
    <div className="flex items-stretch gap-0 border border-app-border rounded overflow-hidden shrink-0">
      {PIPELINE_AGENTS.map((agent, i) => {
        const state = states[agent.key];
        const Icon = agent.icon;
        const secs = elapsed[agent.key];
        const colorClass =
          state === "running" ? "bg-app-accent/15 border-app-accent text-app-accent" :
          state === "done"    ? "bg-app-success/10 text-app-success" :
          state === "error"   ? "bg-app-error/10 text-app-error" :
          state === "skipped" ? "bg-app-warning/10 text-app-warning" :
          "text-app-text-muted";
        return (
          <div
            key={agent.key}
            className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 px-1
              ${colorClass}
              ${i > 0 ? "border-l border-app-border" : ""}
              transition-colors duration-300`}
          >
            <div className="flex items-center gap-1">
              {state === "running"
                ? <Loader2 size={13} className="animate-spin" />
                : state === "done"
                ? <CheckCircle2 size={13} />
                : state === "error"
                ? <X size={13} />
                : state === "skipped"
                ? <ShieldAlert size={13} />
                : <Clock size={13} className="opacity-40" />}
              <Icon size={12} />
            </div>
            <span className="text-ui-xs font-medium">{agent.label}</span>
            <span className="text-ui-xs opacity-60">{agent.desc}</span>
            {secs > 0 && (
              <span className="text-ui-xs opacity-50">{secs}s</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
