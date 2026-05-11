import { useState, useCallback, useEffect, useRef } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { LogView, type LogLine } from "../components/LogView";
import { InputBar } from "../components/InputBar";
import { ScoutConfirmPanel, type ScoutPendingData } from "../components/ScoutConfirmPanel";
import {
  Loader2, WifiOff, Search, Sparkles, BarChart2, FileText, Cpu,
  ArrowRight, FolderOpen, Upload, ChevronDown, CheckCircle2, X,
} from "lucide-react";

const MAX_LOG_LINES = 500;

const AGENT_ICON_MAP: Record<string, React.ReactNode> = {
  scout:    <Search size={12} />,
  cleaner:  <Sparkles size={12} />,
  analyst:  <BarChart2 size={12} />,
  reporter: <FileText size={12} />,
  manager:  <Cpu size={12} />,
  system:   <Cpu size={12} />,
};

function agentIcon(name: string): React.ReactNode {
  const key = name.replace(/_/g, " ").toLowerCase();
  for (const k of Object.keys(AGENT_ICON_MAP)) {
    if (key.includes(k)) return AGENT_ICON_MAP[k];
  }
  return <Cpu size={12} />;
}

let _msgIdCounter = 0;

interface ProjectFile {
  name: string;
  path: string;
  size: number;
  mtime: number;
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function AnalyzePanel() {
  const { send } = useWebSocket();
  const status = useWorkspaceStore((s) => s.status);
  const connectionStatus = useWorkspaceStore((s) => s.connectionStatus);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const projects = useWorkspaceStore((s) => s.projects);
  const setActiveView = useWorkspaceStore((s) => s.setActiveView);

  const [dataPath, setDataPath] = useState("");
  const [phase, setPhase] = useState<"full" | "scout_first">("full");
  const [pendingScout, setPendingScout] = useState<ScoutPendingData | null>(null);
  const [resultSummary, setResultSummary] = useState<{
    summary: string;
    reportUrl: string;
    project: string;
  } | null>(null);
  const [logs, setLogs] = useState<LogLine[]>([]);

  // File section state
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [showFileDropdown, setShowFileDropdown] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Project dropdown state
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);
  const projectDropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdowns on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowFileDropdown(false);
      }
      if (projectDropdownRef.current && !projectDropdownRef.current.contains(e.target as Node)) {
        setShowProjectDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Load project files when project changes
  const loadFiles = useCallback((proj: string) => {
    setFilesLoading(true);
    fetch(`/api/projects/${proj}/files`)
      .then((r) => r.json())
      .then((d: { files: ProjectFile[] }) => setProjectFiles(d.files ?? []))
      .catch(() => setProjectFiles([]))
      .finally(() => setFilesLoading(false));
  }, []);

  // Auto-fill data_path from project detail
  useEffect(() => {
    if (!currentProject) {
      setDataPath("");
      setProjectFiles([]);
      return;
    }
    loadFiles(currentProject);
    fetch(`/api/projects/${currentProject}/detail`)
      .then((r) => r.json())
      .then((d: { data_path?: string }) => {
        if (d.data_path) setDataPath(d.data_path);
      })
      .catch(() => {});
  }, [currentProject, loadFiles]);

  useAgentStatusSync();
  const batch = useBatchEvents();

  useEffect(() => {
    if (batch.length === 0) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLogs((prev) => {
      let next = prev;
      for (const msg of batch) {
        if (msg.type === "event" && msg.data) {
          const d = msg.data;
          if (d.event_type === "user_input_requested" && d.agent === "scout") {
            setPendingScout(d.data as unknown as ScoutPendingData);
          }
          const icon = agentIcon(d.agent);
          next = [
            ...next.slice(-(MAX_LOG_LINES - 1)),
            {
              id: d.event_id,
              text: <><span className="inline-flex items-center mr-1">{icon}</span>[{d.event_type}] {d.agent.replace(/_/g, " ")}</>,
              type: "event" as const,
              timestamp: d.timestamp,
            },
          ];
        }
        if (msg.type === "ack") {
          next = [
            ...next.slice(-(MAX_LOG_LINES - 1)),
            {
              id: `ack-${++_msgIdCounter}`,
              text: msg.message ?? "处理中…",
              type: "system" as const,
              timestamp: new Date().toISOString(),
            },
          ];
        }
      }
      return next;
    });
  }, [batch]);

  useEffect(() => {
    if (batch.length === 0) return;
    for (const msg of batch) {
      if (msg.type === "event" && msg.data) {
        const d = msg.data;
        if (d.agent === "reporter" && d.event_type === "agent_completed") {
          const proj = (d.data as Record<string, unknown>)?.project_name as string ?? currentProject ?? "default";
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setResultSummary({
            summary: (d.data as Record<string, unknown>)?.result_summary as string ?? "分析完成",
            reportUrl: `/api/reports/${proj}`,
            project: proj,
          });
        }
      }
    }
  }, [batch, currentProject]);

  const handleScoutConfirm = useCallback(
    (confirmedTypes: Record<string, string>) => {
      if (!pendingScout) return;
      send("respond", {
        user_input: {
          agent: "scout",
          phase: "confirm_fields",
          confirmed: confirmedTypes,
          data_path: pendingScout.data_path,
          query: pendingScout.query,
          context: pendingScout.context,
        },
        project_name: currentProject ?? "default",
      });
      setPendingScout(null);
    },
    [send, pendingScout, currentProject]
  );

  const handleSend = useCallback(
    (text: string) => {
      setResultSummary(null);
      setLogs([]);
      if (!dataPath.trim()) {
        setLogs((prev) => [
          ...prev.slice(-(MAX_LOG_LINES - 1)),
          {
            id: `sys-${++_msgIdCounter}`,
            text: "请先选择数据文件",
            type: "system" as const,
            timestamp: new Date().toISOString(),
          },
        ]);
        return;
      }
      setLogs((prev) => [
        ...prev.slice(-(MAX_LOG_LINES - 1)),
        {
          id: `user-${++_msgIdCounter}`,
          text: `[${dataPath}] ${text}`,
          type: "user" as const,
          timestamp: new Date().toISOString(),
        },
      ]);
      send("analyze", { data_path: dataPath, query: text, project_name: currentProject ?? "default", phase });
    },
    [send, dataPath, currentProject, phase],
  );

  const handleUpload = useCallback(async (file: File) => {
    if (!currentProject) return;
    setUploading(true);
    setUploadError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`/api/projects/${currentProject}/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "上传失败" }));
        throw new Error(err.detail ?? "上传失败");
      }
      const data = await res.json() as { path: string };
      setDataPath(data.path);
      loadFiles(currentProject);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [currentProject, loadFiles]);

  const selectedFileName = dataPath ? dataPath.split("/").pop() ?? dataPath : null;

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="分析" />

      {/* ── Project selector ── */}
      <div className="px-3 py-2 border-b border-app-border bg-app-bg-secondary shrink-0">
        <div className="text-ui-xs text-app-text-muted mb-1">当前项目</div>
        <div className="flex items-center gap-2">
          <div className="relative flex-1" ref={projectDropdownRef}>
            <button
              onClick={() => setShowProjectDropdown((v) => !v)}
              className="w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border border-app-border rounded
                         text-ui-sm text-app-text hover:border-app-accent transition-colors cursor-pointer"
            >
              <FolderOpen size={13} className="text-app-accent shrink-0" />
              <span className="flex-1 text-left truncate font-mono">
                {currentProject ?? "— 选择项目 —"}
              </span>
              <ChevronDown size={12} className="text-app-text-muted shrink-0" />
            </button>
            {showProjectDropdown && (
              <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-48 overflow-y-auto">
                {projects.length === 0 ? (
                  <div className="px-3 py-2 text-ui-xs text-app-text-muted">暂无项目</div>
                ) : (
                  projects.map((p) => (
                    <button
                      key={p}
                      onClick={() => { setCurrentProject(p); setShowProjectDropdown(false); }}
                      className={`w-full text-left px-3 py-1.5 text-ui-sm font-mono hover:bg-app-bg cursor-pointer
                        ${p === currentProject ? "text-app-accent" : "text-app-text"}`}
                    >
                      {p === currentProject && <CheckCircle2 size={11} className="inline mr-1.5 text-app-accent" />}
                      {p}
                    </button>
                  ))
                )}
                <div className="border-t border-app-border">
                  <button
                    onClick={() => { setShowProjectDropdown(false); setActiveView("projects"); }}
                    className="w-full text-left px-3 py-1.5 text-ui-xs text-app-accent hover:bg-app-bg cursor-pointer"
                  >
                    + 新建项目 →
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Data file selector ── */}
      <div className="px-3 py-2 border-b border-app-border shrink-0">
        <div className="text-ui-xs text-app-text-muted mb-1">数据文件</div>
        <div className="flex items-center gap-2">
          {/* File picker dropdown */}
          <div className="relative flex-1" ref={dropdownRef}>
            <button
              disabled={!currentProject}
              onClick={() => setShowFileDropdown((v) => !v)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border rounded
                         text-ui-sm transition-colors
                         ${currentProject
                           ? "border-app-border hover:border-app-accent cursor-pointer text-app-text"
                           : "border-app-border opacity-40 cursor-not-allowed text-app-text-muted"}`}
            >
              <FileText size={13} className={selectedFileName ? "text-app-accent shrink-0" : "text-app-text-muted shrink-0"} />
              <span className="flex-1 text-left truncate font-mono text-ui-xs">
                {selectedFileName ?? "— 选择文件 —"}
              </span>
              {filesLoading
                ? <Loader2 size={12} className="animate-spin text-app-text-muted shrink-0" />
                : <ChevronDown size={12} className="text-app-text-muted shrink-0" />
              }
            </button>
            {showFileDropdown && currentProject && (
              <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-56 overflow-y-auto">
                {projectFiles.length === 0 ? (
                  <div className="px-3 py-3 text-ui-xs text-app-text-muted text-center">
                    该项目暂无数据文件，请上传
                  </div>
                ) : (
                  projectFiles.map((f) => (
                    <button
                      key={f.path}
                      onClick={() => { setDataPath(f.path); setShowFileDropdown(false); }}
                      className={`w-full text-left px-3 py-2 hover:bg-app-bg cursor-pointer border-b border-app-border/50 last:border-0
                        ${f.path === dataPath ? "text-app-accent" : "text-app-text"}`}
                    >
                      <div className="flex items-center gap-2">
                        {f.path === dataPath && <CheckCircle2 size={11} className="text-app-accent shrink-0" />}
                        <span className="text-ui-xs font-mono truncate flex-1">{f.name}</span>
                        <span className="text-ui-xs text-app-text-muted shrink-0">{fmtSize(f.size)}</span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Upload button */}
          <div className="relative shrink-0">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.tsv,.json,.jsonl,.xlsx,.xls,.parquet,.txt"
              className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              disabled={!currentProject || uploading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleUpload(f);
              }}
            />
            <button
              disabled={!currentProject || uploading}
              className={`flex items-center gap-1 px-2 py-1.5 border rounded text-ui-xs transition-colors
                ${currentProject && !uploading
                  ? "border-app-accent text-app-accent hover:bg-app-accent hover:text-white cursor-pointer"
                  : "border-app-border text-app-text-muted opacity-40 cursor-not-allowed"}`}
            >
              {uploading
                ? <Loader2 size={12} className="animate-spin" />
                : <Upload size={12} />
              }
              {uploading ? "上传中…" : "上传"}
            </button>
          </div>
        </div>

        {/* Upload error */}
        {uploadError && (
          <div className="mt-1.5 flex items-center gap-1 text-ui-xs text-app-error">
            <X size={11} />
            {uploadError}
            <button onClick={() => setUploadError(null)} className="ml-auto text-app-text-muted hover:text-app-text cursor-pointer">忽略</button>
          </div>
        )}
      </div>

      {/* ── Mode toggle ── */}
      <div className="px-3 pt-2 pb-1 flex gap-1 shrink-0">
        {(["full", "scout_first"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setPhase(p)}
            className={`px-2 py-0.5 text-ui-xs rounded border transition-colors duration-150 cursor-pointer
              ${phase === p
                ? "bg-app-accent border-app-accent text-white"
                : "bg-app-bg-secondary border-app-border text-app-text-muted hover:text-app-text"
              }`}
          >
            {p === "full" ? "完整分析" : "分步执行"}
          </button>
        ))}
      </div>

      {/* ── Log area ── */}
      <div className="relative flex-1 overflow-hidden">
        {pendingScout && (
          <div className="p-3 border-b border-app-border">
            <ScoutConfirmPanel
              data={pendingScout}
              onConfirm={handleScoutConfirm}
              onSkip={() => setPendingScout(null)}
            />
          </div>
        )}
        <LogView lines={logs} />
        {resultSummary && (
          <div className="mt-2 mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-success rounded flex items-center justify-between gap-3">
            <div>
              <div className="text-ui-xs text-app-success font-semibold mb-0.5">分析完成</div>
              <div className="text-ui-sm text-app-text">{resultSummary.summary}</div>
            </div>
            <a
              href={resultSummary.reportUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 px-3 py-1 bg-app-accent hover:bg-app-accent-hover text-white
                         text-ui-xs rounded cursor-pointer transition-colors duration-150 whitespace-nowrap"
            >
              查看报告 <ArrowRight size={12} className="inline" />
            </a>
          </div>
        )}
        {status === "running" && (
          <div className="h-0.5 bg-app-accent animate-pulse" />
        )}
        {(connectionStatus === "connecting" || connectionStatus === "reconnecting") && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-app-bg/80 backdrop-blur-sm">
            <Loader2 size={20} className="animate-spin text-app-accent" />
            <span className="text-ui-sm text-app-text-muted">正在连接服务器…</span>
          </div>
        )}
        {connectionStatus === "disconnected" && (
          <div className="absolute inset-0 bg-app-bg/90 flex flex-col items-center justify-center gap-2 z-10">
            <WifiOff size={28} className="text-app-text-muted" />
            <span className="text-ui-base text-app-error">连接断开</span>
            <span className="text-ui-xs text-app-text-muted">正在重新连接…</span>
          </div>
        )}
      </div>
      <InputBar onSend={handleSend} disabled={status === "running"} />
    </div>
  );
}
