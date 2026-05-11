import type { ReactNode } from "react";

interface PanelHeaderProps {
  title: string;
  /** Optional badge shown next to the title (e.g. count) */
  badge?: ReactNode;
  /** Optional children rendered at the right side of the header bar */
  children?: ReactNode;
}

export function PanelHeader({ title, badge, children }: PanelHeaderProps) {
  return (
    <div className="px-3 py-2 text-[11px] uppercase tracking-widest font-semibold text-[#888] select-none flex items-center gap-2 border-b border-[#333]">
      <span>{title}</span>
      {badge}
      <div className="flex-1" />
      {children}
    </div>
  );
}