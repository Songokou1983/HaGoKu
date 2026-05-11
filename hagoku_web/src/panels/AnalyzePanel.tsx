import { useState, useCallback, useEffect, useRef } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { ScoutConfirmPanel, type ScoutPendingData } from "../components/ScoutConfirmPanel";
import {
  Loader2, WifiOff, Search, Sparkles, BarChart2, FileText,
  ArrowRight, FolderOpen, Upload, ChevronDown, CheckCircle2, X,
  PlayCircle, RotateCcw, Clock,
} from "lucide-react";

// ── Agent pipeline definition ─────────────────────────────────
const PIPELINE_AGENTS = [
  { key: "scout",    label: "Scout",    icon: Search,    desc: "理解数据" },
  { key: "cleaner",  label: "Cleaner",  icon: Sparkles,  desc: "清洗数据" },
  { key: "analyst",  label: "Analyst",  icon: BarChart2, desc: "统计分析" },
  { key: "reporter", label: "Reporter", icon: FileText,  desc: "生成报告" },
] as const;

type AgentKey = typeof PIPELINE_AGENTS[number]["key"];
type AgentRunState = "idle" | "running" | "done" | "error";

// Map raw WS event agent names → pipeline keys
function resolveAgentKey(raw: string): AgentKey | null {
  const s = raw.toLowerCase();
  if (s.includes("scout"))    return "scout";
  if (s.includes("clean"))    return "cleaner";
  if (s.includes("analys"))   return "analyst";
  if (s.includes("report"))   return "reporter";
  return null;
}

// Human-readable event descriptions
function describeEvent(agent: string, eventType: string): string {
  const key = resolveAgentKey(agent);
  const label = PIPELINE_AGENTS.find(p => p.key === key)?.label ?? agent;
  switch (eventType) {
    case "agent_started":         return `${label} 开始工作…`;
    case "agent_completed":       return `${label} 完成`;
    case "agent_failed":          return `${label} 遇到问题`;
    case "user_input_requested":  return `${label} 需要您确认`;
    case "analysis_started":      return "分析流程启动";
    case "analysis_completed":    return "🎉 分析完成！";
    default:                      return `${label}：${eventType.replace(/_/g, " ")}`;
  }
}

// ── Types ────────────────────────────────────────────────────
type SessionPhase = "setup" | "query" | "running" | "done";

interface ConvoMessage {
  id: string;
  role: "system" | "user" | "agent";
  text: string;
  timestamp: string;
}

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

let _idCtr = 0;
function uid() { return `m-${++_idCtr}-${Date.now()}`; }

// ── Pipeline status bar ───────────────────────────────────────
function PipelineBar({ states, elapsed }: {
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

// ── Conversation feed ─────────────────────────────────────────
function ConvoFeed({ messages }: { messages: ConvoMessage[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
      {messages.map((m) => (
        <div
          key={m.id}
          className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[85%] px-3 py-2 rounded-lg text-ui-sm leading-relaxed
              ${m.role === "user"
                ? "bg-app-accent text-white rounded-br-sm"
                : m.role === "agent"
                ? "bg-app-bg-secondary border border-app-border text-app-text rounded-bl-sm"
                : "bg-transparent text-app-text-muted text-ui-xs italic"
              }`}
          >
            {m.text}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────
export default function AnalyzePanel() {
  const { send } = useWebSocket();
  const status = useWorkspaceStore((s) => s.status);
  const connectionStatus = useWorkspaceStore((s) => s.connectionStatus);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const projects = useWorkspaceStore((s) => s.projects);
  const setActiveView = useWorkspaceStore((s) => s.setActiveView);

  // Session state machine
  const [phase, setPhase] = useState<SessionPhase>("setup");
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<ConvoMessage[]>([]);
  const [agentStates, setAgentStates] = useState<Record<AgentKey, AgentRunState>>({
    scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle",
  });
  const [agentElapsed, setAgentElapsed] = useState<Record<AgentKey, number>>({
    scout: 0, cleaner: 0, analyst: 0, reporter: 0,
  });
  const agentStartTimes = useRef<Record<string, number>>({});
  const [pendingScout, setPendingScout] = useState<ScoutPendingData | null>(null);
  const [resultReportUrl, setResultReportUrl] = useState<string | null>(null);

  // File / project state
  const [dataPath, setDataPath] = useState("");
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [showFileDropdown, setShowFileDropdown] = useState(false);
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const projectDropdownRef = useRef<HTMLDivElement>(null);
  const queryRef = useRef<HTMLTextAreaElement>(null);

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node))
        setShowFileDropdown(false);
      if (projectDropdownRef.current && !projectDropdownRef.current.contains(e.target as Node))
        setShowProjectDropdown(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  const loadFiles = useCallback((proj: string) => {
    setFilesLoading(true);
    fetch(`/api/projects/${proj}/files`)
      .then((r) => r.json())
      .then((d: { files: ProjectFile[] }) => setProjectFiles(d.files ?? []))
      .catch(() => setProjectFiles([]))
      .finally(() => setFilesLoading(false));
  }, []);

  useEffect(() => {
    if (!currentProject) { setDataPath(""); setProjectFiles([]); return; }
    loadFiles(currentProject);
    fetch(`/api/projects/${currentProject}/detail`)
      .then((r) => r.json())
      .then((d: { data_path?: string }) => { if (d.data_path) setDataPath(d.data_path); })
      .catch(() => {});
  }, [currentProject, loadFiles]);

  useAgentStatusSync();
  const batch = useBatchEvents();

  // Process WS events
  useEffect(() => {
    if (batch.length === 0) return;
    for (const msg of batch) {
      if (msg.type === "event" && msg.data) {
        const d = msg.data;
        const agentKey = resolveAgentKey(d.agent);

        // Agent lifecycle → update pipeline
        if (d.event_type === "agent_started" && agentKey) {
          agentStartTimes.current[agentKey] = Date.now();
          setAgentStates((prev) => ({ ...prev, [agentKey]: "running" }));
        }
        if (d.event_type === "agent_completed" && agentKey) {
          const elapsed = Math.round((Date.now() - (agentStartTimes.current[agentKey] ?? Date.now())) / 1000);
          setAgentStates((prev) => ({ ...prev, [agentKey]: "done" }));
          setAgentElapsed((prev) => ({ ...prev, [agentKey]: elapsed }));
        }
        if (d.event_type === "agent_failed" && agentKey) {
          setAgentStates((prev) => ({ ...prev, [agentKey]: "error" }));
        }

        // Scout confirmation request
        if (d.event_type === "user_input_requested" && d.agent === "scout") {
          setPendingScout(d.data as unknown as ScoutPendingData);
        }

        // Reporter done → show report
        if (d.agent === "reporter" && d.event_type === "agent_completed") {
          const proj = (d.data as Record<string, unknown>)?.project_name as string ?? currentProject ?? "default";
          setResultReportUrl(`/api/reports/${proj}`);
          setPhase("done");
        }

        // Human-readable conversation entry
        const human = describeEvent(d.agent, d.event_type);
        setMessages((prev) => [
          ...prev,
          { id: uid(), role: "agent", text: human, timestamp: d.timestamp },
        ]);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batch]);

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
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "user", text: "已确认字段含义", timestamp: new Date().toISOString() },
      ]);
    },
    [send, pendingScout, currentProject],
  );

  const handleStartSession = useCallback(() => {
    if (!currentProject || !dataPath) return;
    setPhase("query");
    setTimeout(() => queryRef.current?.focus(), 100);
    setMessages([
      {
        id: uid(),
        role: "agent",
        text: `项目「${currentProject}」已就绪，数据文件已加载。\n\n请告诉我您想分析什么？`,
        timestamp: new Date().toISOString(),
      },
    ]);
  }, [currentProject, dataPath]);

  const handleSubmitQuery = useCallback(() => {
    const q = query.trim();
    if (!q) return;
    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "user", text: q, timestamp: new Date().toISOString() },
      { id: uid(), role: "agent", text: "收到，正在启动分析流程…", timestamp: new Date().toISOString() },
    ]);
    setAgentStates({ scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" });
    setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
    setPhase("running");
    setQuery("");
    send("analyze", { data_path: dataPath, query: q, project_name: currentProject ?? "default", phase: "full" });
  }, [query, send, dataPath, currentProject]);

  const handleReset = useCallback(() => {
    setPhase("setup");
    setMessages([]);
    setQuery("");
    setPendingScout(null);
    setResultReportUrl(null);
    setAgentStates({ scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" });
    setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
  }, []);

  const handleUpload = useCallback(async (file: File) => {
    if (!currentProject) return;
    setUploading(true);
    setUploadError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`/api/projects/${currentProject}/upload`, { method: "POST", body: form });
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
  const canStart = !!currentProject && !!dataPath && connectionStatus === "connected";

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text">
      <PanelHeader title="分析" />

      {/* ── Connection overlay ── */}
      {connectionStatus === "disconnected" && (
        <div className="absolute inset-0 bg-app-bg/90 flex flex-col items-center justify-center gap-2 z-20">
          <WifiOff size={28} className="text-app-text-muted" />
          <span className="text-ui-base text-app-error">连接断开</span>
          <span className="text-ui-xs text-app-text-muted">正在重新连接…</span>
        </div>
      )}
      {(connectionStatus === "connecting" || connectionStatus === "reconnecting") && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-app-bg/80 backdrop-blur-sm">
          <Loader2 size={20} className="animate-spin text-app-accent" />
          <span className="text-ui-sm text-app-text-muted">正在连接服务器…</span>
        </div>
      )}

      {/* ── Setup: project + file selectors ── */}
      <div className="px-3 py-2 border-b border-app-border bg-app-bg-secondary shrink-0 space-y-2">
        {/* Project selector */}
        <div className="flex items-center gap-2">
          <span className="text-ui-xs text-app-text-muted w-12 shrink-0">项目</span>
          <div className="relative flex-1" ref={projectDropdownRef}>
            <button
              onClick={() => setShowProjectDropdown((v) => !v)}
              disabled={phase === "running"}
              className={`w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border rounded
                         text-ui-sm transition-colors
                         ${phase !== "running"
                           ? "border-app-border hover:border-app-accent cursor-pointer text-app-text"
                           : "border-app-border opacity-50 cursor-not-allowed text-app-text-muted"}`}
            >
              <FolderOpen size={13} className="text-app-accent shrink-0" />
              <span className="flex-1 text-left truncate font-mono">{currentProject ?? "— 选择项目 —"}</span>
              <ChevronDown size={12} className="text-app-text-muted shrink-0" />
            </button>
            {showProjectDropdown && (
              <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-48 overflow-y-auto">
                {projects.length === 0
                  ? <div className="px-3 py-2 text-ui-xs text-app-text-muted">暂无项目</div>
                  : projects.map((p) => (
                    <button key={p} onClick={() => { setCurrentProject(p); setShowProjectDropdown(false); }}
                      className={`w-full text-left px-3 py-1.5 text-ui-sm font-mono hover:bg-app-bg cursor-pointer
                        ${p === currentProject ? "text-app-accent" : "text-app-text"}`}>
                      {p === currentProject && <CheckCircle2 size={11} className="inline mr-1.5 text-app-accent" />}
                      {p}
                    </button>
                  ))}
                <div className="border-t border-app-border">
                  <button onClick={() => { setShowProjectDropdown(false); setActiveView("projects"); }}
                    className="w-full text-left px-3 py-1.5 text-ui-xs text-app-accent hover:bg-app-bg cursor-pointer">
                    + 新建项目 →
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* File selector */}
        <div className="flex items-center gap-2">
          <span className="text-ui-xs text-app-text-muted w-12 shrink-0">数据</span>
          <div className="relative flex-1" ref={dropdownRef}>
            <button
              disabled={!currentProject || phase === "running"}
              onClick={() => setShowFileDropdown((v) => !v)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border rounded text-ui-sm transition-colors
                ${currentProject && phase !== "running"
                  ? "border-app-border hover:border-app-accent cursor-pointer text-app-text"
                  : "border-app-border opacity-40 cursor-not-allowed text-app-text-muted"}`}
            >
              <FileText size={13} className={selectedFileName ? "text-app-accent shrink-0" : "text-app-text-muted shrink-0"} />
              <span className="flex-1 text-left truncate font-mono text-ui-xs">{selectedFileName ?? "— 选择文件 —"}</span>
              {filesLoading
                ? <Loader2 size={12} className="animate-spin text-app-text-muted shrink-0" />
                : <ChevronDown size={12} className="text-app-text-muted shrink-0" />}
            </button>
            {showFileDropdown && currentProject && (
              <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-56 overflow-y-auto">
                {projectFiles.length === 0
                  ? <div className="px-3 py-3 text-ui-xs text-app-text-muted text-center">暂无数据文件，请上传</div>
                  : projectFiles.map((f) => (
                    <button key={f.path} onClick={() => { setDataPath(f.path); setShowFileDropdown(false); }}
                      className={`w-full text-left px-3 py-2 hover:bg-app-bg cursor-pointer border-b border-app-border/50 last:border-0
                        ${f.path === dataPath ? "text-app-accent" : "text-app-text"}`}>
                      <div className="flex items-center gap-2">
                        {f.path === dataPath && <CheckCircle2 size={11} className="text-app-accent shrink-0" />}
                        <span className="text-ui-xs font-mono truncate flex-1">{f.name}</span>
                        <span className="text-ui-xs text-app-text-muted shrink-0">{fmtSize(f.size)}</span>
                      </div>
                    </button>
                  ))}
              </div>
            )}
          </div>
          {/* Upload button */}
          <div className="relative shrink-0">
            <input ref={fileInputRef} type="file"
              accept=".csv,.tsv,.json,.jsonl,.xlsx,.xls,.parquet,.txt"
              className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              disabled={!currentProject || uploading || phase === "running"}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleUpload(f); }}
            />
            <button disabled={!currentProject || uploading || phase === "running"}
              className={`flex items-center gap-1 px-2 py-1.5 border rounded text-ui-xs transition-colors
                ${currentProject && !uploading && phase !== "running"
                  ? "border-app-accent text-app-accent hover:bg-app-accent hover:text-white cursor-pointer"
                  : "border-app-border text-app-text-muted opacity-40 cursor-not-allowed"}`}>
              {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
              {uploading ? "上传中…" : "上传"}
            </button>
          </div>
        </div>
        {uploadError && (
          <div className="flex items-center gap-1 text-ui-xs text-app-error">
            <X size={11} />{uploadError}
            <button onClick={() => setUploadError(null)} className="ml-auto text-app-text-muted hover:text-app-text cursor-pointer">忽略</button>
          </div>
        )}
      </div>

      {/* ── Setup idle: start button ── */}
      {phase === "setup" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6">
          {!currentProject || !dataPath ? (
            <div className="text-center space-y-2">
              <div className="text-app-text-muted text-ui-sm">
                {!currentProject ? "请先选择一个项目" : "请选择或上传数据文件"}
              </div>
              <div className="text-app-text-muted text-ui-xs">准备好后点击"开始分析"</div>
            </div>
          ) : (
            <div className="text-center space-y-2">
              <div className="text-ui-sm text-app-text-muted">项目和数据文件已就绪</div>
              <div className="text-ui-xs text-app-text-muted opacity-60">
                Agent 将引导您完成整个分析流程
              </div>
            </div>
          )}
          <button
            onClick={handleStartSession}
            disabled={!canStart}
            className={`flex items-center gap-2 px-6 py-3 rounded-lg text-ui-base font-medium transition-all duration-200
              ${canStart
                ? "bg-app-accent hover:bg-app-accent-hover text-white cursor-pointer shadow-lg hover:shadow-app-accent/30 hover:-translate-y-0.5"
                : "bg-app-bg-secondary border border-app-border text-app-text-muted cursor-not-allowed"}`}
          >
            <PlayCircle size={18} />
            开始分析
          </button>
        </div>
      )}

      {/* ── Query / running / done: conversation view ── */}
      {phase !== "setup" && (
        <>
          {/* Pipeline bar */}
          <div className="px-3 py-2 border-b border-app-border shrink-0">
            <PipelineBar states={agentStates} elapsed={agentElapsed} />
          </div>

          {/* Running progress bar */}
          {status === "running" && (
            <div className="h-0.5 bg-app-accent animate-pulse shrink-0" />
          )}

          {/* Conversation feed */}
          <ConvoFeed messages={messages} />

          {/* Scout confirmation */}
          {pendingScout && (
            <div className="px-3 pb-2 shrink-0">
              <ScoutConfirmPanel
                data={pendingScout}
                onConfirm={handleScoutConfirm}
                onSkip={() => setPendingScout(null)}
              />
            </div>
          )}

          {/* Query input (shown in query phase) */}
          {phase === "query" && (
            <div className="px-3 pb-3 shrink-0">
              <div className="flex gap-2 items-end">
                <textarea
                  ref={queryRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      if (query.trim()) handleSubmitQuery();
                    }
                  }}
                  placeholder="例如：广告投入对销售额有没有显著影响？"
                  rows={2}
                  className="flex-1 bg-app-bg-secondary border border-app-border rounded px-3 py-2
                             text-ui-sm text-app-text placeholder-app-text-muted resize-none
                             focus:outline-none focus:border-app-accent transition-colors"
                />
                <button
                  onClick={handleSubmitQuery}
                  disabled={!query.trim()}
                  className={`px-4 py-2 rounded text-ui-sm font-medium transition-colors shrink-0
                    ${query.trim()
                      ? "bg-app-accent hover:bg-app-accent-hover text-white cursor-pointer"
                      : "bg-app-bg-secondary border border-app-border text-app-text-muted cursor-not-allowed"}`}
                >
                  发送
                </button>
              </div>
              <div className="mt-1 text-ui-xs text-app-text-muted">Enter 发送 · Shift+Enter 换行</div>
            </div>
          )}

          {/* Done: report link + reset */}
          {phase === "done" && resultReportUrl && (
            <div className="mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-success rounded flex items-center justify-between gap-3 shrink-0">
              <div>
                <div className="text-ui-xs text-app-success font-semibold mb-0.5">分析完成</div>
                <div className="text-ui-sm text-app-text">报告已生成</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <a href={resultReportUrl} target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 bg-app-accent hover:bg-app-accent-hover text-white text-ui-xs rounded cursor-pointer transition-colors whitespace-nowrap flex items-center gap-1">
                  查看报告 <ArrowRight size={12} />
                </a>
                <button onClick={handleReset}
                  className="px-3 py-1.5 border border-app-border text-app-text-muted hover:text-app-text text-ui-xs rounded cursor-pointer transition-colors flex items-center gap-1">
                  <RotateCcw size={12} /> 再次分析
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
