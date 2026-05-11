import { BookOpen, Loader2, BarChart3, DollarSign, TrendingUp } from "lucide-react";
import { useState, useEffect } from "react";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";

interface KbEntry {
  title: string;
  category: string;
  tags: string[];
  summary: string;
  filename: string;
}

const CATEGORY_LABEL: Record<string, string> = {
  stats:     "统计学",
  financial: "财务",
  business:  "业务分析",
};

const CATEGORY_ICON: Record<string, React.ReactNode> = {
  stats:     <BarChart3 size={13} className="shrink-0" />,
  financial: <DollarSign size={13} className="shrink-0" />,
  business:  <TrendingUp size={13} className="shrink-0" />,
};

const CATEGORY_COLOR: Record<string, string> = {
  stats:     "text-app-accent bg-app-running",
  financial: "text-app-success bg-app-done",
  business:  "text-app-warning bg-app-status-waiting",
};

export default function KnowledgePanel() {
  const [entries, setEntries] = useState<KbEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  const load = () => {
    setLoading(true);
    setError(null);
    fetch("/api/kb")
      .then((r) => r.json())
      .then((d: { entries: KbEntry[] }) => setEntries(d.entries))
      .catch(() => setError("知识库加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const categories = ["all", ...Array.from(new Set(entries.map((e) => e.category)))];
  const visible = filter === "all" ? entries : entries.filter((e) => e.category === filter);

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text">
      <PanelHeader title="知识库" />

      {/* Category filter */}
      <div className="px-3 py-2 border-b border-app-border flex gap-1 flex-wrap shrink-0">
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`px-2 py-0.5 text-ui-xs rounded border transition-colors duration-150 cursor-pointer
              ${filter === cat
                ? "bg-app-accent border-app-accent text-white"
                : "bg-app-bg-secondary border-app-border text-app-text-muted hover:text-app-text"
              }`}
          >
            {cat === "all" ? "全部" : (CATEGORY_LABEL[cat] ?? cat)}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto p-3">
        {loading && (
          <div className="flex items-center justify-center py-6 gap-2">
            <Loader2 size={16} className="animate-spin text-app-accent" />
            <span className="text-ui-sm text-app-text-muted">加载中…</span>
          </div>
        )}
        {error && (
          <div className="mb-2 px-2 py-1 bg-app-status-error text-app-error text-ui-xs rounded flex items-center gap-2">
            <span className="flex-1">{error}</span>
            <button onClick={load} className="underline cursor-pointer hover:no-underline">重试</button>
          </div>
        )}
        {visible.length === 0 && !loading ? (
          <EmptyState
            icon={<BookOpen size={32} />}
            message="暂无知识库条目"
          />
        ) : (
          <div className="space-y-2">
            {visible.map((e) => (
              <div
                key={e.filename}
                className="p-3 bg-app-bg-secondary border border-app-border rounded"
              >
                <div className="flex items-start gap-2 mb-1">
                  <span className={`text-ui-xs px-1.5 py-0.5 rounded flex items-center gap-1 shrink-0 ${CATEGORY_COLOR[e.category] ?? "text-app-text-muted bg-app-bg-tertiary"}`}>
                    {CATEGORY_ICON[e.category]}
                    {CATEGORY_LABEL[e.category] ?? e.category}
                  </span>
                  <span className="text-ui-base text-app-text font-semibold leading-snug">{e.title}</span>
                </div>
                <p className="text-ui-xs text-app-text-muted leading-relaxed mb-1.5">{e.summary}</p>
                <div className="flex flex-wrap gap-1">
                  {e.tags.map((tag) => (
                    <span key={tag} className="text-ui-xs px-1.5 py-0.5 bg-app-bg-tertiary text-app-text-muted rounded">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
