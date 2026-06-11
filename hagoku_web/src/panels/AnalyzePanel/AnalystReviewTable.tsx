import type { AnalystReviewPayload } from "./types";
import { significanceShort } from "./parsers";
import { focusLabel } from "../../constants/focusAreas";

export function AnalystReviewTable({ data }: { data: AnalystReviewPayload }) {
  return (
    <div
      className="w-full max-w-full border border-app-border rounded-lg bg-app-bg-secondary overflow-x-auto
        motion-safe:transition-shadow motion-safe:duration-300 shadow-sm hover:shadow-md"
    >
      <div className="px-3 py-2 border-b border-app-border text-ui-xs leading-snug space-y-0.5">
        <div className="font-medium text-app-text">{focusLabel("analyst")}</div>
        <div className="text-app-text-muted">
          共 {data.n_findings} 条结果 · 其中统计显著 {data.n_significant} 条 · 请核对下表（p 值、效应量、置信区间）；可补充说明，或点「确认继续」进入下一步
        </div>
      </div>
      <table className="w-full text-ui-sm border-collapse min-w-[720px]">
        <caption className="sr-only">统计分析结果摘要</caption>
        <colgroup>
          <col className="w-[7%]" />
          <col className="w-[9%]" />
          <col className="w-[20%]" />
          <col className="w-[9%]" />
          <col className="w-[11%]" />
          <col className="w-[14%]" />
          <col className="w-[8%]" />
          <col className="w-[22%]" />
        </colgroup>
        <thead>
          <tr className="bg-app-bg border-b border-app-border">
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              ID
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              类型
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              研究问题
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              p 值
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              效应量
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              置信区间
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              显著性
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center align-middle">
              简要结论
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rows.length === 0 ? (
            <tr>
              <td colSpan={8} className="px-2 py-2 text-left text-app-text-muted text-ui-xs">
                （无结构化结果行）
              </td>
            </tr>
          ) : (
            data.rows.map((r, i) => (
              <tr key={`${r.result_id}-${i}`} className="border-b border-app-border last:border-b-0">
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-all">
                  {r.result_id || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-all">
                  {r.analysis_type || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border break-words">
                  {r.question || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs tabular-nums">
                  {r.p_value || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-words">
                  {r.effect_summary || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-words">
                  {r.confidence_interval || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border">
                  {significanceShort(r.significance)}
                </td>
                <td className="px-2 py-1.5 text-left align-top break-words">{r.conclusion_plain || "—"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
