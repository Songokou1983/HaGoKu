import { create } from "zustand";
import type { AgentStatus, ConnectionStatus } from "../types/events";

export type PanelId =
  | "projects"
  | "analyze"
  | "report"
  | "knowledge"
  | "settings"
  | "lab"
  | "events"
  | "doctor"
  | "quant-datasets";

/**
 * 量化数据集元信息（来自 parquet metadata，ONE file）。
 * UI 仅缓存当前选中的数据集，用于 AnalyzePanel 从数据集库选数据时减少回环。
 */
export interface QuantDatasetMeta {
  id: string;
  market: "a_stock" | "crypto";
  symbol: string;
  period: string;
  interval: "d1" | "h1";
  fetched_at: string;
  rows: number;
  source: "akshare" | "ccxt";
}

interface WorkspaceStore {
  activeView: PanelId;
  status: "idle" | "running" | "done";
  agents: Record<string, AgentStatus>;
  connectionStatus: ConnectionStatus;
  projects: string[];
  currentProject: string | null;
  currentDataPath: string;
  reportFiles: { name: string; url: string; mtime: number }[];
  lastError: string | null;
  /** 项目切换快照 */
  snapshot: {
    messages: any[];
    reportUrl: string | null;
    pendingAskUser: any | null;
    projectName: string;
    dataPath: string;
  } | null;
  /** 当前选中的量化数据集元信息（AnalyzePanel 数据选择器写入） */
  datasetMeta: QuantDatasetMeta | null;

  setActiveView: (view: PanelId) => void;
  setStatus: (s: "idle" | "running" | "done") => void;
  setAgentStatus: (agent: string, s: AgentStatus) => void;
  setConnectionStatus: (s: ConnectionStatus) => void;
  setProjects: (projects: string[]) => void;
  setCurrentProject: (name: string | null) => void;
  setCurrentDataPath: (path: string) => void;
  setSnapshot: (snap: any | null) => void;
  setReportFiles: (files: { name: string; url: string; mtime: number }[]) => void;
  setLastError: (msg: string | null) => void;
  setDatasetMeta: (meta: QuantDatasetMeta | null) => void;
  /** 分析重置：全局运行状态 + Agent 状态条（与项目卡片「进行中」一致） */
  resetRunUiState: () => void;
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  activeView: "projects" as PanelId,
  status: "idle",
  agents: {},
  connectionStatus: "idle",
  projects: [],
  currentProject: localStorage.getItem('hagoku_active_project') || null,
  currentDataPath: localStorage.getItem('hagoku_active_data_path') || '',
  reportFiles: [],
  lastError: null,
  snapshot: null,
  datasetMeta: null,

  setActiveView: (activeView) => {
    set({ activeView });
  },
  setStatus: (status) => set({ status }),
  setAgentStatus: (agent, st) =>
    set((s) => ({
      agents: { ...s.agents, [agent]: st },
    })),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setProjects: (projects) => set({ projects: Array.isArray(projects) ? projects : [] }),
  setSnapshot: (snap) => set({ snapshot: snap }),
  setCurrentProject: (currentProject) => {
    if (currentProject) localStorage.setItem('hagoku_active_project', currentProject);
    else localStorage.removeItem('hagoku_active_project');
    set({ currentProject });
  },
  setCurrentDataPath: (currentDataPath) => {
    if (currentDataPath) localStorage.setItem('hagoku_active_data_path', currentDataPath);
    else localStorage.removeItem('hagoku_active_data_path');
    set({ currentDataPath });
  },
  setReportFiles: (reportFiles) => set({ reportFiles }),
  setLastError: (lastError) => set({ lastError }),
  setDatasetMeta: (datasetMeta) => set({ datasetMeta }),
  resetRunUiState: () => set({ status: "idle", agents: {} }),
  resetAgentStates: () => set({ agents: { scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" } }),
}));