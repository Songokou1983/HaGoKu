import {
  List,
  CheckCircle2,
  Circle,
  AlertCircle,
  Clock,
  PlayCircle,
  PauseCircle,
  Archive,
  MessageSquare,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useState, useEffect, useCallback } from "react";
import { useWorkspaceStore } from "../stores/workspace";
import { useWebSocket } from "../hooks/useWebSocket";
import { PanelHeader } from "../components/PanelHeader";
import { focusLabel } from "../constants/focusAreas";

interface KanbanTask {
  id: string;
  agent: string;
  title: string;
  description: string | null;
  status: string;
  priority: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  result: string | null;
  comments: KanbanComment[];
}

interface KanbanComment {
  id: string;
  task_id: string;
  author: string;
  body: string;
  created_at: string;
}

function agentLabel(agent: string): string {
  // Kanban uses capitalized agent names; map to lowercase stage keys
  const key = agent.toLowerCase();
  return focusLabel(key);
}

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  triage: { icon: <Circle size={12} />, label: "待分配", color: "text-app-text-muted" },
  todo: { icon: <List size={12} />, label: "待办", color: "text-app-text-muted" },
  ready: { icon: <PlayCircle size={12} />, label: "就绪", color: "text-app-accent" },
  running: { icon: <Loader2 size={12} className="animate-spin" />, label: "运行中", color: "text-app-warning" },
  blocked: { icon: <PauseCircle size={12} />, label: "等待确认", color: "text-app-warning" },
  done: { icon: <CheckCircle2 size={12} />, label: "完成", color: "text-app-success" },
  archived: { icon: <Archive size={12} />, label: "归档", color: "text-app-text-muted/50" },
};

function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.triage;
  return (
    <span className={`inline-flex items-center gap-1 text-ui-xs ${config.color}`}>
      {config.icon}
      <span>{config.label}</span>
    </span>
  );
}

function TaskCard({ task }: { task: KanbanTask }) {
  const [expanded, setExpanded] = useState(false);
  const agentDisplayLabel = agentLabel(task.agent);
  const hasComments = task.comments && task.comments.length > 0;

  return (
    <div className="border border-app-border rounded bg-app-bg-secondary p-3 hover:border-app-accent/30 transition-colors duration-150">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-ui-xs font-mono text-app-accent shrink-0">{task.agent}</span>
          <span className="text-ui-xs text-app-text-muted shrink-0">·</span>
          <span className="text-ui-xs text-app-text-muted shrink-0">{agentDisplayLabel}</span>
        </div>
        <StatusBadge status={task.status} />
      </div>

      {/* Title */}
      <div className="text-ui-sm text-app-text mb-1.5 leading-relaxed">{task.title}</div>

      {/* Description */}
      {task.description && (
        <div className="text-ui-xs text-app-text-muted mb-1.5 leading-relaxed line-clamp-2">
          {task.description}
        </div>
      )}

      {/* Result (when done) */}
      {task.status === "done" && task.result && (
        <div className="text-ui-xs text-app-success/80 mt-1.5 bg-app-success/5 rounded px-2 py-1">
          {task.result}
        </div>
      )}

      {/* Time */}
      <div className="flex items-center gap-1 text-ui-xs text-app-text-muted/70">
        <Clock size={10} />
        <span>{task.created_at?.replace("T", " ").substring(0, 16) || "—"}</span>
      </div>

      {/* Comments toggle */}
      {hasComments && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 flex items-center gap-1 text-ui-xs text-app-text-muted hover:text-app-accent transition-colors duration-150 cursor-pointer"
        >
          <MessageSquare size={11} />
          <span>{task.comments.length} 条评论</span>
          <span className="text-[10px]">{expanded ? "▲" : "▼"}</span>
        </button>
      )}

      {/* Comments list */}
      {expanded && hasComments && (
        <div className="mt-2 space-y-1.5 border-t border-app-border pt-2">
          {task.comments.map((comment) => (
            <div key={comment.id} className="text-ui-xs text-app-text-muted leading-relaxed">
              <span className="text-app-text-muted/50">{comment.created_at?.replace("T", " ").substring(0, 16)}</span>
              <span className="mx-1">·</span>
              <span>{comment.body}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PipelineIndicator({ tasks }: { tasks: KanbanTask[] }) {
  const agents = ["Scout", "Cleaner", "Analyst", "Reporter"];
  const taskMap = new Map(tasks.map((t) => [t.agent, t]));

  return (
    <div className="flex items-center gap-1.5 mb-3 px-1">
      {agents.map((agent, i) => {
        const task = taskMap.get(agent);
        const status = task?.status || "triage";
        const isDone = status === "done";
        const isRunning = status === "running";
        const isBlocked = status === "blocked";
        const label = agentLabel(agent);

        return (
          <div key={agent} className="flex items-center gap-1.5">
            {i > 0 && (
              <div
                className={`w-4 h-px ${isDone ? "bg-app-success" : "bg-app-border"}`}
              />
            )}
            <div
              className={`flex items-center gap-1 text-ui-xs px-1.5 py-0.5 rounded ${
                isDone
                  ? "text-app-success"
                  : isRunning
                    ? "text-app-warning"
                    : isBlocked
                      ? "text-app-warning/80"
                      : "text-app-text-muted"
              }`}
              title={`${agent} (${label}): ${status}`}
            >
              {isDone ? (
                <CheckCircle2 size={11} />
              ) : isRunning ? (
                <Loader2 size={11} className="animate-spin" />
              ) : isBlocked ? (
                <PauseCircle size={11} />
              ) : (
                <Circle size={11} />
              )}
              <span>{label}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function KanbanPanel() {
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const [tasks, setTasks] = useState<KanbanTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchKanban = useCallback(async () => {
    if (!currentProject) {
      setTasks([]);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const resp = await fetch(
        `/api/projects/${encodeURIComponent(currentProject)}/kanban/tasks`
      );
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setTasks(data.tasks || []);
    } catch (err) {
      console.error("Failed to fetch kanban tasks:", err);
      setError("无法加载看板数据");
    } finally {
      setLoading(false);
    }
  }, [currentProject]);

  useEffect(() => {
    fetchKanban();
  }, [fetchKanban]);

  // 监听 WebSocket 事件自动刷新看板
  const { onMessage } = useWebSocket();
  useEffect(() => {
    return onMessage((msg: Record<string, unknown>) => {
      const type = msg.type as string;
      if (
        type === "agent_started" ||
        type === "agent_completed" ||
        type === "agent_failed" ||
        type === "tool_called"
      ) {
        fetchKanban();
      }
    });
  }, [onMessage, fetchKanban]);

  if (!currentProject) {
    return (
      <div className="h-full flex flex-col">
        <PanelHeader title="看板" badge={<List size={14} />} />
        <div className="flex-1 flex items-center justify-center text-app-text-muted text-ui-sm">
          请先选择一个项目
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <PanelHeader title="看板" badge={<List size={14} />}>
        <button
          onClick={fetchKanban}
          disabled={loading}
          className="p-1 text-app-text-muted hover:text-app-text disabled:opacity-50 transition-colors duration-150 cursor-pointer"
          aria-label="刷新看板"
          title="刷新看板"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </PanelHeader>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading && tasks.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-app-text-muted text-ui-sm">
            <Loader2 size={16} className="animate-spin mr-2" />
            加载看板中...
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-8 text-app-error text-ui-sm gap-2">
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-app-text-muted text-ui-sm gap-2">
            <Circle size={20} className="opacity-50" />
            <span>当前没有任务</span>
            <span className="text-ui-xs text-app-text-muted/50">
              运行分析后任务将在此显示
            </span>
          </div>
        ) : (
          <>
            {/* Pipeline progress bar */}
            <PipelineIndicator tasks={tasks} />

            {/* Task cards */}
            <div className="space-y-2">
              {tasks.map((task) => (
                <TaskCard key={task.id} task={task} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}