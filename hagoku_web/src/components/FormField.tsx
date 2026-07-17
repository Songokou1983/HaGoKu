import type { ReactNode } from "react";

export interface FieldProps {
  label: string;
  icon: ReactNode;
  children: ReactNode;
}

export function Field({ label, icon, children }: FieldProps) {
  return (
    <label className="block">
      <span className="flex items-center gap-1.5 text-ui-xs text-app-text-muted mb-1">
        {icon}
        {label}
      </span>
      {children}
    </label>
  );
}