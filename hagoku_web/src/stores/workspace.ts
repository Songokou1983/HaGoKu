import { create } from "zustand";
import type { AgentStatus, ConnectionStatus } from "../types/events";

export type PanelId =
  | "projects"
  | "analyze"
  | "report"
  | "knowledge"
  | "settings"
  | "events";

interface WorkspaceStore {
  activeView: PanelId;
  status: "idle" | "running" | "done";
  agents: Record<string, AgentStatus>;
  connectionStatus: ConnectionStatus;
  projects: string[];
  currentProject: string | null;
  reportFiles: { name: string; url: string; mtime: number }[];
  lastError: string | null;

  setActiveView: (view: PanelId) => void;
  setStatus: (s: "idle" | "running" | "done") => void;
  setAgentStatus: (agent: string, s: AgentStatus) => void;
  setConnectionStatus: (s: ConnectionStatus) => void;
  setProjects: (projects: string[]) => void;
  setCurrentProject: (name: string | null) => void;
  setReportFiles: (files: { name: string; url: string; mtime: number }[]) => void;
  setLastError: (msg: string | null) => void;
  /** 分析重置：全局运行状态 + Agent 状态条（与项目卡片「进行中」一致） */
  resetRunUiState: () => void;
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  activeView: "projects",
  status: "idle",
  agents: {},
  connectionStatus: "connecting",
  projects: [],
  currentProject: null,
  reportFiles: [],
  lastError: null,

  setActiveView: (activeView) => set({ activeView }),
  setStatus: (status) => set({ status }),
  setAgentStatus: (agent, st) =>
    set((s) => ({
      agents: { ...s.agents, [agent]: st },
    })),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setProjects: (projects) => set({ projects }),
  setCurrentProject: (currentProject) => set({ currentProject }),
  setReportFiles: (reportFiles) => set({ reportFiles }),
  setLastError: (lastError) => set({ lastError }),
  resetRunUiState: () => set({ status: "idle", agents: {} }),
}));