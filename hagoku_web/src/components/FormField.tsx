import type { ReactNode } from "react";

export interface FieldProps {
  label: string;
  icon: ReactNode;
  children: ReactNode;
}

export function Field({ label, icon, children }: FieldProps) {
  return (
    <label className="block">
      <span className="flex items-center gap-1.5 text-[11px] text-[#888] mb-1">
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
      className="w-full bg-[#252525] border border-[#444] rounded px-2 py-1 text-[13px] text-[#d4d4d4] outline-none focus:border-[#569cd6] hover:border-[#569cd6] transition-colors duration-150"
      defaultValue={value}
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