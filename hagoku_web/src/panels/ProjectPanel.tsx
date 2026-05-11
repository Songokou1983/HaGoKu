import { FolderOpen, Plus } from "lucide-react";
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
    idle: "bg-app-bg-tertiary text-app-text-muted",
    running: "bg-app-running text-app-accent",
    done: "bg-app-done text-app-success",
    error: "bg-app-status-error text-app-error",
    waiting_input: "bg-app-status-waiting text-app-warning",
  }[status];
  return (
    <span className={`text-ui-xs px-1.5 py-0.5 rounded ${def}`}>
      {status}
    </span>
  );
}

export default function ProjectPanel() {
  const agents = useWorkspaceStore((s) => s.agents);
  const projects = useWorkspaceStore((s) => s.projects);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const setProjects = useWorkspaceStore((s) => s.setProjects);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const [summary, setSummary] = useState("");
  const [newName, setNewName] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useAgentStatusSync();
  const batch = useBatchEvents();

  // Load project list on mount
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- mount fetch triggers intentional loading state
    setLoading(true);
     
    setLoadError(null);
    fetch("/api/projects")
      .then((r) => r.json())
      .then((d) => setProjects(d.projects as string[]))
      .catch(() => setLoadError("加载失败，请检查服务"))
      .finally(() => setLoading(false));
  }, [setProjects]);

  // Listen for run_started to show analysis target
  useEffect(() => {
    if (batch.length === 0) return;
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

  const handleCreate = async () => {
    if (!newName.trim()) return;
    await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.trim() }),
    });
    const updated = await fetch("/api/projects").then((r) => r.json());
    setProjects(updated.projects as string[]);
    setCurrentProject(newName.trim());
    setNewName("");
  };

  const agentList = Object.entries(agentDef) as [AgentId, { emoji: string; label: string }][];

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="Project" />
      <div className="flex-1 overflow-auto p-3 space-y-4">
        {/* Summary */}
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

        {/* Project selector */}
        {loading && (
          <div className="text-ui-sm text-app-text-muted py-2">加载中…</div>
        )}
        {loadError && (
          <div className="text-ui-sm text-app-error py-1">{loadError}</div>
        )}
        {projects.length > 0 && (
          <div className="space-y-1">
            <div className="text-ui-xs text-app-text-muted uppercase">Projects</div>
            <div className="flex flex-wrap gap-1">
              {projects.map((p) => (
                <button
                  key={p}
                  onClick={() => setCurrentProject(p)}
                  className={`px-2 py-0.5 text-ui-sm rounded border transition-colors ${
                    p === currentProject
                      ? "bg-app-accent text-white border-app-accent"
                      : "bg-app-bg-secondary text-app-text border-app-border hover:border-app-accent"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* New project form */}
        <div className="flex gap-1">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            placeholder="New project name"
            className="flex-1 px-2 py-1 text-ui-sm bg-app-bg-secondary border border-app-border rounded
                       text-app-text placeholder-app-text-muted focus:outline-none focus:border-app-accent"
          />
          <button
            onClick={handleCreate}
            className="px-2 py-1 text-ui-sm bg-app-accent hover:bg-app-accent-hover text-white rounded
                       flex items-center gap-1 transition-colors"
          >
            <Plus size={14} />
            <span>New</span>
          </button>
        </div>

        {/* Agent status */}
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