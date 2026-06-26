import {
  FolderOpen, Plus, Loader2, BarChart3, Clock,
  CheckCircle2, Circle, AlertCircle, XCircle, Activity,
  Pencil, Trash2, Check, X, ShieldAlert,
} from "lucide-react";
import { useState, useEffect, useCallback, useRef } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWebSocket } from "../hooks/useWebSocket";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";

interface ProjectDetail {
  name: string;
  created_at: string;
  data_path: string;
  description: string;
  run_count: number;
  last_query: string;
  last_run_at: string;
  last_status: "completed" | "unknown" | "none" | "guardrails_blocked";
  last_guardrails_blocked?: boolean;
}

function fmtRunId(id: string): string {
  const m = id.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/);
  if (!m) return id;
  return `${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
}


type PStatus = "running" | "completed" | "none" | "unknown" | "guardrails_blocked";

const STATUS_CONFIG: Record<PStatus, { dot: string; label: string; icon: React.ReactNode }> = {
  running:   { dot: "bg-app-warning animate-pulse", label: "分析中", icon: <Activity   size={11} /> },
  completed: { dot: "bg-app-success",               label: "已完成", icon: <CheckCircle2 size={11} /> },
  unknown:   { dot: "bg-app-text-muted",            label: "未知",   icon: <AlertCircle  size={11} /> },
  none:      { dot: "bg-app-text-muted/50",         label: "未开始", icon: <Circle       size={11} /> },
  guardrails_blocked: {
    dot: "bg-app-warning",
    label: "护栏未过",
    icon: <ShieldAlert size={11} />,
  },
};

function ProjectCard({
  name,
  isSelected,
  isRunning,
  onSelect,
  onDeleted,
}: {
  name: string;
  isSelected: boolean;
  isRunning: boolean;
  onSelect: () => void;
  onDeleted: () => void;
}) {
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingDesc, setEditingDesc] = useState(false);
  const [descDraft, setDescDraft] = useState("");
  const [savingDesc, setSavingDesc] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const descInputRef = useRef<HTMLInputElement>(null);

  const loadDetail = useCallback(() => {
    fetch(`/api/projects/${name}/detail`)
      .then((r) => r.json())
      .then((d: ProjectDetail) => setDetail(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [name]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setDescDraft(detail?.description ?? "");
    setEditingDesc(true);
    setTimeout(() => descInputRef.current?.focus(), 30);
  };

  const saveDesc = async (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setSavingDesc(true);
    await fetch(`/api/projects/${name}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: descDraft }),
    }).catch(() => {});
    setSavingDesc(false);
    setEditingDesc(false);
    setDetail((prev) => prev ? { ...prev, description: descDraft } : prev);
  };

  const cancelEdit = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setEditingDesc(false);
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirmDelete) { setConfirmDelete(true); return; }
    setDeleting(true);
    await fetch(`/api/projects/${name}`, { method: "DELETE" }).catch(() => {});
    setDeleting(false);
    onDeleted();
  };

  const status: PStatus = isRunning ? "running" : (detail?.last_status ?? "none") as PStatus;
  const cfg = STATUS_CONFIG[status];

  return (
    <div
      onClick={onSelect}
      className={`relative cursor-pointer rounded border transition-all duration-150 overflow-hidden group
        ${isSelected
          ? "border-app-accent bg-app-bg-secondary"
          : "border-app-border bg-app-bg-secondary hover:border-app-accent/40"
        }`}
    >
      {isSelected && <div className="absolute left-0 inset-y-0 w-[3px] bg-app-accent" />}

      <div className={isSelected ? "pl-4 pr-4 py-3" : "px-4 py-3"}>

        {/* ── Row 1: name + actions + status ── */}
        <div className="flex items-center gap-2 mb-1">
          <span className="font-mono font-semibold text-app-text text-ui-base leading-tight flex-1 truncate">
            {name}
          </span>

          {/* Actions: show on hover/selected */}
          <div
            className={`flex items-center gap-0.5 transition-opacity duration-150
              ${isSelected ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
            onClick={(e) => e.stopPropagation()}
          >
            <button onClick={startEdit} title="编辑描述"
              className="p-1 text-app-text-muted hover:text-app-text cursor-pointer rounded transition-colors">
              <Pencil size={12} />
            </button>
            {confirmDelete ? (
              <>
                <button onClick={handleDelete} disabled={deleting}
                  className="px-1.5 py-0.5 text-ui-xs text-white bg-app-error rounded cursor-pointer hover:brightness-110 flex items-center gap-0.5">
                  {deleting ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                  确认
                </button>
                <button onClick={(e) => { e.stopPropagation(); setConfirmDelete(false); }}
                  className="p-1 text-app-text-muted hover:text-app-text cursor-pointer rounded">
                  <X size={12} />
                </button>
              </>
            ) : (
              <button onClick={handleDelete} title="删除项目"
                className="p-1 text-app-text-muted hover:text-app-error cursor-pointer rounded transition-colors">
                <Trash2 size={12} />
              </button>
            )}
          </div>

          {/* Status dot */}
          <span className={`flex items-center gap-1 text-ui-xs shrink-0 ${
            status === "running"   ? "text-app-warning" :
            status === "completed" ? "text-app-success"  :
            status === "guardrails_blocked" ? "text-app-warning" :
            "text-app-text-muted"
          }`}>
            <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
            {cfg.label}
          </span>
        </div>

        {/* ── Row 2: description (editable inline) ── */}
        {editingDesc ? (
          <div className="flex items-center gap-1.5 mt-1.5" onClick={(e) => e.stopPropagation()}>
            <input
              ref={descInputRef}
              type="text"
              value={descDraft}
              onChange={(e) => setDescDraft(e.target.value)}
              onKeyDown={(e) => {
                const ne = e.nativeEvent as unknown as { isComposing?: boolean; keyCode?: number };
                if (e.key === "Enter" && !e.nativeEvent.isComposing && ne.keyCode !== 229) {
                  saveDesc();
                }
                if (e.key === "Escape") cancelEdit();
              }}
              placeholder="一句话描述这个项目…"
              className="flex-1 px-2 py-1 text-ui-xs bg-app-bg border border-app-accent rounded
                         text-app-text placeholder-app-text-muted focus:outline-none"
            />
            <button onClick={saveDesc} disabled={savingDesc}
              className="p-1 text-app-success cursor-pointer disabled:opacity-50">
              {savingDesc ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
            </button>
            <button onClick={cancelEdit} className="p-1 text-app-text-muted hover:text-app-text cursor-pointer">
              <X size={12} />
            </button>
          </div>
        ) : detail?.description ? (
          <div className="mt-1 text-ui-xs text-app-text-muted leading-relaxed line-clamp-1">
            {detail.description}
          </div>
        ) : !loading ? (
          <button onClick={startEdit}
            className={`mt-1 text-ui-xs italic cursor-pointer transition-colors
              ${isSelected ? "text-app-text-muted/60 hover:text-app-accent" : "opacity-0 group-hover:opacity-100 text-app-text-muted/40 hover:text-app-text-muted"}`}>
            + 添加描述
          </button>
        ) : null}

        {/* ── Row 3: compact stats + last query ── */}
        {!loading && (
          <div className="mt-2 flex items-center gap-3 text-ui-xs text-app-text-muted font-mono">
            <span className="flex items-center gap-1">
              <BarChart3 size={10} />
              {detail?.run_count ?? 0} 次
            </span>
            {detail?.last_run_at && (
              <span className="flex items-center gap-1">
                <Clock size={10} />
                {fmtRunId(detail.last_run_at)}
              </span>
            )}
            {detail?.last_query && (
              <span className="truncate flex-1 opacity-60" title={detail.last_query}>
                · {detail.last_query}
              </span>
            )}
          </div>
        )}
        {loading && <div className="mt-2 h-3 w-24 bg-app-bg-tertiary rounded animate-pulse" />}
      </div>
    </div>
  );
}

export default function ProjectPanel() {
  const { send } = useWebSocket();
  const projects = useWorkspaceStore((s) => s.projects);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const agents = useWorkspaceStore((s) => s.agents);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);

  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [nameError, setNameError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  /** 避免并发 / 重入 fetch 时前一个请求的 finally 把 loading 提前清掉，或后序请求被盖住一直转圈 */
  const projectsFetchRef = useRef<AbortController | null>(null);

  useAgentStatusSync();
  const batch = useBatchEvents();

  const loadProjects = useCallback(() => {
    projectsFetchRef.current?.abort();
    const ac = new AbortController();
    projectsFetchRef.current = ac;
    setLoading(true);
    setLoadError(null);
    const tid = window.setTimeout(() => ac.abort(), 15_000);

    fetch("/api/projects", { signal: ac.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        if (projectsFetchRef.current !== ac) return;
        const list = d?.projects;
        useWorkspaceStore.getState().setProjects(Array.isArray(list) ? (list as string[]) : []);
      })
      .catch((e: unknown) => {
        if (projectsFetchRef.current !== ac) return;
        const aborted =
          (e instanceof DOMException && e.name === "AbortError") ||
          (e instanceof Error && e.name === "AbortError");
        setLoadError(
          aborted
            ? "HaGoKu Studio 分析服务连接超时，请确认服务已启动后刷新页面。"
            : "无法连接到 HaGoKu Studio 分析服务，请确认服务已启动后刷新页面。",
        );
      })
      .finally(() => {
        window.clearTimeout(tid);
        if (projectsFetchRef.current === ac) {
          projectsFetchRef.current = null;
          setLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // Refresh cards after a run completes (run count changes)
  useEffect(() => {
    for (const msg of batch) {
      if (msg.type === "event" && msg.data?.event_type === "run_completed") {
        loadProjects();
        break;
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batch]);

  const NAME_RE = /^[a-zA-Z0-9_-]+$/;

  const validateName = (v: string) => {
    if (!v.trim()) { setNameError(""); return false; }
    if (!NAME_RE.test(v.trim())) {
      setNameError("只允许英文字母、数字、下划线和连字符");
      return false;
    }
    setNameError("");
    return true;
  };

  const handleCreate = async () => {
    if (!validateName(newName) || !newName.trim() || creating) return;
    setCreating(true);
    try {
      await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() }),
      });
      setCurrentProject(newName.trim());
      setNewName("");
      setNewDesc("");
      setNameError("");
      setShowForm(false);
      loadProjects();
    } finally {
      setCreating(false);
    }
  };

  const isAgentRunning = Object.values(agents).some((s) => s === "running");

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text">
      <PanelHeader title="项目">
        <button
          onClick={() => { setShowForm((v) => !v); }}
          className="flex items-center gap-1 px-2 py-0.5 text-ui-xs bg-app-accent
                     hover:bg-app-accent-hover text-white rounded transition-colors duration-150 cursor-pointer"
        >
          <Plus size={12} />
          新建项目
        </button>
      </PanelHeader>

      {/* Summary bar */}
      {(projects?.length ?? 0) > 0 && (
        <div className="flex items-center gap-4 px-4 py-2 border-b border-app-border text-ui-xs text-app-text-muted bg-app-bg-secondary">
          <span>{projects?.length ?? 0} 个项目</span>
          {currentProject && (
            <span className="text-app-accent font-mono">当前: {currentProject}</span>
          )}
          {isAgentRunning && (
            <span className="text-app-warning flex items-center gap-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-app-warning animate-pulse" />
              分析运行中
            </span>
          )}
        </div>
      )}

      {/* New project inline form */}
      {showForm && (
        <div className="px-4 py-3 border-b border-app-border bg-app-bg-secondary space-y-2">
          <div className="text-ui-xs text-app-text-muted">新建项目</div>

          {/* Name field */}
          <div>
            <input
              autoFocus
              type="text"
              aria-label="新项目名称"
              value={newName}
              onChange={(e) => { setNewName(e.target.value); validateName(e.target.value); }}
              onKeyDown={(e) => {
                const ne = e.nativeEvent as unknown as { isComposing?: boolean; keyCode?: number };
                if (e.key === "Enter" && !e.nativeEvent.isComposing && ne.keyCode !== 229) {
                  handleCreate();
                }
                if (e.key === "Escape") { setShowForm(false); setNewName(""); setNewDesc(""); setNameError(""); }
              }}
              placeholder="项目名称，如 q4_sales_analysis"
              className={`w-full px-2.5 py-1.5 text-ui-sm bg-app-bg border rounded font-mono
                         text-app-text placeholder-app-text-muted focus:outline-none
                         focus-visible:ring-1 focus-visible:ring-app-accent
                         ${nameError ? "border-app-error" : "border-app-border focus:border-app-accent"}`}
            />
            {nameError && (
              <p className="mt-1 text-ui-xs text-app-error">{nameError}</p>
            )}
          </div>

          {/* Description field */}
          <input
            type="text"
            aria-label="项目描述"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            onKeyDown={(e) => {
              const ne = e.nativeEvent as unknown as { isComposing?: boolean; keyCode?: number };
              if (e.key === "Enter" && !e.nativeEvent.isComposing && ne.keyCode !== 229) {
                handleCreate();
              }
              if (e.key === "Escape") { setShowForm(false); setNewName(""); setNewDesc(""); setNameError(""); }
            }}
            placeholder="描述这个项目（可选）"
            className="w-full px-2.5 py-1.5 text-ui-sm bg-app-bg border border-app-border rounded
                       text-app-text placeholder-app-text-muted focus:outline-none
                       focus:border-app-accent focus-visible:ring-1 focus-visible:ring-app-accent"
          />

          <div className="flex gap-2 pt-1">
            <button
              onClick={handleCreate}
              disabled={creating || !newName.trim() || !!nameError}
              className="px-3 py-1.5 text-ui-sm bg-app-accent hover:bg-app-accent-hover text-white rounded
                         flex items-center gap-1 transition-colors duration-150 cursor-pointer
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
              创建项目
            </button>
            <button
              onClick={() => { setShowForm(false); setNewName(""); setNewDesc(""); setNameError(""); }}
              className="px-2 py-1.5 text-ui-xs text-app-text-muted hover:text-app-text
                         border border-app-border rounded cursor-pointer transition-colors duration-150"
            >
              取消
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-auto p-4 space-y-3">
        {loading && (
          <div className="flex items-center gap-2 justify-center py-8 text-app-text-muted">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-ui-sm">加载中…</span>
          </div>
        )}

        {loadError && (
          <div className="flex items-center gap-2 px-3 py-2 bg-app-status-error text-app-error text-ui-xs rounded border border-app-error/30">
            <XCircle size={13} />
            <span className="flex-1">{loadError}</span>
            <button onClick={loadProjects} className="underline cursor-pointer hover:no-underline">重试</button>
          </div>
        )}

        {!projects?.length && !loading && !loadError && (
          <div className="flex flex-col items-center py-20 gap-4 text-app-text-muted select-none">
            <FolderOpen size={48} strokeWidth={1} className="text-app-accent/40" />
            <div className="text-center space-y-1">
              <div className="text-ui-base text-app-text font-semibold">还没有项目</div>
              <div className="text-ui-xs">点击右上角「新建项目」开始你的第一个分析</div>
            </div>
          </div>
        )}

        {projects.map((p) => (
          <ProjectCard
            key={p}
            name={p}
            isSelected={p === currentProject}
            isRunning={isAgentRunning && p === currentProject}
            onSelect={() => {
              if (p !== currentProject) {
                setCurrentProject(p);
                send("switch_project", { project: p });
              }
            }}
            onDeleted={() => {
              if (currentProject === p) setCurrentProject(null);
              loadProjects();
            }}
          />
        ))}
      </div>
    </div>
  );
}
