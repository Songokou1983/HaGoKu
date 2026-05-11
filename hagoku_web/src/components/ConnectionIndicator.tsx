import { useWorkspaceStore } from "../stores/workspace";
import type { ConnectionStatus } from "../types/events";

const statusDef: Record<ConnectionStatus, { dot: string; label: string }> = {
  connecting: { dot: "bg-yellow-500", label: "connecting" },
  connected: { dot: "bg-green-500", label: "connected" },
  reconnecting: { dot: "bg-yellow-500 animate-pulse", label: "reconnecting" },
  disconnected: { dot: "bg-red-500", label: "offline" },
};

export function ConnectionIndicator() {
  const connectionStatus = useWorkspaceStore((s) => s.connectionStatus);
  const { dot, label } = statusDef[connectionStatus];

  return (
    <div className="flex items-center gap-1.5">
      <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
      <span className="text-ui-xs text-app-text-muted">{label}</span>
    </div>
  );
}