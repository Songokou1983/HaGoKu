import type { ReactNode } from "react";

export interface PanelHeaderProps {
  title: string;
  /** Optional icon shown before the title */
  icon?: ReactNode;
  /** Optional badge shown next to the title (e.g. count) */
  badge?: ReactNode;
  /** Optional children rendered at the right side of the header bar */
  children?: ReactNode;
}

export function PanelHeader({ title, icon, badge, children }: PanelHeaderProps) {
  return (
    <div className="px-3 py-2 text-ui-xs uppercase tracking-widest font-semibold text-app-text-muted select-none flex items-center gap-2 border-b border-app-border">
      {icon}
      <span>{title}</span>
      {badge}
      <div className="flex-1" />
      {children}
    </div>
  );
}