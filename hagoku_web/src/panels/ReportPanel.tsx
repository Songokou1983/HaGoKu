import { FileText, Loader2, FolderOpen, ChevronDown, CheckCircle2, ShieldAlert, ArrowRight } from "lucide-react";
import { useEffect, useState, useCallback, useRef } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";

interface ProjectRun {
  run_id: string;
  query: string;
  status: string;
  report_url: string | null;
  guardrails_blocked: boolean;
  guardrails_notice_url: string | null;
}

export default function ReportPanel() {
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const activeView = useWorkspaceStore((s) => s.activeView);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const projects = useWorkspaceStore((s) => s.projects);
  const reportFiles = useWorkspaceStore((s) => s.reportFiles);
  const setReportFiles = useWorkspaceStore((s) => s.setReportFiles);
  const setActiveView = useWorkspaceStore((s) => s.setActiveView);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [runs, setRuns] = useState<ProjectRun[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useAgentStatusSync();
  const batch = useBatchEvents();

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const loadReportsOnly = useCallback(
    (proj: string) =>
      fetch(`/api/reports/${proj}`)
        .then((r) => r.json())
        .then((data) => setReportFiles(data.reports as { name: string; url: string; mtime: number }[]))
        .catch(() => setReportFiles([])),
    [setReportFiles],
  );

  const loadRunsOnly = useCallback((proj: string) => {
    return fetch(`/api/projects/${proj}/runs`)
      .then((r) => r.json())
      .then((data: { runs?: ProjectRun[] }) => setRuns(data.runs ?? []))
      .catch(() => setRuns([]));
  }, []);

  const refreshPanel = useCallback(
    async (proj: string) => {
      setLoading(true);
      setError(null);
      try {
        await Promise.all([loadReportsOnly(proj), loadRunsOnly(proj)]);
      } catch {
        setError("报告加载失败");
      } finally {
        setLoading(false);
      }
    },
    [loadReportsOnly, loadRunsOnly],
  );

  useEffect(() => {
    if (!currentProject) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshPanel(currentProject);
  }, [currentProject, refreshPanel]);

  // 切换到报告面板时自动刷新（报告可能在分析面板期间生成，run_completed 事件可能未触发）
  useEffect(() => {
    if (activeView === "report" && currentProject) {
      void refreshPanel(currentProject);
    }
  }, [activeView, currentProject, refreshPanel]);

  useEffect(() => {
    if (batch.length === 0 || !currentProject) return;
    let need = false;
    for (const msg of batch) {
      if (msg.type !== "event" || !msg.data) continue;
      const d = msg.data;
      if (
        d.event_type === "run_completed" ||
        (d.agent === "reporter" && d.event_type === "agent_completed")
      ) {
        need = true;
        break;
      }
    }
    if (need) void refreshPanel(currentProject);
  }, [batch, currentProject, refreshPanel]);

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="报告" />

      <div className="px-3 py-2 border-b border-app-border bg-app-bg-secondary shrink-0">
        <p className="text-ui-xs text-app-text-muted leading-relaxed mb-2">
          打开报告链接后，用浏览器的<strong>另存为</strong>（或打印为 PDF）即可保存到你想放的文件夹；无需在设置里选输出路径。
        </p>
        <div className="text-ui-xs text-app-text-muted mb-1">查看项目</div>
        <div className="relative" ref={dropdownRef}>
          <button
            type="button"
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
              {!projects?.length ? (
                <div className="px-3 py-2 text-ui-xs text-app-text-muted">暂无项目</div>
              ) : (
                projects.map((p) => (
                  <button
                    type="button"
                    key={p}
                    onClick={() => {
                      setCurrentProject(p);
                      setShowDropdown(false);
                    }}
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
                  type="button"
                  onClick={() => {
                    setShowDropdown(false);
                    setActiveView("projects");
                  }}
                  className="w-full text-left px-3 py-1.5 text-ui-xs text-app-accent hover:bg-app-bg cursor-pointer"
                >
                  + 新建项目 →
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-3">
        {!currentProject ? (
          <EmptyState icon={<FolderOpen size={32} />} message="请先选择一个项目以查看报告" />
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
                  type="button"
                  onClick={() => currentProject && void refreshPanel(currentProject)}
                  className="underline cursor-pointer hover:no-underline"
                >
                  重试
                </button>
              </div>
            )}

            {!loading && runs.length > 0 && (
              <div className="space-y-2 mb-4">
                <div className="text-ui-xs text-app-text-muted font-medium">按运行</div>
                {runs.map((run) => {
                  if (run.guardrails_blocked && run.guardrails_notice_url) {
                    return (
                      <div
                        key={run.run_id}
                        className="p-3 bg-app-bg-secondary border border-app-warning rounded flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="flex items-start gap-2 min-w-0 flex-1">
                          <ShieldAlert size={16} className="text-app-warning shrink-0 mt-0.5" />
                          <div className="min-w-0">
                            <div className="text-ui-sm font-medium text-app-warning">护栏未过 · {run.run_id}</div>
                            {run.query ? (
                              <div className="text-ui-xs text-app-text-muted truncate">{run.query}</div>
                            ) : null}
                            <div className="text-ui-xs text-app-text-muted mt-0.5">未生成正式 HTML 报告</div>
                          </div>
                        </div>
                        <a
                          href={run.guardrails_notice_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 px-3 py-1.5 bg-app-warning hover:bg-app-warning-hover text-white text-ui-xs rounded transition-colors whitespace-nowrap flex items-center justify-center gap-1"
                        >
                          <ShieldAlert size={12} />
                          查看护栏说明
                        </a>
                      </div>
                    );
                  }
                  if (run.status === "completed" && run.report_url) {
                    return (
                      <div
                        key={run.run_id}
                        className="p-3 bg-app-bg-secondary border border-app-border rounded flex items-center gap-2 hover:border-app-accent transition-colors group"
                      >
                        <FileText size={14} className="text-app-accent shrink-0" />
                        <span className="text-ui-sm text-app-text flex-1 truncate">
                          报告 · {run.run_id}
                          {run.query ? ` — ${run.query}` : ""}
                        </span>
                        <a
                          href={run.report_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 px-2 py-1 text-ui-xs text-app-accent hover:underline cursor-pointer"
                        >
                          查看
                        </a>
                        <button
                          type="button"
                          onClick={() => {
                            const printUrl = run.report_url!.replace(".html", "_print.html");
                            const api = window.hagokuDesktop;
                            if (api) api.printUrl(printUrl);
                            else window.open(printUrl, '_blank');
                          }}
                          className="shrink-0 px-2 py-1 text-ui-xs text-app-text-muted hover:text-app-text cursor-pointer"
                          title="打印为 PDF"
                        >
                          PDF
                        </button>
                        <button
                          type="button"
                          onClick={async () => {
                            if (!confirm('确定删除此报告？')) return;
                            const url = run.report_url!.replace('/api/reports/', '');
                            const parts = url.split('/');
                            const delUrl = `/api/reports/${parts[0]}/${parts[1]}/${parts[2]}`;
                            try {
                              const r = await fetch(delUrl, { method: 'DELETE' });
                              if (r.ok) refreshPanel(currentProject!);
                            } catch {}
                          }}
                          className="shrink-0 px-2 py-1 text-ui-xs text-app-text-muted hover:text-red-500 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
                          title="删除报告"
                        >
                          删除
                        </button>
                      </div>
                    );
                  }
                  return (
                    <div
                      key={run.run_id}
                      className="p-3 bg-app-bg-secondary border border-app-border rounded text-ui-xs text-app-text-muted"
                    >
                      <span className="font-mono">{run.run_id}</span>
                      {run.query ? ` · ${run.query}` : ""}
                      <span className="block mt-1">暂无 HTML 报告（状态：{run.status}）</span>
                    </div>
                  );
                })}
              </div>
            )}

            {!loading && reportFiles.length > 0 && (
              <div className="space-y-2">
                <div className="text-ui-xs text-app-text-muted font-medium">所有报告版本（最新在前）</div>
                {reportFiles.map((f) => {
                  const parts = f.name.split("/");
                  const displayName = parts.length > 1 ? f.name : f.name;
                  return (
                    <div
                      key={f.name}
                      className="p-3 bg-app-bg-secondary border border-app-border rounded flex items-center gap-2 hover:border-app-accent transition-colors group"
                    >
                      <FileText size={14} className="text-app-accent shrink-0" />
                      <span className="text-ui-sm text-app-text flex-1 truncate" title={displayName}>
                        {displayName}
                      </span>
                      <span className="text-ui-xs text-app-text-muted shrink-0 mr-2">
                        {new Date(f.mtime * 1000).toLocaleString("zh-CN")}
                      </span>
                      <a
                        href={f.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="shrink-0 px-2 py-1 text-ui-xs text-app-accent hover:underline cursor-pointer"
                      >
                        查看
                      </a>
                      <button
                        type="button"
                        onClick={() => {
                          const printUrl = f.url.replace(".html", "_print.html");
                          const api = window.hagokuDesktop;
                          if (api) api.printUrl(printUrl);
                          else window.open(printUrl, '_blank');
                        }}
                        className="shrink-0 px-2 py-1 text-ui-xs text-app-text-muted hover:text-app-text cursor-pointer"
                      >
                        PDF
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          if (!confirm('确定删除此报告？')) return;
                          const url = f.url.replace('/api/reports/', '');
                          const segs = url.split('/');
                          const delUrl = `/api/reports/${segs[0]}/${segs[1]}/${segs[2]}`;
                          try {
                            const r = await fetch(delUrl, { method: 'DELETE' });
                            if (r.ok) refreshPanel(currentProject!);
                          } catch {}
                        }}
                        className="shrink-0 px-2 py-1 text-ui-xs text-app-text-muted hover:text-red-500 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        删除
                      </button>
                    </div>
                  );
                })}
              </div>
            )}

            {!loading && runs.length === 0 && reportFiles.length === 0 && (
              <EmptyState icon={<FileText size={32} />} message="运行分析后，报告或护栏说明会出现在这里" />
            )}
          </>
        )}
      </div>
    </div>
  );
}
