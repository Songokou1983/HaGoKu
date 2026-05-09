import type { ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  message: string;
}

export function EmptyState({ icon, message }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 text-[#666] pt-8">
      {icon}
      <span className="text-[13px] italic">{message}</span>
    </div>
  );
}