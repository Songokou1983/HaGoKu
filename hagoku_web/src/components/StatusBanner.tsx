import { X, AlertCircle, CheckCircle2, Info } from "lucide-react";
import { useState } from "react";

export type StatusBannerVariant = "error" | "success" | "info";

export interface StatusBannerProps {
  variant: StatusBannerVariant;
  message: string;
  dismissible?: boolean;
  className?: string;
}

const variantConfig: Record<
  StatusBannerVariant,
  { icon: typeof AlertCircle; bg: string; border: string; text: string }
> = {
  error: {
    icon: AlertCircle,
    bg: "bg-app-error/10",
    border: "border-app-error/30",
    text: "text-app-error",
  },
  success: {
    icon: CheckCircle2,
    bg: "bg-app-success/10",
    border: "border-app-success/30",
    text: "text-app-success",
  },
  info: {
    icon: Info,
    bg: "bg-app-accent/10",
    border: "border-app-accent/30",
    text: "text-app-accent",
  },
};

export function StatusBanner({
  variant,
  message,
  dismissible = false,
  className = "",
}: StatusBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const cfg = variantConfig[variant];
  const Icon = cfg.icon;

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded border text-ui-xs
        ${cfg.bg} ${cfg.border} ${cfg.text} ${className}`}
    >
      <Icon size={13} className="shrink-0" />
      <span className="flex-1">{message}</span>
      {dismissible && (
        <button
          onClick={() => setDismissed(true)}
          className="opacity-60 hover:opacity-100 transition-opacity cursor-pointer shrink-0"
          aria-label="关闭"
        >
          <X size={12} />
        </button>
      )}
    </div>
  );
}
