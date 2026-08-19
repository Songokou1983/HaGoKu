/**
 * 量化数据集 — 新建拉取对话框。
 *
 * 通过 createPortal 渲染到 document.body，避免父层 overflow / z-index 干扰。
 * 显式 useRef + useEffect 接管焦点（避免 autoFocus 被父级 transient state 影响）。
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Loader2, X } from "lucide-react";

type Market = "a_stock" | "crypto";
type Period = "1y" | "90d" | "30d";
type Interval = "d1" | "h1";

interface FormState {
  market: Market;
  symbol: string;
  period: Period;
  interval: Interval;
}

const DEFAULT_FORM: FormState = {
  market: "a_stock",
  symbol: "000001",
  period: "1y",
  interval: "d1",
};

export interface NewPullDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function NewPullDialog({ open, onClose, onCreated }: NewPullDialogProps) {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const symbolRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Open → focus symbol input, reset error
  useEffect(() => {
    if (!open) return;
    setError(null);
    // 用 setTimeout 让 dialog 进入 DOM 后再 focus
    const tid = setTimeout(() => symbolRef.current?.focus(), 30);
    return () => clearTimeout(tid);
  }, [open]);

  // Esc to close
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, submitting, onClose]);

  if (!open) return null;

  // A 股 + h1 不支持（akshare 仅 daily）
  const intervalDisabled = form.market === "a_stock" && form.interval === "h1";

  const onChange = <K extends keyof FormState>(k: K, v: FormState[K]) => {
    setForm((prev) => ({ ...prev, [k]: v }));
  };

  const submit = async () => {
    setError(null);
    const sym = form.symbol.trim();
    if (!sym) {
      setError("请输入交易代码 / 股票代码");
      symbolRef.current?.focus();
      return;
    }
    if (intervalDisabled) {
      setError("A 股不支持小时级数据（akshare 限制），请把 interval 改为 d1");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/quant/datasets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          market: form.market,
          symbol: sym,
          period: form.period,
          interval: form.interval,
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({ detail: "拉取失败" }));
        throw new Error(typeof d.detail === "string" ? d.detail : "拉取失败");
      }
      onCreated();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "拉取失败");
    } finally {
      setSubmitting(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center"
      onMouseDown={(e) => {
        // 点击遮罩关闭（不拦截 dialog 内部点击）
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-label="新建拉取"
        className="bg-app-bg border border-app-border rounded-md w-[420px] max-w-[92vw]
                   shadow-xl flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-app-border">
          <div className="text-ui-sm font-semibold text-app-text">新建拉取</div>
          <button
            onClick={onClose}
            disabled={submitting}
            aria-label="关闭"
            className="text-app-text-muted hover:text-app-text p-1 rounded
                       disabled:opacity-40 cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div className="px-4 py-3 space-y-3">
          {/* Market radio */}
          <div>
            <div className="text-ui-xs text-app-text-muted mb-1.5">市场</div>
            <div className="flex gap-2">
              {(["a_stock", "crypto"] as Market[]).map((m) => (
                <label
                  key={m}
                  className={`flex-1 flex items-center justify-center gap-1.5 px-2.5 py-1.5
                              border rounded text-ui-sm cursor-pointer transition-colors
                              ${form.market === m
                                ? "border-app-accent bg-app-accent/10 text-app-accent"
                                : "border-app-border text-app-text-muted hover:text-app-text"}`}
                >
                  <input
                    type="radio"
                    name="market"
                    value={m}
                    checked={form.market === m}
                    onChange={() => onChange("market", m)}
                    className="accent-app-accent"
                  />
                  <span>{m === "a_stock" ? "A 股" : "加密货币"}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Symbol */}
          <div>
            <div className="text-ui-xs text-app-text-muted mb-1.5">
              {form.market === "a_stock" ? "股票代码" : "交易对"}
            </div>
            <input
              ref={symbolRef}
              type="text"
              value={form.symbol}
              onChange={(e) => onChange("symbol", e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void submit();
                }
              }}
              placeholder={form.market === "a_stock" ? "如 000001" : "如 BTC/USDT"}
              className="w-full px-2.5 py-1.5 text-ui-sm font-mono bg-app-bg
                         border border-app-border rounded text-app-text
                         placeholder-app-text-muted focus:outline-none
                         focus:border-app-accent"
            />
          </div>

          {/* Period + Interval */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-ui-xs text-app-text-muted mb-1.5">时长</div>
              <select
                value={form.period}
                onChange={(e) => onChange("period", e.target.value as Period)}
                className="w-full px-2 py-1.5 text-ui-sm bg-app-bg border border-app-border
                           rounded text-app-text focus:outline-none focus:border-app-accent"
              >
                <option value="1y">1 年</option>
                <option value="90d">90 天</option>
                <option value="30d">30 天</option>
              </select>
            </div>
            <div>
              <div className="text-ui-xs text-app-text-muted mb-1.5">
                频率
                {intervalDisabled && (
                  <span className="ml-1.5 text-app-warning text-ui-xs">
                    (A 股仅日线)
                  </span>
                )}
              </div>
              <select
                value={form.interval}
                onChange={(e) => onChange("interval", e.target.value as Interval)}
                className="w-full px-2 py-1.5 text-ui-sm bg-app-bg border border-app-border
                           rounded text-app-text focus:outline-none focus:border-app-accent
                           disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <option value="d1">日线 (d1)</option>
                <option value="h1" disabled={intervalDisabled && form.interval !== "h1"}>
                  小时 (h1)
                </option>
              </select>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="text-ui-xs text-app-error bg-app-error/10 border border-app-error/30
                            rounded px-2.5 py-2 whitespace-pre-wrap">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2.5 border-t border-app-border flex items-center gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-3 py-1.5 text-ui-xs text-app-text-muted hover:text-app-text
                       border border-app-border rounded cursor-pointer
                       transition-colors duration-150 disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="px-3 py-1.5 text-ui-xs bg-app-accent hover:bg-app-accent-hover
                       text-white rounded cursor-pointer flex items-center gap-1
                       transition-colors duration-150 disabled:opacity-50"
          >
            {submitting && <Loader2 size={11} className="animate-spin" />}
            {submitting ? "拉取中…" : "开始拉取"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
