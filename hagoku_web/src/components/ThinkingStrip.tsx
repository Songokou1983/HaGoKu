/** CO-15: ThinkingStrip — 单条展示最新 agent_thinking。
 *
 * agent_thinking 不进 ConvoFeed 刷屏；在此作为 Pipeline 下方的独立条展示。
 * 每次新的 thinking 到达时替换旧内容（不堆叠）。
 */
export interface ThinkingStripProps {
  text: string | null;
}

export function ThinkingStrip({ text }: ThinkingStripProps) {
  if (!text) return null;

  const short = text.length > 280 ? `${text.slice(0, 277)}…` : text;

  return (
    <div className="px-3 py-1.5 border-b border-app-border/40 bg-app-bg-secondary/50 shrink-0">
      <div className="flex items-start gap-2">
        <span className="text-ui-xs text-app-text-muted shrink-0 mt-px select-none">
          思考:
        </span>
        <span className="text-ui-xs text-app-text-muted italic leading-relaxed animate-pulse">
          {short}
        </span>
      </div>
    </div>
  );
}
