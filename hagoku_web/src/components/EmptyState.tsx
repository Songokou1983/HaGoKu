import type { ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  message: string;
}

export function EmptyState({ icon, message }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 text-app-text-muted pt-8">
      {icon}
      <span className="text-ui-base">{message}</span>
    </div>
  );
}