/** CO-02: 4 关注点常量 — 用户可见的中文叙事层。
 *
 * 底层 WS stage key 仍为 scout/cleaner/analyst/reporter（协议不变），
 * 此模块提供翻译为中文关注点的 label/desc/placeholder 映射。
 */
export const FOCUS_AREAS = {
  scout:    { key: "scout",    label: "理解字段", desc: "字段语义与目标对齐", order: 1 },
  cleaner:  { key: "cleaner",  label: "评估清洗", desc: "缺失值与异常策略",   order: 2 },
  analyst:  { key: "analyst",  label: "跑统计",   desc: "检验、效应量与诊断", order: 3 },
  reporter: { key: "reporter", label: "写报告",   desc: "结论与双轨 HTML",   order: 4 },
} as const;

export type StageKey = keyof typeof FOCUS_AREAS;

/** 按 order 排序的 stage key 列表 */
export const STAGE_ORDER: StageKey[] = ["scout", "cleaner", "analyst", "reporter"];

export function focusLabel(stageKey: string): string {
  return FOCUS_AREAS[stageKey as StageKey]?.label ?? stageKey;
}

export function focusDesc(stageKey: string): string {
  return FOCUS_AREAS[stageKey as StageKey]?.desc ?? "";
}

export function focusPlaceholder(stageKey: string): string {
  const label = focusLabel(stageKey);
  const map: Record<string, string> = {
    scout:   "字段理解不对时输入说明，Enter 发送",
    cleaner: "不同意建议？输入你的想法后 Enter 发送",
    analyst: "补充关注点后 Enter 发送",
    reporter: "输入回复后 Enter 发送",
  };
  return map[stageKey] ?? `正在${label}，输入回复后 Enter 发送`;
}
