import { DockviewReact, type DockviewApi } from "dockview";
import "dockview/dist/styles/dockview.css";
import { useRef, useCallback, useMemo } from "react";
import { useWorkspaceStore, type PanelId } from "./stores/workspace";
import ProjectPanel from "./panels/ProjectPanel";
import AnalyzePanel from "./panels/AnalyzePanel";
import ReportPanel from "./panels/ReportPanel";
import KnowledgePanel from "./panels/KnowledgePanel";
import SettingsPanel from "./panels/SettingsPanel";
import EventPanel from "./panels/EventPanel";
import {
  FolderKanban,
  BarChart3,
  FileText,
  BookOpen,
  Settings,
  Activity,
} from "lucide-react";

interface PanelConfig {
  id: PanelId;
  component: string;
  title: string;
  iconName: string;
}

const PANEL_CONFIGS: PanelConfig[] = [
  { id: "projects", component: "ProjectPanel", title: "Projects", iconName: "FolderKanban" },
  { id: "analyze", component: "AnalyzePanel", title: "Analyze", iconName: "BarChart3" },
  { id: "report", component: "ReportPanel", title: "Reports", iconName: "FileText" },
  { id: "knowledge", component: "KnowledgePanel", title: "Knowledge", iconName: "BookOpen" },
  { id: "settings", component: "SettingsPanel", title: "Settings", iconName: "Settings" },
  { id: "events", component: "EventPanel", title: "Event Log", iconName: "Activity" },
];

/** Map icon names to pre-rendered JSX — avoids recreating icons per render. */
const iconMap: Record<string, React.ReactNode> = {
  FolderKanban: <FolderKanban size={14} />,
  BarChart3: <BarChart3 size={14} />,
  FileText: <FileText size={14} />,
  BookOpen: <BookOpen size={14} />,
  Settings: <Settings size={14} />,
  Activity: <Activity size={14} />,
};

const COMPONENT_MAP = {
  ProjectPanel,
  AnalyzePanel,
  ReportPanel,
  KnowledgePanel,
  SettingsPanel,
  EventPanel,
} as const;

/** Lightweight indicator dot showing overall agent status */
function SystemStatus() {
  const status = useWorkspaceStore((s) => s.status);
  const agents = useWorkspaceStore((s) => s.agents);

  const busyCount = Object.values(agents).filter((s) => s === "running").length;

  const color =
    status === "running" || busyCount > 0
      ? "bg-yellow-400"
      : status === "done"
        ? "bg-green-500"
        : "bg-[#555]";

  return (
    <div className="flex items-center gap-1.5 text-[11px] text-[#666]">
      <span className={`inline-block w-2 h-2 rounded-full ${color}`} />
      {status === "running" || busyCount > 0 ? (
        <span>{busyCount > 0 ? `${busyCount} busy` : "running"}</span>
      ) : (
        <span>{status}</span>
      )}
    </div>
  );
}

export default function App() {
  const apiRef = useRef<DockviewApi | null>(null);
  const togglePanel = useWorkspaceStore((s) => s.togglePanel);
  const panels = useWorkspaceStore((s) => s.panels);

  const initialPanels = useMemo(
    () =>
      PANEL_CONFIGS.filter((cfg) => panels[cfg.id]?.visible).map(
        (cfg) => cfg.id,
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const onReady = useCallback(
    (event: { api: DockviewApi }) => {
      apiRef.current = event.api;
      for (const pid of initialPanels) {
        const cfg = PANEL_CONFIGS.find((c) => c.id === pid);
        if (!cfg) continue;
        event.api.addPanel({
          id: cfg.id,
          component: cfg.component,
        });
      }
    },
    [initialPanels],
  );

  return (
    <div
      className="dockview-theme-dark"
      style={{
        height: "100%",
        display: "grid",
        gridTemplateRows: "auto 1fr",
        overflow: "hidden",
      }}
    >
      {/* Toggle bar — auto-sized row */}
      <div className="flex items-center gap-1 px-2 py-1 bg-[#252525] border-b border-[#333] select-none">
        {PANEL_CONFIGS.map((cfg) => {
          const visible = panels[cfg.id]?.visible;
          return (
            <button
              key={cfg.id}
              onClick={() => togglePanel(cfg.id)}
              className={`flex items-center gap-1 px-2 py-1 text-[12px] rounded transition-colors ${
                visible
                  ? "bg-[#3a3a3a] text-[#d4d4d4]"
                  : "text-[#555] hover:text-[#888] hover:bg-[#2a2a2a]"
              }`}
            >
              {iconMap[cfg.iconName]}
              {cfg.title}
            </button>
          );
        })}
        <div style={{ flex: 1 }} />
        <SystemStatus />
      </div>

      {/* Dockview workspace — fills remaining 1fr row.
          CSS Grid 1fr track provides a definite height,
          so Dockview's inner height:100% resolves correctly. */}
      <div style={{ minHeight: 0, overflow: "hidden" }}>
        <DockviewReact
          components={COMPONENT_MAP}
          onReady={onReady}
        />
      </div>
    </div>
  );
}