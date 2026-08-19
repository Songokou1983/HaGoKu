/**
 * 量化数据集面板 — 列出 ~/.hagoku/datasets/ 下所有数据集卡，支持新建拉取、刷新、删除。
 *
 * 元数据来自 parquet metadata（ONE file），由后端 /api/quant/datasets 接口解析后吐出。
 * 不在前端维护任何额外状态文件。
 */
import { useCallback, useEffect, useState } from "react";
import {
  Database,
  Plus,
  Loader2,
  RefreshCw,
  Trash2,
  AlertCircle,
  Inbox,
  TrendingUp,
  Bitcoin,
} from "lucide-react";
import { useWorkspaceStore, type QuantDatasetMeta } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { NewPullDialog } from "./QuantDatasetsPanel/NewPullDialog";

function fmtFetchedAt(s: string): string {
  // 20260101T120000Z → 2026-01-01 12:00 UTC
  const m = s.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  if (!m) return s;
  return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]} UTC`;
}

function MarketBadge({ market }: { market: QuantDatasetMeta["market"] }) {
  const cfg = market === "a_stock"
    ? { Icon: TrendingUp, label: "A 股", color: "text-app-accent" }
    : { Icon: Bitcoin,     label: "加密",  color: "text-app-warning" };
  return (
    <span className={`inline-flex items-center gap-1 text-ui-xs ${cfg.color}`}>
      <cfg.Icon size={11} />
      {cfg.label}
    </span>
  );
}

function DatasetCard({
  ds,
  onRefresh,
  onDeleted,
  onSelect,
  selected,
}: {
  ds: QuantDatasetMeta;
  onRefresh: (id: string) => Promise<void>;
  onDeleted: (id: string) => void;
  onSelect?: (ds: QuantDatasetMeta) => void;
  selected?: boolean;
}) {
  const [refreshing, setRefreshing] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const refresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh(ds.id);
    } finally {
      setRefreshing(false);
    }
  };

  const del = async () => {
    if (!confirmDel) {
      setConfirmDel(true);
      return;
    }
    setDeleting(true);
    try {
      const r = await fetch(`/api/quant/datasets/${ds.id}`, { method: "DELETE" });
      if (!r.ok) throw new Error("删除失败");
      onDeleted(ds.id);
    } catch {
      setDeleting(false);
      setConfirmDel(false);
    }
  };

  return (
    <div
      className={`relative rounded border transition-all duration-150 overflow-hidden
                  ${selected
                    ? "border-app-accent bg-app-bg-secondary"
                    : "border-app-border bg-app-bg-secondary hover:border-app-accent/40"}`}
    >
      {selected && <div className="absolute left-0 inset-y-0 w-[3px] bg-app-accent" />}

      <div className={`px-4 py-3 ${selected ? "pl-4" : ""}`}>
        {/* Row 1: symbol + market + actions */}
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono font-semibold text-app-text text-ui-base flex-1 truncate">
            {ds.symbol}
          </span>
          <MarketBadge market={ds.market} />
          <div className="flex items-center gap-1">
            {onSelect && (
              <button
                onClick={() => onSelect(ds)}
                title="选取此数据集"
                className="px-2 py-0.5 text-ui-xs border border-app-accent text-app-accent rounded
                           hover:bg-app-accent hover:text-white cursor-pointer transition-colors"
              >
                选取
              </button>
            )}
            <button
              onClick={refresh}
              disabled={refreshing}
              title="重新拉取"
              className="p-1 text-app-text-muted hover:text-app-text rounded
                         cursor-pointer disabled:opacity-40 transition-colors"
            >
              {refreshing
                ? <Loader2 size={12} className="animate-spin" />
                : <RefreshCw size={12} />}
            </button>
            {confirmDel ? (
              <>
                <button
                  onClick={del}
                  disabled={deleting}
                  className="px-1.5 py-0.5 text-ui-xs text-white bg-app-error rounded
                             cursor-pointer hover:brightness-110 disabled:opacity-50
                             flex items-center gap-0.5"
                >
                  {deleting
                    ? <Loader2 size={11} className="animate-spin" />
                    : <Trash2 size={11} />}
                  确认
                </button>
                <button
                  onClick={() => setConfirmDel(false)}
                  className="p-1 text-app-text-muted hover:text-app-text rounded cursor-pointer"
                >
                  ×
                </button>
              </>
            ) : (
              <button
                onClick={del}
                title="删除数据集"
                className="p-1 text-app-text-muted hover:text-app-error rounded
                           cursor-pointer transition-colors"
              >
                <Trash2 size={12} />
              </button>
            )}
          </div>
        </div>

        {/* Row 2: meta */}
        <div className="flex items-center gap-3 text-ui-xs text-app-text-muted font-mono">
          <span>period: {ds.period}</span>
          <span>interval: {ds.interval}</span>
          <span>·</span>
          <span>{ds.rows} 行</span>
          <span>·</span>
          <span>{ds.source}</span>
        </div>

        {/* Row 3: fetched_at */}
        <div className="mt-1 text-ui-xs text-app-text-muted/70 font-mono">
          {fmtFetchedAt(ds.fetched_at)}
        </div>
      </div>
    </div>
  );
}

export default function QuantDatasetsPanel() {
  const [datasets, setDatasets] = useState<QuantDatasetMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pullOpen, setPullOpen] = useState(false);
  const datasetMeta = useWorkspaceStore((s) => s.datasetMeta);
  const setDatasetMeta = useWorkspaceStore((s) => s.setDatasetMeta);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const r = await fetch("/api/quant/datasets");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setDatasets(Array.isArray(d.datasets) ? d.datasets : []);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 把当前选中 id 同步给 store（id 由后端 round-trip 不变；元数据从卡片 props 拿）
  useEffect(() => {
    if (!datasetMeta) return;
    const exists = datasets.some((d) => d.id === datasetMeta.id);
    if (!exists) setDatasetMeta(null);
  }, [datasets, datasetMeta, setDatasetMeta]);

  const refresh = async (_id: string) => {
    // 重新拉取会创建新 id（带新 fetched_at），不替换旧 id — 直接 reload
    await load();
  };

  const onSelect = (ds: QuantDatasetMeta) => {
    setDatasetMeta(ds);
  };

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text">
      <PanelHeader title="量化数据集">
        <button
          onClick={() => setPullOpen(true)}
          className="flex items-center gap-1 px-2 py-0.5 text-ui-xs bg-app-accent
                     hover:bg-app-accent-hover text-white rounded transition-colors
                     duration-150 cursor-pointer"
        >
          <Plus size={12} />
          新建拉取
        </button>
      </PanelHeader>

      {/* Summary */}
      {!loading && datasets.length > 0 && (
        <div className="flex items-center gap-4 px-4 py-2 border-b border-app-border
                        text-ui-xs text-app-text-muted bg-app-bg-secondary">
          <span>{datasets.length} 个数据集</span>
          {datasetMeta && (
            <span className="text-app-accent font-mono">
              当前选中: {datasetMeta.symbol} ({datasetMeta.interval})
            </span>
          )}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {loading && (
          <div className="flex items-center gap-2 justify-center py-8 text-app-text-muted">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-ui-sm">加载中…</span>
          </div>
        )}

        {loadError && (
          <div className="flex items-center gap-2 px-3 py-2 bg-app-status-error text-app-error
                          text-ui-xs rounded border border-app-error/30">
            <AlertCircle size={13} />
            <span className="flex-1">{loadError}</span>
            <button onClick={load} className="underline cursor-pointer hover:no-underline">重试</button>
          </div>
        )}

        {!loading && !loadError && datasets.length === 0 && (
          <div className="flex flex-col items-center py-20 gap-4 text-app-text-muted select-none">
            <Inbox size={48} strokeWidth={1} className="text-app-accent/40" />
            <div className="text-center space-y-1">
              <div className="text-ui-base text-app-text font-semibold">还没有数据集</div>
              <div className="text-ui-xs">点击右上角「新建拉取」开始获取行情</div>
              <div className="text-ui-xs flex items-center justify-center gap-1 mt-2 opacity-70">
                <Database size={11} />
                数据将保存到 ~/.hagoku/datasets/
              </div>
            </div>
          </div>
        )}

        {datasets.map((ds) => (
          <DatasetCard
            key={ds.id}
            ds={ds}
            selected={datasetMeta?.id === ds.id}
            onRefresh={refresh}
            onDeleted={() => void load()}
            onSelect={onSelect}
          />
        ))}
      </div>

      <NewPullDialog
        open={pullOpen}
        onClose={() => setPullOpen(false)}
        onCreated={() => void load()}
      />
    </div>
  );
}
