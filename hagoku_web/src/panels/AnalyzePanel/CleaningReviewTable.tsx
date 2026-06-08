import type { CleaningReviewPayload } from "./types";

export function CleaningReviewTable({ data }: { data: CleaningReviewPayload }) {
  const pct = `${(100 * data.impact_rate).toFixed(1)}%`;
  const rowLine =
    data.rows_removed > 0
      ? `${data.total_rows_original} → ${data.total_rows_after} 行（已删 ${data.rows_removed}）`
      : `${data.total_rows_original} 行（行数未变）`;
  const qual = data.data_quality && data.data_quality !== "—" ? `${data.data_quality} · ` : "";
  return (
    <div
      className="w-full max-w-full border border-app-border rounded-lg bg-app-bg-secondary overflow-x-auto
        motion-safe:transition-shadow motion-safe:duration-300 shadow-sm hover:shadow-md"
    >
      <div className="px-3 py-2 border-b border-app-border text-ui-xs leading-snug space-y-1">
        <div className="font-medium text-app-text">Cleaner</div>
        <div className="text-app-text-muted">
          {rowLine} · {qual}偏差 {data.bias_risk} · {data.n_ops} 条 · 删行影响率{" "}
          <abbr
            title="该比例来自报告中的删行/整行替换；Winsorize 等只改单元值、不删行时常为 0%。「影响行」列为各列被改写取值的行数。"
            className="cursor-help underline decoration-dotted decoration-app-text-muted/50 underline-offset-2"
          >
            {pct}
          </abbr>
        </div>
        {data.warnings.length > 0 && (
          <ul className="list-disc pl-4 text-app-warning">
            {data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </div>
      <table className="w-full text-ui-sm border-collapse table-fixed">
        <caption className="sr-only">清洗操作摘要</caption>
        <colgroup>
          <col className="w-[16%]" />
          <col className="w-[18%]" />
          <col className="w-[10%]" />
          <col className="w-[56%]" />
        </colgroup>
        <thead>
          <tr className="bg-app-bg border-b border-app-border">
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              列
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              策略
            </th>
            <th
              scope="col"
              title="该列被改写取值的行数（与删行影响率含义不同）"
              className="px-2 py-2 font-medium text-center border-r border-app-border align-middle cursor-help"
            >
              影响行
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center align-middle">
              说明
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rows.length === 0 ? (
            <tr>
              <td colSpan={4} className="px-2 py-2 text-left text-app-text-muted text-ui-xs">
                （无单独逐条操作记录）
              </td>
            </tr>
          ) : (
            data.rows.map((r, i) => (
              <tr key={`${r.column}-${i}`} className="border-b border-app-border last:border-b-0">
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-all">
                  {r.column}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-all">
                  {r.strategy}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border tabular-nums">
                  {r.rows_affected}
                </td>
                <td className="px-2 py-1.5 text-left align-top break-words">{r.reason}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
