import { FolderOpen } from "lucide-react";
import { useState, useEffect } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";
import type { AgentId, AgentStatus } from "../types/events";

const agentDef: Record<AgentId, { emoji: string; label: string }> = {
  scout: { emoji: "🔍", label: "Scout" },
  cleaner: { emoji: "🧹", label: "Cleaner" },
  analyst: { emoji: "📊", label: "Analyst" },
  reporter: { emoji: "📝", label: "Reporter" },
};

function StatusBadge({ status }: { status: AgentStatus }) {
  const def = {
    idle: "bg-[#333] text-app-text-muted",
    running: "bg-[#1a3a5c] text-app-accent",
    done: "bg-[#1a3a1a] text-app-success",
    error: "bg-[#3a1a1a] text-app-error",
    waiting_input: "bg-[#3a3a1a] text-app-warning",
  }[status];
  return (
    <span className={`text-ui-xs px-1.5 py-0.5 rounded ${def}`}>
      {status}
    </span>
  );
}

export default function ProjectPanel() {
  const agents = useWorkspaceStore((s) => s.agents);
  const [summary, setSummary] = useState("");

  useAgentStatusSync();

  const batch = useBatchEvents();

  useEffect(() => {
    if (batch.length === 0) return;
    // Listen for run_started to show analysis target — accumulate then set once
    let found = "";
    for (const msg of batch) {
      if (msg.type === "event" && msg.data) {
        const d = msg.data;
        if (d.event_type === "run_started" && typeof d.data?.query === "string") {
          found = `📋 ${d.data.query}`;
        }
      }
    }
    if (found) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- external event sync, functional update ensures correct merge
      setSummary((prev) => (prev !== found ? found : prev));
    }
  }, [batch]);

  const agentList = Object.entries(agentDef) as [AgentId, { emoji: string; label: string }][];

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="Project" />
      <div className="flex-1 overflow-auto p-3 space-y-4">
        {summary ? (
          <div className="p-2 bg-app-bg-secondary border border-app-border rounded text-ui-base text-app-text whitespace-pre-wrap">
            {summary}
          </div>
        ) : (
          <EmptyState
            icon={<FolderOpen size={32} />}
            message="Start a query in Analyze"
          />
        )}
        <div className="space-y-2">
          {agentList.map(([id, { emoji, label }]) => {
            const st = agents[id] ?? "idle";
            return (
              <div
                key={id}
                className="flex items-center gap-2 p-1.5 bg-app-bg-secondary border border-app-border rounded"
              >
                <span className="text-sm">{emoji}</span>
                <span className="text-ui-base text-app-text flex-1">{label}</span>
                <StatusBadge status={st} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}