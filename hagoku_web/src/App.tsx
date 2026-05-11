import { DockviewReact, type DockviewApi } from "dockview";
import "dockview/dist/styles/dockview.css";
import { useRef, useCallback, useMemo, useEffect } from "react";
import { useWorkspaceStore, type PanelId } from "./stores/workspace";
import { useWebSocket } from "./hooks/useWebSocket";
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
  const errorCount = Object.values(agents).filter((s) => s === "error").length;

  const color =
    errorCount > 0
      ? "bg-app-error"
      : status === "running" || busyCount > 0
        ? "bg-app-warning"
        : status === "done"
          ? "bg-app-success"
          : "bg-app-text-muted";

  return (
    <div className="flex items-center gap-1.5 text-ui-xs text-app-text-muted">
      <span className={`inline-block w-2 h-2 rounded-full ${color}`} />
      {errorCount > 0 ? (
        <span>{errorCount > 1 ? `${errorCount} errors` : "error"}</span>
      ) : status === "running" || busyCount > 0 ? (
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
  const { onMessage } = useWebSocket();
  const setLastError = useWorkspaceStore((s) => s.setLastError);
  const lastError = useWorkspaceStore((s) => s.lastError);

  useEffect(() => {
    return onMessage((msg) => {
      if (msg.type === "error") {
        setLastError((msg as { type: "error"; message: string }).message);
        setTimeout(() => setLastError(null), 5000);
      }
    });
  }, [onMessage, setLastError]);

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
      {/* Global error toast */}
      {lastError && (
        <div className="fixed top-2 left-1/2 -translate-x-1/2 z-50 px-4 py-2
                        bg-app-error/90 text-white text-ui-sm rounded shadow-lg
                        flex items-center gap-2">
          <span>{lastError}</span>
          <button onClick={() => setLastError(null)} className="ml-2 opacity-70 hover:opacity-100">✕</button>
        </div>
      )}

      {/* Toggle bar — auto-sized row */}
      <div className="flex items-center gap-1 px-2 py-1 bg-app-bg-secondary border-b border-app-border select-none max-md:flex-wrap">
        {PANEL_CONFIGS.map((cfg) => {
          const visible = panels[cfg.id]?.visible;
          return (
            <button
              key={cfg.id}
              onClick={() => togglePanel(cfg.id)}
              className={`flex items-center gap-1 px-2 py-1 text-ui-sm rounded transition-colors active:scale-95 ${
                visible
                  ? "bg-app-bg-tertiary text-app-text"
                  : "text-app-text-muted hover:text-app-text-muted hover:bg-app-bg-tertiary"
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