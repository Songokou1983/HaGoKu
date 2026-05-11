import { FileText } from "lucide-react";
import { useEffect, useState } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";

export default function ReportPanel() {
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const reportFiles = useWorkspaceStore((s) => s.reportFiles);
  const setReportFiles = useWorkspaceStore((s) => s.setReportFiles);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useAgentStatusSync();
  const batch = useBatchEvents();

  useEffect(() => {
    if (batch.length === 0) return;
    for (const msg of batch) {
      if (msg.type === "event" && msg.data) {
        const d = msg.data;
        if (d.agent === "reporter" && d.event_type === "agent_completed") {
          const proj = d.data?.project_name ?? currentProject ?? "default";
          // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch triggers intentional loading state
          setLoading(true);
           
          setError(null);
          fetch(`/api/reports/${proj}`)
            .then((r) => r.json())
            .then((data) => setReportFiles(data.reports as { name: string; url: string; mtime: number }[]))
            .catch(() => setError("报告加载失败"))
            .finally(() => setLoading(false));
        }
      }
    }
  }, [batch, currentProject, setReportFiles]);

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="Reports" />
      <div className="flex-1 overflow-auto p-3">
        {loading && (
          <div className="flex items-center justify-center py-4 gap-2">
            <div className="w-4 h-4 border border-app-accent border-t-transparent rounded-full animate-spin" />
            <span className="text-ui-sm text-app-text-muted">加载中…</span>
          </div>
        )}
        {error && (
          <div className="mb-2 px-2 py-1 bg-app-status-error text-app-error text-ui-xs rounded">
            {error}
          </div>
        )}
        {reportFiles.length === 0 && !loading ? (
          <EmptyState icon={<FileText size={32} />} message="No reports yet" />
        ) : (
          <div className="space-y-2">
            {reportFiles.map((f) => (
              <a
                key={f.name}
                href={f.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mb-2 p-3 bg-app-bg-secondary border border-app-border rounded
                           flex items-center gap-2 hover:border-app-accent transition-colors cursor-pointer"
              >
                <FileText size={14} className="text-app-accent shrink-0" />
                <span className="text-ui-base text-app-text flex-1 truncate">{f.name}</span>
                <span className="text-ui-xs text-app-text-muted shrink-0">
                  {new Date(f.mtime * 1000).toLocaleString()}
                </span>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}