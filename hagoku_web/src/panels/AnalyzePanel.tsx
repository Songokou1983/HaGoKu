import { useState, useCallback, useEffect, useRef } from "react";
import { guardrailsRunCompletedInfo } from "../utils/wsGuardrails";
import { useWebSocket } from "../hooks/useWebSocket";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import {
  Loader2, WifiOff, ArrowRight, FolderOpen, Upload,
  ChevronDown, PlayCircle, RotateCcw,
  CheckCircle2, FileText, ShieldAlert, X,
} from "lucide-react";
import type {
  AgentKey, AgentRunState, SessionPhase,
  ConvoMessage, ProjectFile,
} from "./AnalyzePanel/types";
import {
  resolveAgentKey, parsePauseInteractionRevision,
  parseFieldReview, parseCleaningAssessment, parseCleaningReview,
  parseAnalystReview,
} from "./AnalyzePanel/parsers";
import { fmtSize, uid, formatScoutUserInputFactLine, formatStageProceedFactLine } from "./AnalyzePanel/utils";
import { PipelineBar } from "./AnalyzePanel/PipelineBar";
import { ConvoFeed } from "./AnalyzePanel/ConvoFeed";
import { ClearHistoryButton } from "./AnalyzePanel/ClearHistoryButton";

// ── Main component ────────────────────────────────────────────

export default function AnalyzePanel() {
  const { send } = useWebSocket();
  const status = useWorkspaceStore((s) => s.status);
  const connectionStatus = useWorkspaceStore((s) => s.connectionStatus);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const projects = useWorkspaceStore((s) => s.projects);
  const setActiveView = useWorkspaceStore((s) => s.setActiveView);
  const resetRunUiState = useWorkspaceStore((s) => s.resetRunUiState);

  // Session state machine
  const [phase, setPhase] = useState<SessionPhase>("setup");
  const [messages, setMessages] = useState<ConvoMessage[]>([]);
  const [agentStates, setAgentStates] = useState<Record<AgentKey, AgentRunState>>({
    scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle",
  });
  const [agentElapsed, setAgentElapsed] = useState<Record<AgentKey, number>>({
    scout: 0, cleaner: 0, analyst: 0, reporter: 0,
  });
  const agentStartTimes = useRef<Record<string, number>>({});
  // Track which agent is waiting for user reply
  const [waitingAgent, setWaitingAgent] = useState<AgentKey | null>(null);
  const [replyText, setReplyText] = useState("");
  const [queryText, setQueryText] = useState("");
  const queryRef = useRef("");  // 保存原始分析目标，不受 UI 状态变化影响
  const [resultReportUrl, setResultReportUrl] = useState<string | null>(null);
  const [guardrailsBlocked, setGuardrailsBlocked] = useState(false);
  const [blockedRunId, setBlockedRunId] = useState<string | null>(null);
  const replyInputRef = useRef<HTMLTextAreaElement>(null);
  /** 当前暂停点是否对应「字段表」工作流（用于行点选、空回车确认） */
  const [activeFieldReviewId, setActiveFieldReviewId] = useState<string | null>(null);
  /** 多轮对齐：当前 field_review 卡片的 interaction_revision（递增时更新同一卡片） */
  const [activeFieldReviewRevision, setActiveFieldReviewRevision] = useState<number>(-1);
  const [activeCleaningReviewId, setActiveCleaningReviewId] = useState<string | null>(null);
  const [activeCleaningReviewRevision, setActiveCleaningReviewRevision] = useState<number>(-1);
  const [activeAnalystReviewId, setActiveAnalystReviewId] = useState<string | null>(null);
  const [activeAnalystReviewRevision, setActiveAnalystReviewRevision] = useState<number>(-1);
  /** 跨阶段闸门：gate_to_cleaning 暂停点（展示「确认进入清洗」/「还有补充」按钮） */
  const [gateOpen, setGateOpen] = useState(false);
  /** 强确认类按钮默认收起，用户点「我已核对」后再展示，避免与输入区误触混淆 */
  /** 字段表刷新时递增，驱动对话区把该卡片滚入视口（原地更新时 length 不变，仅靠 length 不会滚） */
  const [fieldReviewScrollNonce, setFieldReviewScrollNonce] = useState(0);
  /** 最近一次 respond：WS 报错「无暂停」等时恢复等待态 */
  const replySnapshotRef = useRef<{ agent: AgentKey; gate: boolean } | null>(null);

  // File / project state
  const [dataPath, setDataPath] = useState("");
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [showFileDropdown, setShowFileDropdown] = useState(false);
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const projectDropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node))
        setShowFileDropdown(false);
      if (projectDropdownRef.current && !projectDropdownRef.current.contains(e.target as Node))
        setShowProjectDropdown(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  const loadFiles = useCallback((proj: string) => {
    setFilesLoading(true);
    fetch(`/api/projects/${proj}/files`)
      .then((r) => r.json())
      .then((d: { files: ProjectFile[] }) => setProjectFiles(d.files ?? []))
      .catch(() => setProjectFiles([]))
      .finally(() => setFilesLoading(false));
  }, []);

  useEffect(() => {
    if (!currentProject) { setDataPath(""); setProjectFiles([]); return; }
    loadFiles(currentProject);
    fetch(`/api/projects/${currentProject}/detail`)
      .then((r) => r.json())
      .then((d: { data_path?: string; last_query?: string }) => {
        if (d.data_path) setDataPath(d.data_path);
        if (d.last_query && phase === "setup") setQueryText(d.last_query);
      })
      .catch(() => {});
  }, [currentProject, loadFiles]);

  useAgentStatusSync();
  const batch = useBatchEvents();

  // Process WS events
  useEffect(() => {
    if (batch.length === 0) return;
    for (const msg of batch) {
      if (msg.type === "ack" && msg.cmd === "respond") {
        replySnapshotRef.current = null;
        continue;
      }
      if (msg.type === "error") {
        const detail = typeof msg.message === "string" ? msg.message.trim() : "";
        const iso = new Date().toISOString();
        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            role: "system",
            text: detail || "服务器返回错误",
            timestamp: iso,
          },
        ]);
        const snap = replySnapshotRef.current;
        const recoverable = /No agent is waiting|No active orchestrator/i.test(detail);
        if (recoverable && snap) {
          setWaitingAgent(snap.agent);
          setGateOpen(snap.gate);
          replySnapshotRef.current = null;
        }
        continue;
      }
      if (msg.type === "event" && msg.data) {
        const d = msg.data;
        const agentKey = resolveAgentKey(d.agent);

        // Agent lifecycle → update pipeline（不在此插入固定「台词」）
        if (d.event_type === "agent_started" && agentKey) {
          agentStartTimes.current[agentKey] = Date.now();
          setAgentStates((prev) => ({ ...prev, [agentKey]: "running" }));
        }
        if (d.event_type === "agent_completed" && agentKey) {
          const elapsed = Math.round((Date.now() - (agentStartTimes.current[agentKey] ?? Date.now())) / 1000);
          setAgentStates((prev) => ({ ...prev, [agentKey]: "done" }));
          setAgentElapsed((prev) => ({ ...prev, [agentKey]: elapsed }));
        }
        if (d.event_type === "agent_failed" && agentKey) {
          setAgentStates((prev) => ({ ...prev, [agentKey]: "error" }));
          const detail = (d.data as Record<string, unknown>)?.error;
          if (typeof detail === "string" && detail.trim()) {
            setMessages((prev) => [
              ...prev,
              { id: uid(), role: "system", text: detail.trim(), timestamp: d.timestamp },
            ]);
          }
        }

        // 进度提示：后端在长时间步骤会发 agent_thinking；此前对话区空白易被误认为「无回复」
        if (d.event_type === "agent_thinking") {
          const raw = (d.data as Record<string, unknown> | undefined)?.thought;
          if (typeof raw === "string") {
            const t = raw.trim();
            if (t) {
              const short = t.length > 220 ? `${t.slice(0, 217)}…` : t;
              setMessages((prev) => [
                ...prev,
                { id: uid(), role: "system", text: short, timestamp: d.timestamp },
              ]);
            }
          }
        }

        // Reporter skipped (guardrails blocked) → set skipped state
        if (d.agent === "reporter" && d.event_type === "agent_completed") {
          const data = d.data as Record<string, unknown>;
          const elapsed = Math.round((Date.now() - (agentStartTimes.current["reporter"] ?? Date.now())) / 1000);
          if (data?.skipped === true) {
            setAgentStates((prev) => ({ ...prev, reporter: "skipped" }));
            setAgentElapsed((prev) => ({ ...prev, reporter: elapsed }));
            setWaitingAgent(null);
            setPhase("done");
          } else {
            setAgentStates((prev) => ({ ...prev, reporter: "done" }));
            setAgentElapsed((prev) => ({ ...prev, reporter: elapsed }));
            const proj = data?.project_name as string ?? currentProject ?? "default";
            setResultReportUrl(`/api/reports/${proj}`);
            setWaitingAgent(null);
            setPhase("done");
          }
        }

        // 暂停点：结构化 field_review 用工作流卡片展示；message 由编排层填入简短 Agent 气泡（可与卡片并存）
        if (d.event_type === "user_input_requested") {
          setGateOpen(false);  // 每次暂停默认关，有 gate 才开
          const dataObj = (d.data ?? {}) as Record<string, unknown>;
          const gatePayload = dataObj.gate as { phase?: string; prompt?: string } | undefined;
          const fr = parseFieldReview(dataObj.field_review);
          const ca = parseCleaningAssessment(dataObj.cleaning_assessment);
          const cr = parseCleaningReview(dataObj.cleaning_review);
          const ar = parseAnalystReview(dataObj.analyst_review);
          const incRev = parsePauseInteractionRevision(dataObj);
          const incomingRevision = incRev !== null ? incRev : Infinity;
          if (fr) {
            // 多轮对齐：同 revision 或递增 revision → 更新同一张卡片（不堆叠）；revision 未变时
            // 常见于闸门「还有补充」回到字段表（后端已递增 revision；此处兜底同号原地更新）。
            const patchInPlace =
              activeFieldReviewId !== null
              && (
                incomingRevision === activeFieldReviewRevision
                || incomingRevision > activeFieldReviewRevision
              );
            if (patchInPlace) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === activeFieldReviewId ? { ...m, fieldReview: fr, timestamp: d.timestamp } : m,
                ),
              );
            } else {
              // 新卡片
              const wfId = uid();
              setActiveFieldReviewId(wfId);
              setMessages((prev) => [
                ...prev,
                {
                  id: wfId,
                  role: "workflow",
                  text: "",
                  timestamp: d.timestamp,
                  fieldReview: fr,
                },
              ]);
            }
            setActiveFieldReviewRevision(incomingRevision);
            setFieldReviewScrollNonce((n) => n + 1);
          } else if (!gatePayload && !cr && !ar) {
            // 非结构化暂停（且无清洗/分析卡）时才清 field_review 追踪；避免 Cleaner 暂停误清
            setActiveFieldReviewId(null);
            setActiveFieldReviewRevision(-1);
            setFieldReviewScrollNonce(0);
          }
          if (cr) {
            const patchCleaning =
              activeCleaningReviewId !== null
              && incRev !== null
              && (
                incRev === activeCleaningReviewRevision
                || incRev > activeCleaningReviewRevision
              );
            if (patchCleaning) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === activeCleaningReviewId
                    ? { ...m, cleaningReview: cr, timestamp: d.timestamp }
                    : m,
                ),
              );
            } else {
              const cid = uid();
              setActiveCleaningReviewId(cid);
              setMessages((prev) => [
                ...prev,
                {
                  id: cid,
                  role: "workflow",
                  text: "",
                  timestamp: d.timestamp,
                  cleaningReview: cr,
                },
              ]);
            }
            if (incRev !== null) setActiveCleaningReviewRevision(incRev);
          } else {
            setActiveCleaningReviewId(null);
            setActiveCleaningReviewRevision(-1);
          }
          if (ca) {
            // 清洗评估：结构化展示 LLM 的大白话评估
            const cid = uid();
            const colLines = ca.columns.map((c) =>
              `<tr><td style="padding:4px 8px;border:1px solid #2a3040">${c.column}</td><td style="padding:4px 8px;border:1px solid #2a3040;color:#4ade80">${c.action === "clean" ? "清洗" : "不清洗"}</td><td style="padding:4px 8px;border:1px solid #2a3040">${c.reason}</td></tr>`
            ).join("");
            const tableHtml = `<div style="margin-top:8px"><table style="width:100%;border-collapse:collapse;font-size:14px"><thead><tr style="background:#1e2430"><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">字段</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:center;width:80px">建议</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">原因</th></tr></thead><tbody>${colLines}</tbody></table></div>`;
            setMessages((prev) => [
              ...prev,
              {
                id: cid,
                role: "agent",
                text: ca.summary,
                html: `<p><strong>${ca.summary}</strong></p>${tableHtml}`,
                timestamp: d.timestamp,
              } as ConvoMessage,
            ]);
          }
          if (ar) {
            const patchAnalyst =
              activeAnalystReviewId !== null
              && incRev !== null
              && (
                incRev === activeAnalystReviewRevision
                || incRev > activeAnalystReviewRevision
              );
            if (patchAnalyst) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === activeAnalystReviewId
                    ? { ...m, analystReview: ar, timestamp: d.timestamp }
                    : m,
                ),
              );
            } else {
              const aid = uid();
              setActiveAnalystReviewId(aid);
              setMessages((prev) => [
                ...prev,
                {
                  id: aid,
                  role: "workflow",
                  text: "",
                  timestamp: d.timestamp,
                  analystReview: ar,
                },
              ]);
            }
            if (incRev !== null) setActiveAnalystReviewRevision(incRev);
          } else {
            setActiveAnalystReviewId(null);
            setActiveAnalystReviewRevision(-1);
          }
          // 跨阶段闸门：gate_to_cleaning（Scout 对齐后、进入清洗前）
          if (gatePayload) {
            setGateOpen(true);
            const prompt =
              typeof gatePayload.prompt === "string" ? gatePayload.prompt.trim() : "";
            if (prompt) {
              const gateId = uid();
              setMessages((prev) => [
                ...prev,
                {
                  id: gateId,
                  role: "workflow",
                  text: prompt,
                  timestamp: d.timestamp,
                },
              ]);
            }
          }
          const raw = dataObj.message;
          const agentMsg = typeof raw === "string" ? raw.trim() : "";
          if (agentMsg) {
            setMessages((prev) => [
              ...prev,
              { id: uid(), role: "agent", text: agentMsg, timestamp: d.timestamp },
            ]);
          }
          const pausedAgent = resolveAgentKey(d.agent) ?? "scout";
          setWaitingAgent(pausedAgent);
          setPhase("running");
          setTimeout(() => replyInputRef.current?.focus(), 100);
        }

        if (d.event_type === "user_input_received") {
          const inner = (d.data ?? {}) as Record<string, unknown>;
          if (agentKey === "scout") {
            const hasNewFields =
              "parse_applied_count" in inner
              || "columns_still_needing_input" in inner
              || "pure_confirm" in inner;
            let line = "";
            if (hasNewFields) {
              line = formatScoutUserInputFactLine(inner);
            } else {
              const applied = inner.applied_field_updates;
              const lines = Array.isArray(applied)
                ? applied.filter((x): x is string => typeof x === "string" && x !== null && (x as string).trim() !== "")
                : [];
              if (lines.length > 0) {
                line = `字段理解写入: ${lines.join("；")}`;
              }
            }
            if (line) {
              setMessages((prev) => [
                ...prev,
                { id: uid(), role: "system", text: line, timestamp: d.timestamp },
              ]);
            }
          } else if (agentKey === "cleaner" && typeof inner.proceed_accepted === "boolean") {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "system",
                text: formatStageProceedFactLine("清洗", inner),
                timestamp: d.timestamp,
              },
            ]);
          } else if (agentKey === "analyst" && typeof inner.proceed_accepted === "boolean") {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "system",
                text: formatStageProceedFactLine("统计", inner),
                timestamp: d.timestamp,
              },
            ]);
          }
        }

        // Run completed with guardrails blocked（说明走底部 CTA，不插固定对话文案）
        if (d.event_type === "run_completed") {
          const runPayload = (d.data ?? {}) as Record<string, unknown>;
          if (runPayload.cancelled === true) {
            setWaitingAgent(null);
            setActiveFieldReviewId(null);
            setActiveFieldReviewRevision(-1);
            setFieldReviewScrollNonce(0);
            setActiveCleaningReviewId(null);
            setActiveCleaningReviewRevision(-1);
            setActiveAnalystReviewId(null);
            setActiveAnalystReviewRevision(-1);
            setGateOpen(false);
            setPhase("setup");
            setAgentStates({ scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" });
            setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
            setResultReportUrl(null);
            setGuardrailsBlocked(false);
            setBlockedRunId(null);
            continue;
          }
          const gr = guardrailsRunCompletedInfo({
            event_type: d.event_type,
            agent: d.agent,
            data: d.data as Record<string, unknown> | undefined,
          });
          if (gr.guardrailsBlocked) {
            setGuardrailsBlocked(true);
            if (gr.runId) setBlockedRunId(gr.runId);
            setWaitingAgent(null);
            setActiveFieldReviewId(null);
            setActiveFieldReviewRevision(-1);
            setFieldReviewScrollNonce(0);
            setActiveCleaningReviewId(null);
            setActiveCleaningReviewRevision(-1);
            setActiveAnalystReviewId(null);
            setActiveAnalystReviewRevision(-1);
            setGateOpen(false);
            setPhase("done");
          }
        }
      }
    }
  }, [batch]);

  const submitUserReply = useCallback(
    (raw: string) => {
      if (!waitingAgent) return;
      const outgoing = raw.trim();
      if (!outgoing) return;
      const displayBubble = outgoing;
      replySnapshotRef.current = { agent: waitingAgent, gate: gateOpen };
      const sent = send("respond", { text: outgoing });
      if (!sent) {
        replySnapshotRef.current = null;
        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            role: "system",
            text: "当前未连接到服务器，回复未发出。请确认右上角连接状态后重试。",
            timestamp: new Date().toISOString(),
          },
        ]);
        return;
      }
      const ts = new Date().toISOString();
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "user",
          text: displayBubble,
          timestamp: ts,
        },
      ]);
      setReplyText("");
    setQueryText("");
      setWaitingAgent(null);
      setGateOpen(false);
      // 多轮对齐：不清 activeFieldReviewId / activeCleaningReviewId / activeAnalystReviewId；
      // 下一轮 user_input_requested 依赖同一 id 原地更新工作流卡片。
    },
    [send, waitingAgent, gateOpen],
  );

  const handleReply = useCallback(() => {
    submitUserReply(replyText);
  }, [submitUserReply, replyText]);

  /** 与 PROJECT.md「人机互动」一致：不在此步插入固定 Agent 话术；由编排层在暂停点生成说明。 */
  const handleStartSession = useCallback(() => {
    if (!currentProject || !dataPath) return;
    setMessages([]);
    setAgentStates({ scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" });
    setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
    setGuardrailsBlocked(false);
    setBlockedRunId(null);
    setResultReportUrl(null);
    setWaitingAgent(null);
    setReplyText("");
    setActiveFieldReviewId(null);
    setActiveFieldReviewRevision(-1);
    setFieldReviewScrollNonce(0);
    setActiveCleaningReviewId(null);
    setActiveCleaningReviewRevision(-1);
    setActiveAnalystReviewId(null);
    setActiveAnalystReviewRevision(-1);
    setGateOpen(false);
    setPhase("running");
    const q = queryText.trim();
    queryRef.current = q;  // 锁定原始 query，后续不会变
    send("analyze", {
      data_path: dataPath,
      query: q || "",
      project_name: currentProject ?? "default",
      phase: "full",
    });
  }, [send, dataPath, currentProject, queryText]);

  const handleReset = useCallback(() => {
    send("cancel_analysis", {});
    resetRunUiState();
    setPhase("setup");
    setMessages([]);
    setWaitingAgent(null);
    setReplyText("");
    setActiveFieldReviewId(null);
    setActiveFieldReviewRevision(-1);
    setFieldReviewScrollNonce(0);
    setActiveCleaningReviewId(null);
    setActiveCleaningReviewRevision(-1);
    setActiveAnalystReviewId(null);
    setActiveAnalystReviewRevision(-1);
    setGateOpen(false);
    setResultReportUrl(null);
    setGuardrailsBlocked(false);
    setBlockedRunId(null);
    setAgentStates({ scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" });
    setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
  }, [send, resetRunUiState]);

  const handleUpload = useCallback(async (file: File) => {
    if (!currentProject) return;
    setUploading(true);
    setUploadError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`/api/projects/${currentProject}/upload`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "上传失败" }));
        throw new Error(err.detail ?? "上传失败");
      }
      const data = await res.json() as { path: string };
      setDataPath(data.path);
      loadFiles(currentProject);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [currentProject, loadFiles]);

  const selectedFileName = dataPath ? dataPath.split("/").pop() ?? dataPath : null;
  const [fileExists, setFileExists] = useState(false);
  useEffect(() => {
    if (!currentProject || !dataPath) { setFileExists(false); return; }
    fetch(`/api/projects/${currentProject}/files`)
      .then(r => r.json())
      .then((d: { files?: Array<{path: string}> }) => {
        setFileExists((d.files || []).some((f: {path: string}) => f.path === dataPath));
      })
      .catch(() => setFileExists(false));
  }, [currentProject, dataPath]);
  const canStart = !!currentProject && !!dataPath && fileExists && connectionStatus === "connected";
  const scoutFieldReviewOpen =
    Boolean(activeFieldReviewId) && waitingAgent === "scout";
  const cleanerCleaningReviewOpen =
    Boolean(activeCleaningReviewId) && waitingAgent === "cleaner";
  const analystReviewOpen =
    Boolean(activeAnalystReviewId) && waitingAgent === "analyst";
  const canSendReply =
    !!waitingAgent && replyText.trim().length > 0;
  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text relative">
      <PanelHeader title="分析">
        {(
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleReset}
              className="flex items-center gap-1 px-2 py-0.5 border border-app-border rounded text-ui-xs normal-case tracking-normal font-medium text-app-text
                hover:border-app-accent hover:text-app-accent transition-colors cursor-pointer"
            >
              <RotateCcw size={12} />
              重置分析
            </button>
            <ClearHistoryButton currentProject={currentProject} onClear={handleReset} />
          </div>
        )}
      </PanelHeader>

      {/* ── Connection overlay ── */}
      {connectionStatus === "disconnected" && (
        <div className="absolute inset-0 bg-app-bg/90 flex flex-col items-center justify-center gap-2 z-20">
          <WifiOff size={28} className="text-app-text-muted" />
          <span className="text-ui-base text-app-error">连接断开</span>
          <span className="text-ui-xs text-app-text-muted">正在重新连接…</span>
        </div>
      )}
      {(connectionStatus === "connecting" || connectionStatus === "reconnecting") && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-app-bg/80 backdrop-blur-sm">
          <Loader2 size={20} className="animate-spin text-app-accent" />
          <span className="text-ui-sm text-app-text-muted">正在连接服务器…</span>
        </div>
      )}

      {/* ── Setup: project + file selectors ── */}
      <div className="px-3 py-2 border-b border-app-border bg-app-bg-secondary shrink-0 space-y-2">
        {/* Project selector */}
        <div className="flex items-center gap-2">
          <span className="text-ui-xs text-app-text-muted w-12 shrink-0">项目</span>
          <div className="relative flex-1" ref={projectDropdownRef}>
            <button
              onClick={() => setShowProjectDropdown((v) => !v)}
              disabled={phase === "running"}
              className={`w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border rounded
                         text-ui-sm transition-colors
                         ${phase !== "running"
                           ? "border-app-border hover:border-app-accent cursor-pointer text-app-text"
                           : "border-app-border opacity-50 cursor-not-allowed text-app-text-muted"}`}
            >
              <FolderOpen size={13} className="text-app-accent shrink-0" />
              <span className="flex-1 text-left truncate font-mono">{currentProject ?? "— 选择项目 —"}</span>
              <ChevronDown size={12} className="text-app-text-muted shrink-0" />
            </button>
            {showProjectDropdown && (
              <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-48 overflow-y-auto">
                {projects.length === 0
                  ? <div className="px-3 py-2 text-ui-xs text-app-text-muted">暂无项目</div>
                  : projects.map((p) => (
                    <button key={p} onClick={() => { setCurrentProject(p); setShowProjectDropdown(false); }}
                      className={`w-full text-left px-3 py-1.5 text-ui-sm font-mono hover:bg-app-bg cursor-pointer
                        ${p === currentProject ? "text-app-accent" : "text-app-text"}`}>
                      {p === currentProject && <CheckCircle2 size={11} className="inline mr-1.5 text-app-accent" />}
                      {p}
                    </button>
                  ))}
                <div className="border-t border-app-border">
                  <button onClick={() => { setShowProjectDropdown(false); setActiveView("projects"); }}
                    className="w-full text-left px-3 py-1.5 text-ui-xs text-app-accent hover:bg-app-bg cursor-pointer">
                    + 新建项目 →
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* File selector */}
        <div className="flex items-center gap-2">
          <span className="text-ui-xs text-app-text-muted w-12 shrink-0">数据</span>
          <div className="relative flex-1" ref={dropdownRef}>
            <button
              disabled={!currentProject || phase === "running"}
              onClick={() => setShowFileDropdown((v) => !v)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border rounded text-ui-sm transition-colors
                ${currentProject && phase !== "running"
                  ? "border-app-border hover:border-app-accent cursor-pointer text-app-text"
                  : "border-app-border opacity-40 cursor-not-allowed text-app-text-muted"}`}
            >
              <FileText size={13} className={selectedFileName ? "text-app-accent shrink-0" : "text-app-text-muted shrink-0"} />
              <span className="flex-1 text-left truncate font-mono text-ui-xs">{selectedFileName ?? "— 选择文件 —"}</span>
              {filesLoading
                ? <Loader2 size={12} className="animate-spin text-app-text-muted shrink-0" />
                : <ChevronDown size={12} className="text-app-text-muted shrink-0" />}
            </button>
            {showFileDropdown && currentProject && (
              <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-56 overflow-y-auto">
                {projectFiles.length === 0
                  ? <div className="px-3 py-3 text-ui-xs text-app-text-muted text-center">暂无数据文件，请上传</div>
                  : projectFiles.map((f) => (
                    <button key={f.path} onClick={() => { setDataPath(f.path); setShowFileDropdown(false); }}
                      className={`w-full text-left px-3 py-2 hover:bg-app-bg cursor-pointer border-b border-app-border/50 last:border-0
                        ${f.path === dataPath ? "text-app-accent" : "text-app-text"}`}>
                      <div className="flex items-center gap-2">
                        {f.path === dataPath && <CheckCircle2 size={11} className="text-app-accent shrink-0" />}
                        <span className="text-ui-xs font-mono truncate flex-1">{f.name}</span>
                        <span className="text-ui-xs text-app-text-muted shrink-0">{fmtSize(f.size)}</span>
                      </div>
                    </button>
                  ))}
              </div>
            )}
          </div>
          {/* Upload button */}
          <div className="relative shrink-0">
            <input ref={fileInputRef} type="file"
              accept=".csv,.tsv,.json,.jsonl,.xlsx,.xls,.parquet,.txt"
              className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              disabled={!currentProject || uploading || phase === "running"}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleUpload(f); }}
            />
            <button disabled={!currentProject || uploading || phase === "running"}
              className={`flex items-center gap-1 px-2 py-1.5 border rounded text-ui-xs transition-colors
                ${currentProject && !uploading && phase !== "running"
                  ? "border-app-accent text-app-accent hover:bg-app-accent hover:text-white cursor-pointer"
                  : "border-app-border text-app-text-muted opacity-40 cursor-not-allowed"}`}>
              {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
              {uploading ? "上传中…" : "上传"}
            </button>
          </div>
        </div>
        {uploadError && (
          <div className="flex items-center gap-1 text-ui-xs text-app-error">
            <X size={11} />{uploadError}
            <button onClick={() => setUploadError(null)} className="ml-auto text-app-text-muted hover:text-app-text cursor-pointer">忽略</button>
          </div>
        )}
      </div>

      {/* ── Setup idle: start button ── */}
      {phase === "setup" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6">
          {!currentProject || !dataPath ? (
            <div className="text-center space-y-2">
              <div className="text-app-text-muted text-ui-sm">
                {!currentProject ? "请先选择一个项目" : "请选择或上传数据文件"}
              </div>
              <div className="text-app-text-muted text-ui-xs">准备好后点击"开始分析"</div>
            </div>
          ) : (
            <>
              <div className="text-center space-y-2">
                <div className="text-ui-sm text-app-text-muted">项目和数据文件已就绪</div>
                <div className="text-ui-xs text-app-text-muted opacity-60">
                  需要暂停确认时会在对话区提示，并在下方出现输入框
                </div>
              </div>
              <div className="w-full max-w-md">
                <textarea
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                  placeholder="你想分析什么？例如：这批广告投放的 ROI 如何？哪个渠道转化最高？"
                  rows={3}
                  className="w-full px-3 py-2 bg-app-bg border border-app-border rounded-md text-ui-sm text-app-text placeholder:text-app-text-muted focus:outline-none focus:border-app-accent resize-none transition-colors"
                />
              </div>
            </>
          )}
          <button
            onClick={handleStartSession}
            disabled={!canStart}
            className={`flex items-center gap-2 px-6 py-3 rounded-lg text-ui-base font-medium transition-all duration-200
              ${canStart
                ? "bg-app-accent hover:bg-app-accent-hover text-white cursor-pointer shadow-lg hover:shadow-app-accent/30 hover:-translate-y-0.5"
                : "bg-app-bg-secondary border border-app-border text-app-text-muted cursor-not-allowed"}`}
          >
            <PlayCircle size={18} />
            开始分析
          </button>
        </div>
      )}

      {/* ── Query / running / done: conversation view ── */}
      {phase !== "setup" && (
        <>
          {/* Pipeline bar */}
          <div className="px-3 py-2 border-b border-app-border shrink-0">
            <PipelineBar states={agentStates} elapsed={agentElapsed} />
          </div>

          {/* Running progress bar */}
          {status === "running" && (
            <div className="h-0.5 bg-app-accent animate-pulse shrink-0" />
          )}

          {/* Conversation feed */}
          <ConvoFeed
            messages={messages}
            scrollFieldTableId={activeFieldReviewId}
            scrollFieldTableNonce={fieldReviewScrollNonce}
          />

          {/* Agent reply input — shown when any agent is waiting */}
          {waitingAgent && (
            <div className="px-3 pb-2 shrink-0 border-t border-app-border/60 pt-2 motion-safe:transition-colors">
              {(cleanerCleaningReviewOpen) && (
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => submitUserReply("确认继续")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium
                      bg-app-accent text-white hover:bg-app-accent-hover cursor-pointer motion-safe:transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    确认继续
                  </button>
                </div>
              )}
              {analystReviewOpen && (
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => submitUserReply("确认继续")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium
                      bg-app-accent text-white hover:bg-app-accent-hover cursor-pointer motion-safe:transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    确认继续
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      submitUserReply("已核对上表中的 p 值、效应量与置信区间，同意进入报告阶段")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium border
                      border-app-border text-app-text hover:border-app-accent hover:text-app-accent cursor-pointer
                      motion-safe:transition-colors"
                  >
                    <FileText size={14} />
                    同意进入报告
                  </button>
                </div>
              )}
              {scoutFieldReviewOpen && !gateOpen && (
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => submitUserReply("可以进入下一阶段了")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium
                      bg-app-accent text-white hover:bg-app-accent-hover cursor-pointer motion-safe:transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    进入下一阶段
                  </button>
                </div>
              )}
              {waitingAgent === "cleaner" && (
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => submitUserReply("确认继续")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium
                      bg-app-accent text-white hover:bg-app-accent-hover cursor-pointer motion-safe:transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    确认
                  </button>
                </div>
              )}
              <div className="flex gap-2 items-end">
                <textarea
                  ref={replyInputRef}
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter" || e.shiftKey) return;
                    // 中文输入法用 Enter 确认候选时勿 preventDefault，否则无法上屏
                    const ne = e.nativeEvent as unknown as { isComposing?: boolean; keyCode?: number };
                    if (e.nativeEvent.isComposing || ne.keyCode === 229) {
                      return;
                    }
                    e.preventDefault();
                    if (canSendReply) submitUserReply(replyText);
                  }}
                  placeholder={
                    waitingAgent === "cleaner" && !cleanerCleaningReviewOpen
                      ? "不同意建议？输入你的想法后 Enter 发送；进入下一阶段请点上方按钮"
                      : scoutFieldReviewOpen
                      ? "字段理解不对时输入说明，Enter 发送；进入下一阶段请点上方按钮"
                      : cleanerCleaningReviewOpen
                        ? "补充说明后 Enter 发送；确认结果请点上方按钮"
                        : analystReviewOpen
                          ? "补充关注点后 Enter 发送；确认结果请点上方按钮"
                          : gateOpen && waitingAgent === "scout"
                            ? "补充说明后 Enter 发送；确认请点上方按钮"
                            : "输入回复后 Enter 发送 · Shift+Enter 换行"
                  }
                  rows={2}
                  className={`flex-1 bg-app-bg-secondary border rounded px-3 py-2
                             text-ui-sm text-app-text placeholder-app-text-muted resize-none
                             focus:outline-none transition-colors
                             ${scoutFieldReviewOpen
                               ? "border-app-accent ring-1 ring-app-accent/30"
                               : cleanerCleaningReviewOpen
                                 ? "border-app-success/50 ring-1 ring-app-success/20"
                                 : analystReviewOpen
                                   ? "border-app-accent/60 ring-1 ring-app-accent/25"
                                   : "border-app-accent/50 focus:border-app-accent"}`}
                />
                <button
                  type="button"
                  onClick={handleReply}
                  disabled={!canSendReply}
                  className={`px-4 py-2 rounded text-ui-sm font-medium transition-colors shrink-0 flex items-center gap-1.5
                    ${canSendReply
                      ? "bg-app-accent hover:bg-app-accent-hover text-white cursor-pointer"
                      : "bg-app-bg-secondary border border-app-border text-app-text-muted cursor-not-allowed"}`}
                >
                  <ArrowRight size={14} />
                  发送
                </button>
              </div>
              <div className="mt-1 text-ui-xs text-app-text-muted">
                {scoutFieldReviewOpen
                  ? "用自然语言说明字段理解即可 · Scout 会带入后续 · Enter 发送 · Shift+Enter 换行"
                  : cleanerCleaningReviewOpen
                    ? "补充说明后 Enter 发送 · Shift+Enter 换行"
                    : analystReviewOpen
                      ? "补充关注点后 Enter 发送 · Shift+Enter 换行"
                      : gateOpen && waitingAgent === "scout"
                        ? "补充说明后 Enter 发送 · Shift+Enter 换行"
                    : "Enter 发送 · Shift+Enter 换行"}
              </div>
            </div>
          )}

          {/* Done: report link + reset */}
          {phase === "done" && resultReportUrl && !guardrailsBlocked && (
            <div className="mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-success rounded flex items-center justify-between gap-3 shrink-0">
              <div>
                <div className="text-ui-xs text-app-success font-semibold mb-0.5">分析完成</div>
                <div className="text-ui-sm text-app-text">报告已生成</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <a href={resultReportUrl} target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 bg-app-accent hover:bg-app-accent-hover text-white text-ui-xs rounded cursor-pointer transition-colors whitespace-nowrap flex items-center gap-1">
                  查看报告 <ArrowRight size={12} />
                </a>
                <button onClick={handleReset}
                  className="px-3 py-1.5 border border-app-border text-app-text-muted hover:text-app-text text-ui-xs rounded cursor-pointer transition-colors flex items-center gap-1">
                  <RotateCcw size={12} /> 再次分析
                </button>
              </div>
            </div>
          )}

          {/* Done: guardrails blocked — different UI */}
          {phase === "done" && guardrailsBlocked && (
            <div className="mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-warning rounded flex items-center justify-between gap-3 shrink-0">
              <div>
                <div className="text-ui-xs text-app-warning font-semibold mb-0.5 flex items-center gap-1">
                  <ShieldAlert size={12} />
                  报告未生成
                </div>
                <div className="text-ui-sm text-app-text">统计护栏未通过，请查看说明</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {blockedRunId && currentProject && (
                  <a
                    href={`/api/reports/${currentProject}/${blockedRunId}/GUARDRAILS_BLOCKED.md`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 bg-app-warning hover:bg-app-warning-hover text-white text-ui-xs rounded cursor-pointer transition-colors whitespace-nowrap flex items-center gap-1"
                  >
                    <ShieldAlert size={12} />
                    查看护栏说明
                  </a>
                )}
                <button onClick={handleReset}
                  className="px-3 py-1.5 border border-app-border text-app-text-muted hover:text-app-text text-ui-xs rounded cursor-pointer transition-colors flex items-center gap-1">
                  <RotateCcw size={12} /> 再次分析
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
