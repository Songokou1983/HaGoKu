import {
  BookOpen,
  Loader2,
  BarChart3,
  DollarSign,
  TrendingUp,
  ArrowLeft,
  FileText,
  ArrowRight,
} from "lucide-react";
import { useState, useEffect, useCallback, type ReactNode } from "react";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";
import { sanitizeHtml } from "../utils/sanitize";

interface KbEntry {
  title: string;
  category: string;
  tags: string[];
  summary: string;
  filename: string;
}

interface KbDetailPayload {
  filename: string;
  title: string;
  category: string;
  tags: string[];
  summary: string;
  html: string;
}

const CATEGORY_LABEL: Record<string, string> = {
  stats: "统计学",
  financial: "财务",
  business: "业务分析",
};

const CATEGORY_ICON: Record<string, ReactNode> = {
  stats: <BarChart3 size={13} className="shrink-0" />,
  financial: <DollarSign size={13} className="shrink-0" />,
  business: <TrendingUp size={13} className="shrink-0" />,
};

const CATEGORY_COLOR: Record<string, string> = {
  stats: "text-app-accent bg-app-running",
  financial: "text-app-success bg-app-done",
  business: "text-app-warning bg-app-status-waiting",
};

export default function KnowledgePanel() {
  const [entries, setEntries] = useState<KbEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  const [view, setView] = useState<"list" | "detail">("list");
  const [detailMeta, setDetailMeta] = useState<KbEntry | null>(null);
  const [detailHtml, setDetailHtml] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch("/api/kb")
      .then((r) => r.json())
      .then((d: { entries: KbEntry[] }) => setEntries(d.entries))
      .catch(() => setError("知识库加载失败"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = (e: KbEntry) => {
    setDetailMeta(e);
    setView("detail");
    setDetailHtml("");
    setDetailError(null);
    setDetailLoading(true);
    const q = new URLSearchParams({ filename: e.filename });
    fetch(`/api/kb/content?${q.toString()}`)
      .then(async (r) => {
        if (!r.ok) {
          const t = await r.text();
          throw new Error(t || `加载失败 (${r.status})`);
        }
        return r.json() as Promise<KbDetailPayload>;
      })
      .then((d) => setDetailHtml(d.html))
      .catch((err: unknown) => {
        setDetailError(err instanceof Error ? err.message : "正文加载失败");
      })
      .finally(() => setDetailLoading(false));
  };

  const closeDetail = () => {
    setView("list");
    setDetailMeta(null);
    setDetailHtml("");
    setDetailError(null);
  };

  const categories = ["all", ...Array.from(new Set(entries.map((e) => e.category)))];
  const visible = filter === "all" ? entries : entries.filter((e) => e.category === filter);

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text">
      <PanelHeader title="知识库" />

      {view === "list" && (
        <>
          <div className="px-3 py-2 border-b border-app-border flex gap-1 flex-wrap shrink-0">
            {categories.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setFilter(cat)}
                className={`px-2 py-0.5 text-ui-xs rounded border transition-colors duration-150 cursor-pointer
                  ${
                    filter === cat
                      ? "bg-app-accent border-app-accent text-white"
                      : "bg-app-bg-secondary border-app-border text-app-text-muted hover:text-app-text"
                  }`}
              >
                {cat === "all" ? "全部" : CATEGORY_LABEL[cat] ?? cat}
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
                <button type="button" onClick={load} className="underline cursor-pointer hover:no-underline">
                  重试
                </button>
              </div>
            )}
            {visible.length === 0 && !loading ? (
              <EmptyState icon={<BookOpen size={32} />} message="暂无知识库条目" />
            ) : (
              <div className="space-y-2">
                {visible.map((e) => (
                  <button
                    key={e.filename}
                    type="button"
                    onClick={() => openDetail(e)}
                    className="w-full text-left p-3 bg-app-bg-secondary border border-app-border rounded
                               hover:border-app-accent transition-colors duration-150 cursor-pointer group"
                  >
                    <div className="flex items-start gap-2 mb-1">
                      <span
                        className={`text-ui-xs px-1.5 py-0.5 rounded flex items-center gap-1 shrink-0 ${
                          CATEGORY_COLOR[e.category] ?? "text-app-text-muted bg-app-bg-tertiary"
                        }`}
                      >
                        {CATEGORY_ICON[e.category]}
                        {CATEGORY_LABEL[e.category] ?? e.category}
                      </span>
                      <span className="text-ui-base text-app-text font-semibold leading-snug flex-1 min-w-0">
                        {e.title}
                      </span>
                    </div>
                    <p className="text-ui-xs text-app-text-muted leading-relaxed mb-1.5">{e.summary}</p>
                    <div className="flex flex-wrap gap-1 mb-2">
                      {e.tags.map((tag) => (
                        <span key={tag} className="text-ui-xs px-1.5 py-0.5 bg-app-bg-tertiary text-app-text-muted rounded">
                          {tag}
                        </span>
                      ))}
                    </div>
                    <span className="inline-flex items-center gap-1.5 text-ui-xs text-app-accent group-hover:text-app-accent-hover">
                      <FileText size={12} className="shrink-0" />
                      查看正文
                      <ArrowRight size={12} className="shrink-0 opacity-70" />
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {view === "detail" && detailMeta && (
        <>
          <div className="px-3 py-2 border-b border-app-border bg-app-bg-secondary shrink-0 space-y-2">
            <button
              type="button"
              onClick={closeDetail}
              className="flex items-center gap-2 px-2 py-1.5 rounded border border-app-border bg-app-bg hover:border-app-accent text-ui-sm text-app-text transition-colors cursor-pointer"
            >
              <ArrowLeft size={14} className="shrink-0 text-app-accent" />
              返回列表
            </button>
            <div>
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span
                  className={`text-ui-xs px-1.5 py-0.5 rounded flex items-center gap-1 shrink-0 ${
                    CATEGORY_COLOR[detailMeta.category] ?? "text-app-text-muted bg-app-bg-tertiary"
                  }`}
                >
                  {CATEGORY_ICON[detailMeta.category]}
                  {CATEGORY_LABEL[detailMeta.category] ?? detailMeta.category}
                </span>
                <h2 className="text-ui-md font-semibold text-app-text">{detailMeta.title}</h2>
              </div>
              <p className="text-ui-xs text-app-text-muted leading-relaxed">{detailMeta.summary}</p>
            </div>
          </div>

          <div className="flex-1 overflow-auto p-3 min-h-0">
            {detailLoading && (
              <div className="flex items-center justify-center py-8 gap-2">
                <Loader2 size={16} className="animate-spin text-app-accent" />
                <span className="text-ui-sm text-app-text-muted">加载正文…</span>
              </div>
            )}
            {detailError && (
              <div className="px-2 py-2 bg-app-status-error text-app-error text-ui-sm rounded mb-2">{detailError}</div>
            )}
            {!detailLoading && !detailError && detailHtml && (
              <article className="kb-detail-html" dangerouslySetInnerHTML={{ __html: sanitizeHtml(detailHtml) }} />
            )}
          </div>
        </>
      )}
    </div>
  );
}
