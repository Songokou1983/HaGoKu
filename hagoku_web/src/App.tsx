import { useEffect, useRef, type ReactNode } from "react";
import { useWorkspaceStore, type PanelId } from "./stores/workspace";
import { useWebSocket } from "./hooks/useWebSocket";
import { switchToProject } from "./utils/switchProject";
import ProjectPanel from "./panels/ProjectPanel";
import AnalyzePanel from "./panels/AnalyzePanel";
import ReportPanel from "./panels/ReportPanel";
import KnowledgePanel from "./panels/KnowledgePanel";
import SettingsPanel from "./panels/SettingsPanel";
import PromptLabPanel from "./panels/PromptLabPanel";
import EventPanel from "./panels/EventPanel";
import DoctorPanel from "./panels/DoctorPanel";
import { TitleBar } from "./components/TitleBar";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useThemeStore } from "./stores/theme";
import {
  FolderKanban,
  BarChart3,
  FileText,
  BookOpen,
  Settings,
  Activity,
  List,
  X,
  FlaskConical,
  Stethoscope,
} from "lucide-react";

type NavSection = "work" | "ref" | "dev";

interface NavItem {
  id: PanelId;
  title: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
  section: NavSection;
}

const NAV_ITEMS: NavItem[] = [
  // ── 工作区 ──
  { id: "projects",  title: "项目",   Icon: FolderKanban,  section: "work" },
  { id: "analyze",   title: "分析",   Icon: BarChart3,     section: "work" },
  { id: "report",    title: "报告",   Icon: FileText,      section: "work" },
  // ── 参考 ──
  { id: "knowledge", title: "知识库", Icon: BookOpen,      section: "ref" },
  // ── 开发者 ──
  { id: "lab",       title: "Prompt Lab", Icon: FlaskConical, section: "dev" },
  { id: "doctor",    title: "HaGoKu Doctor", Icon: Stethoscope,  section: "dev" },
  { id: "events",    title: "运行日志", Icon: Activity,     section: "dev" },
  { id: "settings",  title: "设置",   Icon: Settings,      section: "dev" },
];

const SECTION_LABELS: Record<NavSection, string> = {
  work: "工作区",
  ref:  "参考",
  dev:  "开发者",
};

const PANEL_MAP: Record<PanelId, ReactNode> = {
  projects:  <ProjectPanel />,
  analyze:   <ErrorBoundary><AnalyzePanel /></ErrorBoundary>,
  report:    <ReportPanel />,
  knowledge: <KnowledgePanel />,
  events:    <EventPanel />,
  settings:  <SettingsPanel />,
  lab:       <PromptLabPanel />,
  doctor:    <DoctorPanel />,
};

/** 固定顺序，保证切换侧栏时面板不卸载（避免分析页 local state 被重置） */
const PANEL_ORDER: PanelId[] = [
  "projects",
  "analyze",
  "report",
  "knowledge",
  "events",
  "lab",
  "doctor",
  "settings",
];

function SystemStatus() {
  const status = useWorkspaceStore((s) => s.status);
  const agents = useWorkspaceStore((s) => s.agents);

  const busyCount = Object.values(agents).filter((s) => s === "running").length;
  const errorCount = Object.values(agents).filter((s) => s === "error").length;

  const dotColor =
    errorCount > 0
      ? "bg-app-error"
      : status === "running" || busyCount > 0
        ? "bg-app-warning animate-pulse"
        : status === "done"
          ? "bg-app-success"
          : "bg-app-text-muted";

  const label =
    errorCount > 0
      ? `${errorCount} 个异常`
      : status === "running" || busyCount > 0
        ? busyCount > 0 ? `${busyCount} 个运行中` : "运行中"
        : status === "done"
          ? "完成"
          : "就绪";

  return (
    <div className="flex items-center gap-1.5 text-ui-xs text-app-text-muted">
      <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
      <span>{label}</span>
    </div>
  );
}

export default function App() {
  const { onMessage, send } = useWebSocket();
  const theme = useThemeStore((s) => s.theme);
  const setLastError = useWorkspaceStore((s) => s.setLastError);
  const lastError = useWorkspaceStore((s) => s.lastError);
  const activeView = useWorkspaceStore((s) => s.activeView);
  const setActiveView = useWorkspaceStore((s) => s.setActiveView);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const initialSwitchSent = useRef(false);

  useEffect(() => {
    return onMessage((msg) => {
      if (msg.type === "error") {
        setLastError((msg as { type: "error"; message: string }).message);
        setTimeout(() => setLastError(null), 5000);
      }
    });
  }, [onMessage, setLastError]);

  useEffect(() => {
    const proj = useWorkspaceStore.getState().currentProject;
    if (proj && !initialSwitchSent.current) {
      initialSwitchSent.current = true;
      switchToProject(proj, send, setCurrentProject);
    }
  }, []);


  return (
    <div className="h-full flex flex-col bg-app-bg" data-theme={theme}>
      <TitleBar />
      <div className="flex-1 min-h-0"
      style={{
        display: "grid",
        gridTemplateColumns: "180px 1fr",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* ── Left sidebar ── */}
      <aside className="flex flex-col border-r border-app-border bg-app-bg-secondary overflow-hidden">
        {/* Logo */}
        <div className="px-4 py-3 border-b border-app-border shrink-0">
          <div className="text-app-text font-mono font-semibold tracking-wide">HaGoKu</div>
          <div className="text-ui-xs text-app-text-muted mt-0.5">v2.3.1 · 数据分析师</div>
        </div>

        {/* Current project indicator */}
        <div className="px-3 py-2 border-b border-app-border shrink-0">
          <div className="text-ui-xs text-app-text-muted mb-1">当前项目</div>
          {currentProject ? (
            <button
              onClick={() => setActiveView("projects")}
              title={currentProject}
              className="text-ui-sm text-app-accent truncate w-full text-left cursor-pointer hover:brightness-125 transition-all duration-150"
            >
              {currentProject}
            </button>
          ) : (
            <button
              onClick={() => setActiveView("projects")}
              className="text-ui-xs text-app-text-muted cursor-pointer hover:text-app-text transition-colors duration-150"
            >
              未选择项目 →
            </button>
          )}
        </div>

        {/* Nav items with section headers */}
        <nav className="flex-1 py-1 overflow-y-auto">
          {NAV_ITEMS.reduce<ReactNode[]>((acc, { id, title, Icon, section }, i) => {
            const prev = i > 0 ? NAV_ITEMS[i - 1] : null;
            if (!prev || prev.section !== section) {
              acc.push(
                <div key={`hdr-${section}`} className="px-3 pt-3 pb-1 text-ui-xs text-app-text-muted/60 font-medium uppercase tracking-wider select-none">
                  {SECTION_LABELS[section]}
                </div>,
              );
            }
            const isActive = activeView === id;
            acc.push(
              <button
                key={id}
                onClick={() => setActiveView(id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-ui-sm transition-colors duration-150 cursor-pointer text-left
                  ${isActive
                    ? "bg-app-accent/15 text-app-accent border-l-2 border-app-accent"
                    : "text-app-text-muted hover:text-app-text hover:bg-app-bg-tertiary border-l-2 border-transparent"
                  }`}
              >
                <Icon size={15} />
                <span>{title}</span>
              </button>,
            );
            return acc;
          }, [])}
        </nav>

        {/* System status */}
        <div className="px-3 py-2.5 border-t border-app-border shrink-0">
          <SystemStatus />
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="overflow-hidden relative h-full min-h-0">
        {/* Global error toast */}
        {lastError && (
          <div className="absolute top-2 left-1/2 -translate-x-1/2 z-50 px-4 py-2
                          bg-app-error/90 text-white text-ui-sm rounded shadow-lg
                          flex items-center gap-2">
            <span>{lastError}</span>
            <button
              aria-label="关闭提示"
              onClick={() => setLastError(null)}
              className="ml-2 opacity-70 hover:opacity-100 transition-opacity duration-150 focus:outline-none focus:ring-1 focus:ring-white rounded cursor-pointer"
            >
              <X size={12} />
            </button>
          </div>
        )}
        {PANEL_ORDER.map((id) => (
          <div
            key={id}
            className={
              activeView === id
                ? "h-full min-h-0 overflow-hidden"
                : "hidden"
            }
            aria-hidden={activeView !== id}
          >
            {PANEL_MAP[id]}
          </div>
        ))}
      </main>
    </div>
    </div>
  );
}
