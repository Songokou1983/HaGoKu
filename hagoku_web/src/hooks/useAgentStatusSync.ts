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
  const setStatus = useWorkspaceStore((s) => s.setStatus);

  useEffect(() => {
    return onMessage((msg: WSMessage) => {
      if (msg.type !== "event" || !msg.data) return;

      const { agent, event_type } = msg.data;
      const agentKey = agent?.toLowerCase() ?? "";

      switch (event_type) {
        case "run_started":
          setStatus("running");
          break;
        case "run_completed":
        case "run_failed":
          setStatus("idle");
          break;
        case "agent_started":
          setAgentStatus(agentKey, "running");
          break;
        case "agent_completed":
          setAgentStatus(agentKey, "done");
          break;
        case "agent_failed":
          setAgentStatus(agentKey, "error");
          break;
        case "user_input_requested":
          setAgentStatus(agentKey, "waiting_input");
          break;
      }
    });
  }, [onMessage, setAgentStatus, setStatus]);
}