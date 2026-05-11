import { useState } from "react";

interface ScoutColumn {
  name: string;
  inferred_type: string;
  sample_values: string[];
  description: string;
}

export interface ScoutPendingData {
  message: string;
  data_path: string;
  query: string;
  context: {
    columns: ScoutColumn[];
    n_rows: number;
    n_cols: number;
  };
  phase: string;
  agent: string;
}

interface Props {
  data: ScoutPendingData;
  onConfirm: (confirmed: Record<string, string>) => void;
  onSkip: () => void;
}

const TYPE_OPTIONS = ["numeric", "categorical", "text", "datetime", "id", "boolean"] as const;

export function ScoutConfirmPanel({ data, onConfirm, onSkip }: Props) {
  const [types, setTypes] = useState<Record<string, string>>(
    Object.fromEntries(data.context.columns.map((c) => [c.name, c.inferred_type]))
  );

  return (
    <div className="border border-app-accent rounded p-3 bg-app-bg-secondary space-y-3">
      <div className="text-ui-sm text-app-accent font-semibold">
        Scout 字段确认 — {data.context.n_rows} 行 × {data.context.n_cols} 列
      </div>
      <div className="text-ui-xs text-app-text-muted">{data.message}</div>

      <div className="flex items-center gap-2 text-ui-xs text-app-text-muted mb-1 px-0.5">
        <span className="w-32">字段名</span>
        <span className="flex-1">类型</span>
        <span className="max-w-[100px]">样例</span>
      </div>
      <div className="space-y-1 max-h-[200px] overflow-auto">
        {data.context.columns.map((col) => (
          <div key={col.name} className="flex items-center gap-2">
            <span className="text-ui-sm text-app-text w-32 truncate" title={col.name}>
              {col.name}
            </span>
            <select
              aria-label={`${col.name} 字段类型`}
              value={types[col.name]}
              onChange={(e) => setTypes({ ...types, [col.name]: e.target.value })}
              className="bg-app-bg border border-app-border rounded px-1 py-0.5 text-ui-xs text-app-text flex-1 outline-none focus:border-app-accent focus:ring-1 focus:ring-app-accent hover:border-app-accent transition-colors duration-150 cursor-pointer"
            >
              {TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <span
              className="text-ui-xs text-app-text-muted truncate max-w-[100px]"
              title={col.sample_values.join(", ")}
            >
              {col.sample_values.slice(0, 2).join(", ")}
            </span>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => onConfirm(types)}
          className="px-3 py-1 bg-app-accent hover:bg-app-accent-hover text-white text-ui-xs rounded cursor-pointer transition-colors duration-150"
        >
          确认并继续
        </button>
        <button
          onClick={onSkip}
          className="px-3 py-1 border border-app-border text-app-text-muted text-ui-xs rounded cursor-pointer hover:text-app-text transition-colors duration-150"
        >
          跳过
        </button>
      </div>
    </div>
  );
}