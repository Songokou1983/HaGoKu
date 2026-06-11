import { Loader2, CheckCircle2, X, ShieldAlert, Clock, Search, Sparkles, BarChart2, FileText } from "lucide-react";
import type { AgentKey, AgentRunState } from "./types";
import { focusLabel, focusDesc } from "../../constants/focusAreas";

const PIPELINE_AGENTS = [
  { key: "scout" as const,    icon: Search, },
  { key: "cleaner" as const,  icon: Sparkles, },
  { key: "analyst" as const,  icon: BarChart2, },
  { key: "reporter" as const, icon: FileText, },
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
          state === "running" ? "bg-app-accent/15 border-app-accent text-app-accent ring-1 ring-app-accent" :
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
            <span className="text-ui-xs font-medium">{focusLabel(agent.key)}</span>
            <span className="text-ui-xs opacity-60">{focusDesc(agent.key)}</span>
            {secs > 0 && (
              <span className="text-ui-xs opacity-50">{secs}s</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
