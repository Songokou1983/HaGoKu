import type { FieldReviewPayload } from "./types";

export function FieldReviewTable({ data }: { data: FieldReviewPayload }) {
  const summaryLine = data.analysis_fields_summary
    ? data.analysis_fields_summary
    : `共 ${String(data.n_rows)} 行 × ${data.n_cols} 列 · 四列：字段名称 / 中文名称 / 含义理解 / 参与分析`;
  return (
    <div
      className="w-full max-w-full border border-app-border rounded-lg bg-app-bg-secondary overflow-x-auto
        motion-safe:transition-shadow motion-safe:duration-300 shadow-sm hover:shadow-md"
    >
      <div className="px-3 py-2 border-b border-app-border text-ui-xs text-app-text-muted leading-snug">
        {summaryLine}
      </div>
      <table className="w-full text-ui-sm border-collapse">
        <caption className="sr-only">字段理解核对</caption>
        <thead>
          <tr className="bg-app-bg/50 border-b border-app-border">
            <th className="px-3 py-2 font-medium text-left border-r border-app-border w-24">字段</th>
            <th className="px-3 py-2 font-medium text-left border-r border-app-border w-28">中文名称</th>
            <th className="px-3 py-2 font-medium text-left border-r border-app-border">含义理解</th>
            <th className="px-3 py-2 font-medium text-left" style={{minWidth: 180}}>参与分析</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r, i) => (
            <tr key={`${r.field_name}-${i}`} className="border-b border-app-border/40 hover:bg-app-bg/30">
              <td className="px-3 py-2 align-top border-r border-app-border/40 font-mono text-ui-xs">{r.field_name}</td>
              <td className="px-3 py-2 align-top border-r border-app-border/40 font-medium">{r.chinese_name}</td>
              <td className="px-3 py-2 align-top border-r border-app-border/40 text-app-text-muted">{r.meaning}</td>
              <td className="px-3 py-2 align-top">
                <span className={r.used_in_analysis === true ? 'text-green-400' : r.used_in_analysis === false ? 'text-app-text-muted' : ''}>
                  {r.used_in_analysis === true ? '是' : r.used_in_analysis === false ? '否' : '-'}
                </span>
                {r.evidence && <div className="text-ui-xs text-app-text-muted/70 mt-1 leading-relaxed">{r.evidence}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
