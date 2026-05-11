import { FolderOpen, Plus, Loader2, Search, Sparkles, BarChart2, FileText, Circle, CheckCircle2, XCircle } from "lucide-react";
import { useState, useEffect, useRef, type ComponentType } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";
import type { AgentId, AgentStatus } from "../types/events";

const agentDef: Record<AgentId, { Icon: ComponentType<{ size?: number; className?: string }>; label: string }> = {
  scout:    { Icon: Search,      label: "Scout" },
  cleaner:  { Icon: Sparkles,    label: "Cleaner" },
  analyst:  { Icon: BarChart2,  label: "Analyst" },
  reporter: { Icon: FileText,    label: "Reporter" },
};

const STATUS_LABEL: Record<AgentStatus, string> = {
  idle:          "待机",
  running:       "运行中",
  done:          "完成",
  error:         "异常",
  waiting_input: "等待确认",
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
      {STATUS_LABEL[status]}
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
  const [creating, setCreating] = useState(false);
  const [runMeta, setRunMeta] = useState<{
    query: string;
    startedAt: number;
    elapsed: string;
    status: "running" | "done" | "failed";
  } | null>(null);
  const runStartedAtRef = useRef<number>(0);

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
          found = d.data.query as string;
          runStartedAtRef.current = Date.now();
          // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: tracking run start, ref avoids dep cycle
          setRunMeta({ query: d.data.query as string, startedAt: Date.now(), elapsed: "", status: "running" });
        }
        if (d.event_type === "run_completed" || d.event_type === "run_failed") {
          const elapsed = `${((Date.now() - runStartedAtRef.current) / 1000).toFixed(1)}s`;
          setRunMeta((prev) => prev ? {
            ...prev,
            elapsed,
            status: d.event_type === "run_completed" ? "done" : "failed",
          } : null);
        }
      }
    }
    if (found) {
       
      setSummary((prev) => (prev !== found ? found : prev));
    }
  }, [batch]);

  const handleCreate = async () => {
    if (!newName.trim() || creating) return;
    setCreating(true);
    try {
    await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.trim() }),
    });
    const updated = await fetch("/api/projects").then((r) => r.json());
    setProjects(updated.projects as string[]);
    setCurrentProject(newName.trim());
    setNewName("");
    } finally {
      setCreating(false);
    }
  };

  const agentList = Object.entries(agentDef) as [AgentId, { Icon: ComponentType<{ size?: number; className?: string }>; label: string }][];

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="Projects" />
      <div className="flex-1 overflow-auto p-3 space-y-4">
        {/* Summary */}
        {summary ? (
          <div className="p-2 bg-app-bg-secondary border border-app-border rounded text-ui-base text-app-text whitespace-pre-wrap">
            {summary}
          </div>
        ) : (
          <EmptyState
            icon={<FolderOpen size={32} />}
            message="在 Analyze 面板发起分析"
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
                  className={`px-2 py-0.5 text-ui-sm rounded border transition-colors duration-150 ${
                    p === currentProject
                      ? "bg-app-accent text-white border-app-accent cursor-pointer hover:brightness-110"
                      : "bg-app-bg-secondary text-app-text border-app-border hover:border-app-accent cursor-pointer"
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
            aria-label="新项目名称"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            placeholder="新项目名称"
            className="flex-1 px-2 py-1 text-ui-sm bg-app-bg-secondary border border-app-border rounded
                       text-app-text placeholder-app-text-muted focus:outline-none focus:border-app-accent focus-visible:ring-1 focus-visible:ring-app-accent"
          />
          <button
            onClick={handleCreate}
            disabled={creating}
            className="px-2 py-1 text-ui-sm bg-app-accent hover:bg-app-accent-hover text-white rounded
                       flex items-center gap-1 transition-colors duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            <span>{creating ? "创建中…" : "新建"}</span>
          </button>
        </div>

        {/* Agent status */}
        {runMeta && (
          <div className={`px-3 py-1.5 border-b border-app-border text-ui-xs flex items-center gap-2
            ${runMeta.status === "running" ? "text-app-warning" : runMeta.status === "done" ? "text-app-success" : "text-app-error"}`}>
            <span className={runMeta.status === "running" ? "animate-pulse" : ""}>
              {runMeta.status === "running" ? <Circle size={10} className="text-app-warning fill-current" /> : runMeta.status === "done" ? <CheckCircle2 size={10} className="text-app-success" /> : <XCircle size={10} className="text-app-error" />}
            </span>
            <span className="flex-1 truncate">{runMeta.query}</span>
            {runMeta.elapsed && <span className="shrink-0 text-app-text-muted">{runMeta.elapsed}</span>}
          </div>
        )}
        <div className="space-y-2">
          {agentList.map(([id, { Icon, label }]) => {
            const st = agents[id] ?? "idle";
            return (
              <div
                key={id}
                className="flex items-center gap-2 p-1.5 bg-app-bg-secondary border border-app-border rounded"
              >
                <Icon size={14} className="text-app-text-muted" />
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