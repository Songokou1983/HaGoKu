import { FileText, Loader2, FolderOpen, ChevronDown, CheckCircle2 } from "lucide-react";
import { useEffect, useState, useCallback, useRef } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";

export default function ReportPanel() {
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const projects = useWorkspaceStore((s) => s.projects);
  const reportFiles = useWorkspaceStore((s) => s.reportFiles);
  const setReportFiles = useWorkspaceStore((s) => s.setReportFiles);
  const setActiveView = useWorkspaceStore((s) => s.setActiveView);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useAgentStatusSync();
  const batch = useBatchEvents();

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const loadReports = useCallback((proj: string) => {
    setLoading(true);
    setError(null);
    fetch(`/api/reports/${proj}`)
      .then((r) => r.json())
      .then((data) => setReportFiles(data.reports as { name: string; url: string; mtime: number }[]))
      .catch(() => setError("报告加载失败"))
      .finally(() => setLoading(false));
  }, [setReportFiles]);

  useEffect(() => {
    if (!currentProject) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadReports(currentProject);
  }, [currentProject, loadReports]);

  useEffect(() => {
    if (batch.length === 0) return;
    for (const msg of batch) {
      if (msg.type === "event" && msg.data) {
        const d = msg.data;
        if (d.agent === "reporter" && d.event_type === "agent_completed") {
          const proj = ((d.data?.project_name as string) || currentProject || "default") as string;
          // eslint-disable-next-line react-hooks/set-state-in-effect
          loadReports(proj);
        }
      }
    }
  }, [batch, currentProject, loadReports]);

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="报告" />

      {/* ── Project selector ── */}
      <div className="px-3 py-2 border-b border-app-border bg-app-bg-secondary shrink-0">
        <div className="text-ui-xs text-app-text-muted mb-1">查看项目</div>
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setShowDropdown((v) => !v)}
            className="w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border border-app-border rounded
                       text-ui-sm text-app-text hover:border-app-accent transition-colors cursor-pointer"
          >
            <FolderOpen size={13} className="text-app-accent shrink-0" />
            <span className="flex-1 text-left truncate font-mono">
              {currentProject ?? "— 选择项目 —"}
            </span>
            <ChevronDown size={12} className="text-app-text-muted shrink-0" />
          </button>
          {showDropdown && (
            <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-48 overflow-y-auto">
              {projects.length === 0 ? (
                <div className="px-3 py-2 text-ui-xs text-app-text-muted">暂无项目</div>
              ) : (
                projects.map((p) => (
                  <button
                    key={p}
                    onClick={() => { setCurrentProject(p); setShowDropdown(false); }}
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
                  onClick={() => { setShowDropdown(false); setActiveView("projects"); }}
                  className="w-full text-left px-3 py-1.5 text-ui-xs text-app-accent hover:bg-app-bg cursor-pointer"
                >
                  + 新建项目 →
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Report list ── */}
      <div className="flex-1 overflow-auto p-3">
        {!currentProject ? (
          <EmptyState
            icon={<FolderOpen size={32} />}
            message="请先选择一个项目以查看报告"
          />
        ) : (
          <>
            {loading && (
              <div className="flex items-center justify-center py-4 gap-2">
                <Loader2 size={16} className="animate-spin text-app-accent" />
                <span className="text-ui-sm text-app-text-muted">加载中…</span>
              </div>
            )}
            {error && (
              <div className="mb-2 px-2 py-1 bg-app-status-error text-app-error text-ui-xs rounded flex items-center gap-2">
                <span className="flex-1">{error}</span>
                <button
                  onClick={() => currentProject && loadReports(currentProject)}
                  className="underline cursor-pointer hover:no-underline"
                >
                  重试
                </button>
              </div>
            )}
            {reportFiles.length === 0 && !loading ? (
              <EmptyState icon={<FileText size={32} />} message="运行分析后，报告会出现在这里" />
            ) : (
              <div className="space-y-2">
                {reportFiles.map((f) => (
                  <a
                    key={f.name}
                    href={f.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mb-2 p-3 bg-app-bg-secondary border border-app-border rounded
                               flex items-center gap-2 hover:border-app-accent transition-colors duration-150 cursor-pointer"
                  >
                    <FileText size={14} className="text-app-accent shrink-0" />
                    <span className="text-ui-base text-app-text flex-1 truncate">{f.name}</span>
                    <span className="text-ui-xs text-app-text-muted shrink-0">
                      {new Date(f.mtime * 1000).toLocaleString("zh-CN")}
                    </span>
                  </a>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
