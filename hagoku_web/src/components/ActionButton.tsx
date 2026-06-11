import { Loader2, type LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ActionButtonVariant = "primary" | "secondary" | "danger" | "ghost";

export interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ActionButtonVariant;
  loading?: boolean;
  icon?: LucideIcon;
  children: ReactNode;
}

const variantClasses: Record<ActionButtonVariant, string> = {
  primary:
    "bg-app-accent text-white hover:bg-app-accent-hover border-app-accent",
  secondary:
    "border border-app-border text-app-text hover:border-app-accent hover:text-app-accent bg-transparent",
  danger:
    "bg-app-error/15 text-app-error border border-app-error/30 hover:bg-app-error/25",
  ghost:
    "text-app-text-muted hover:text-app-text bg-transparent",
};

export function ActionButton({
  variant = "primary",
  loading = false,
  icon: Icon,
  children,
  className = "",
  disabled,
  ...rest
}: ActionButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <button
      {...rest}
      disabled={isDisabled}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-ui-xs font-medium
        transition-colors duration-150 cursor-pointer
        ${variantClasses[variant]}
        ${isDisabled ? "opacity-50 cursor-not-allowed" : ""}
        ${className}`}
    >
      {loading ? (
        <Loader2 size={13} className="animate-spin shrink-0" />
      ) : Icon ? (
        <Icon size={13} className="shrink-0" />
      ) : null}
      {children}
    </button>
  );
}
