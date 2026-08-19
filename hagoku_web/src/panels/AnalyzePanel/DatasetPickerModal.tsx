/**
 * 量化数据集选择器 — 从 ~/.hagoku/datasets/ 拉取列表，选取一条后 GET parquet
 * 并走「上传」通道（handleUpload 创建副本到当前项目）。
 *
 * 不走 fetch_market_data — 那是 LLM 工具通道；这里是用户手动选取。
 */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Database, Loader2, X, AlertCircle, Inbox } from "lucide-react";
import type { QuantDatasetMeta } from "../../stores/workspace";
import { useWorkspaceStore } from "../../stores/workspace";

interface DatasetPickerModalProps {
  open: boolean;
  currentProject: string | null;
  phase: string;
  handleUpload: (file: File) => Promise<void>;
  onClose: () => void;
}

export function DatasetPickerModal({
  open, currentProject, phase, handleUpload, onClose,
}: DatasetPickerModalProps) {
  const [datasets, setDatasets] = useState<QuantDatasetMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pickingId, setPickingId] = useState<string | null>(null);
  const setDatasetMeta = useWorkspaceStore((s) => s.setDatasetMeta);

  // 打开时拉列表
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setLoadError(null);
    fetch("/api/quant/datasets")
      .then((r) => r.json())
      .then((d: { datasets?: QuantDatasetMeta[] }) => {
        setDatasets(Array.isArray(d.datasets) ? d.datasets : []);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  }, [open]);

  // Esc 关闭
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !pickingId) onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, pickingId, onClose]);

  if (!open) return null;

  const pick = async (ds: QuantDatasetMeta) => {
    if (!currentProject || phase === "running") return;
    setPickingId(ds.id);
    try {
      const r = await fetch(`/api/quant/datasets/${ds.id}/parquet`);
      if (!r.ok) throw new Error("parquet 拉取失败");
      const blob = await r.blob();
      // 副本命名为 <symbol>__<interval>.parquet — 用户在文件列表里能看出来源
      const fname = `${ds.symbol}__${ds.interval}.parquet`;
      const file = new File([blob], fname, { type: "application/octet-stream" });
      setDatasetMeta(ds);
      await handleUpload(file);
      onClose();
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "选取失败");
    } finally {
      setPickingId(null);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !pickingId) onClose();
      }}
    >
      <div
        role="dialog"
        aria-label="选择量化数据集"
        className="bg-app-bg border border-app-border rounded-md w-[520px] max-w-[92vw]
                   shadow-xl flex flex-col max-h-[80vh]"
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-app-border">
          <div className="text-ui-sm font-semibold text-app-text flex items-center gap-1.5">
            <Database size={14} className="text-app-accent" />
            从量化数据集选取
          </div>
          <button
            onClick={onClose}
            disabled={pickingId !== null}
            aria-label="关闭"
            className="text-app-text-muted hover:text-app-text p-1 rounded
                       disabled:opacity-40 cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-3 space-y-2">
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
            </div>
          )}

          {!loading && !loadError && datasets.length === 0 && (
            <div className="flex flex-col items-center py-12 gap-2 text-app-text-muted select-none">
              <Inbox size={36} strokeWidth={1} className="text-app-accent/40" />
              <div className="text-ui-sm">还没有数据集</div>
              <div className="text-ui-xs opacity-70">请到「量化数据集」面板新建拉取</div>
            </div>
          )}

          {datasets.map((ds) => {
            const isPicking = pickingId === ds.id;
            return (
              <button
                key={ds.id}
                onClick={() => void pick(ds)}
                disabled={pickingId !== null || phase === "running"}
                className="w-full text-left px-3 py-2 bg-app-bg-secondary border border-app-border
                           rounded hover:border-app-accent transition-colors
                           disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono font-semibold text-app-text flex-1 truncate">
                    {ds.symbol}
                  </span>
                  <span className="text-ui-xs text-app-text-muted">{ds.market === "a_stock" ? "A 股" : "加密"}</span>
                  {isPicking && <Loader2 size={12} className="animate-spin text-app-accent" />}
                </div>
                <div className="mt-1 text-ui-xs text-app-text-muted font-mono">
                  period: {ds.period} · interval: {ds.interval} · {ds.rows} 行 · {ds.source}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>,
    document.body,
  );
}
