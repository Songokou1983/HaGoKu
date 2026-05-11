import { BookOpen, Loader2 } from "lucide-react";
import { useState, useEffect, useCallback } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";

interface KnowledgeEntry {
  key: string;
  title: string;
  tags: string[];
}

export default function KnowledgePanel() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useAgentStatusSync();

  const loadKnowledge = useCallback((proj: string) => {
    setLoading(true);
    setError(null);
    fetch(`/api/knowledge/${proj}`)
      .then((r) => r.json())
      .then((d) => setEntries(
        (d.entries as string[]).map((k) => ({ key: k, title: k, tags: [] as string[] }))
      ))
      .catch(() => setError("知识库加载失败"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!currentProject) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: clear entries when project is null
      setEntries([]); return;
    }
    loadKnowledge(currentProject);
  }, [currentProject, loadKnowledge]);

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="Knowledge" />
      <div className="flex-1 overflow-auto p-3">
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
              onClick={() => currentProject && loadKnowledge(currentProject)}
              className="underline cursor-pointer hover:no-underline"
            >
              重试
            </button>
          </div>
        )}
        {entries.length === 0 && !loading ? (
          <EmptyState
            icon={<BookOpen size={32} />}
            message="分析完成后，Scout 会自动学习字段含义并存入知识库"
          />
        ) : (
          <div className="space-y-2">
            {entries.map((e) => (
              <div
                key={e.key}
                className="p-2 bg-app-bg-secondary border border-app-border rounded flex items-center gap-2"
              >
                <BookOpen size={14} className="text-app-accent shrink-0" />
                <span className="text-ui-base text-app-text">{e.title}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
