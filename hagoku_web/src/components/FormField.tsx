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

export interface SelectProps {
  options: string[];
  value: string;
  onChange?: (value: string) => void;
}

export function Select({ options, value, onChange }: SelectProps) {
  return (
    <select
      className="w-full bg-app-bg-secondary border border-app-border rounded px-2 py-1 text-ui-base text-app-text outline-none focus:border-app-accent focus-visible:ring-1 focus-visible:ring-app-accent hover:border-app-accent transition-colors duration-150"
      value={value}
      onChange={onChange ? (e) => onChange(e.target.value) : undefined}
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}