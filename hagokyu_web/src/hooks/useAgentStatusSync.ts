import { useEffect } from "react";
import type { WSMessage } from "../types/events";
import { useWebSocket } from "./useWebSocket";
import { useWorkspaceStore } from "../stores/workspace";

/**
 * Subscribes to WebSocket events and syncs agent lifecycle status
 * into the global Zustand store. Returns nothing — side-effect only.
 *
 * Use in any panel that needs to react to agent state changes
 * without duplicating the status-sync logic.
 */
export function useAgentStatusSync() {
  const { onMessage } = useWebSocket();
  const setAgentStatus = useWorkspaceStore((s) => s.setAgentStatus);

  useEffect(() => {
    return onMessage((msg: WSMessage) => {
      if (msg.type !== "event" || !msg.data) return;

      const { agent, event_type } = msg.data;
      switch (event_type) {
        case "agent_started":
          setAgentStatus(agent, "running");
          break;
        case "agent_completed":
          setAgentStatus(agent, "done");
          break;
        case "agent_failed":
          setAgentStatus(agent, "error");
          break;
      }
    });
  }, [onMessage, setAgentStatus]);
}