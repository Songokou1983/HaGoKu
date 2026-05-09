import { create } from "zustand";
import type { AgentStatus, ConnectionStatus } from "../types/events";

export type PanelId =
  | "projects"
  | "analyze"
  | "report"
  | "knowledge"
  | "settings"
  | "events";

interface PanelState {
  visible: boolean;
  order: number;
}

interface WorkspaceStore {
  panels: Record<PanelId, PanelState>;
  status: "idle" | "running" | "done";
  agents: Record<string, AgentStatus>;
  connectionStatus: ConnectionStatus;

  togglePanel: (id: PanelId) => void;
  setStatus: (s: "idle" | "running" | "done") => void;
  setAgentStatus: (agent: string, s: AgentStatus) => void;
  setConnectionStatus: (s: ConnectionStatus) => void;
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  panels: {
    projects: { visible: true, order: 0 },
    analyze: { visible: true, order: 1 },
    report: { visible: false, order: 2 },
    knowledge: { visible: true, order: 3 },
    settings: { visible: false, order: 4 },
    events: { visible: true, order: 5 },
  },
  status: "idle",
  agents: {},
  connectionStatus: "connecting",

  togglePanel: (id) =>
    set((s) => ({
      panels: {
        ...s.panels,
        [id]: { ...s.panels[id], visible: !s.panels[id].visible },
      },
    })),

  setStatus: (status) => set({ status }),
  setAgentStatus: (agent, st) =>
    set((s) => ({
      agents: { ...s.agents, [agent]: st },
    })),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
}));