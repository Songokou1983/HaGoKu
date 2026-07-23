/** CO-15: 处理中指示 — 展示当前阶段/agent 名称。 */
import { Loader2 } from "lucide-react";

export interface ThinkingStripProps {
  text: string | null;
}

export function ThinkingStrip({ text }: ThinkingStripProps) {
  if (!text) return null;

  return (
    <div className="px-3 py-1.5 border-b border-app-border/40 bg-app-bg-secondary/50 shrink-0">
      <div className="flex items-center gap-2">
        <Loader2 size={12} className="animate-spin text-app-accent shrink-0" />
        <span className="text-ui-xs text-app-text-muted select-none truncate">
          {text}
        </span>
      </div>
    </div>
  );
}
