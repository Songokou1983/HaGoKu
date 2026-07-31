/** CO-15: 处理中指示 — 不展示模型内部 reasoning 文本。 */
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
        <span className="text-ui-xs text-app-text-muted select-none">
          {text}
        </span>
      </div>
    </div>
  );
}
