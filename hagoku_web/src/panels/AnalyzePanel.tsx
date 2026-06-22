import { useState, useCallback } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { InputBar } from "../components/InputBar";
import { ThinkingStrip } from "../components/ThinkingStrip";
import {
  Loader2,
  WifiOff,
  ArrowRight,
  RotateCcw,
  CheckCircle2,
  FileText,
  ShieldAlert,
} from "lucide-react";
import { PipelineBar } from "./AnalyzePanel/PipelineBar";
import { ConvoFeed } from "./AnalyzePanel/ConvoFeed";
import { ClearHistoryButton } from "./AnalyzePanel/ClearHistoryButton";
import { ProjectFileSelectors } from "./AnalyzePanel/ProjectFileSelectors";
import { StartPanel } from "./AnalyzePanel/StartPanel";
import { useFileUpload } from "./AnalyzePanel/hooks/useFileUpload";
import { useConversation } from "./AnalyzePanel/hooks/useConversation";
import { useAnalyzeSession } from "./AnalyzePanel/hooks/useAnalyzeSession";
import { useWsEventHandler } from "./AnalyzePanel/hooks/useWsEventHandler";
import { sanitizeText } from "../utils/sanitize";
import { focusLabel, focusPlaceholder } from "../constants/focusAreas";

export default function AnalyzePanel() {
  const { send } = useWebSocket();
  const status = useWorkspaceStore((s) => s.status);
  const connectionStatus = useWorkspaceStore((s) => s.connectionStatus);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const projects = useWorkspaceStore((s) => s.projects);
  const setActiveView = useWorkspaceStore((s) => s.setActiveView);
  const resetRunUiState = useWorkspaceStore((s) => s.resetRunUiState);
  const currentDataPath = useWorkspaceStore((s) => s.currentDataPath);
  const setCurrentDataPath = useWorkspaceStore((s) => s.setCurrentDataPath);

  // Phase state
  const [phase, setPhase] = useState<any>("setup");
  const [queryText, setQueryText] = useState("");

  // CO-15: Thinking text (external from useWsEventHandler)
  const [thinkingText, setThinkingText] = useState<string | null>(null);

  // CO-16: reply pending state
  const [replyPending, setReplyPending] = useState(false);

  // File upload hook
  const [dataPath, _setDataPath] = useState(currentDataPath);
  const setDataPath = (path: string) => {
    _setDataPath(path);
    setCurrentDataPath(path);
  };
  const {
    projectFiles,
    filesLoading,
    showFileDropdown,
    setShowFileDropdown,
    showProjectDropdown,
    setShowProjectDropdown,
    uploading,
    uploadError,
    setUploadError,
    fileExists,
    fileInputRef,
    dropdownRef,
    projectDropdownRef,
    loadFiles,
    handleUpload,
  } = useFileUpload(currentProject, dataPath, setDataPath);
  const selectedFileName = dataPath
    ? dataPath.split("/").pop() ?? dataPath
    : null;
  void loadFiles;

  // Conversation hook
  const { messages, setMessages, addSystemMsg, addUserMsg } =
    useConversation();

  // Analyze session hook
  const sess = useAnalyzeSession(
    send,
    dataPath,
    currentProject,
    queryText,
    setQueryText,
    setPhase,
    resetRunUiState,
    setMessages,
  );

  // WS event handler hook
  useWsEventHandler({
    batch: useBatchEvents(),
    setMessages,
    setAgentStates: sess.setAgentStates,
    setAgentElapsed: sess.setAgentElapsed,
    agentStartTimes: sess.agentStartTimes,
    setWaitingAgent: sess.setWaitingAgent,
    setPhase,
    setActiveFieldReviewId: sess.setActiveFieldReviewId,
    setActiveFieldReviewRevision: sess.setActiveFieldReviewRevision,
    setFieldReviewScrollNonce: sess.setFieldReviewScrollNonce,
    setActiveCleaningReviewId: sess.setActiveCleaningReviewId,
    setActiveCleaningReviewRevision: sess.setActiveCleaningReviewRevision,
    setActiveAnalystReviewId: sess.setActiveAnalystReviewId,
    setActiveAnalystReviewRevision: sess.setActiveAnalystReviewRevision,
    setGateOpen: sess.setGateOpen,
    setGuardrailsBlocked: sess.setGuardrailsBlocked,
    setBlockedRunId: sess.setBlockedRunId,
    setResultReportUrl: sess.setResultReportUrl,
    replySnapshotRef: sess.replySnapshotRef,
    replyInputRef: sess.replyInputRef,
    waitinAgent: sess.waitingAgent,
    gateOpen: sess.gateOpen,
    activeFieldReviewId: sess.activeFieldReviewId,
    activeFieldReviewRevision: sess.activeFieldReviewRevision,
    activeCleaningReviewId: sess.activeCleaningReviewId,
    activeCleaningReviewRevision: sess.activeCleaningReviewRevision,
    activeAnalystReviewId: sess.activeAnalystReviewId,
    activeAnalystReviewRevision: sess.activeAnalystReviewRevision,
    currentProject,
    onThinking: setThinkingText,
    setReplyPending,
  });

  useAgentStatusSync();

  // Submit reply handler
  const submitUserReply = useCallback(
    (raw: string) => {
      if (!sess.waitingAgent && !replyPending) return;
      const outgoing = sanitizeText(raw.trim());
      if (!outgoing) return;
      sess.replySnapshotRef.current = {
        agent: sess.waitingAgent || "analyst",
        gate: sess.gateOpen,
      };
      const s = send("respond", { text: outgoing });
      if (!s) {
        sess.replySnapshotRef.current = null;
        addSystemMsg(
          "当前未连接到服务器，回复未发出。请确认右上角连接状态后重试。",
        );
        return;
      }
      addUserMsg(outgoing);
      sess.setReplyText("");
      setQueryText("");
      // CO-16: set replyPending instead of instantly clearing waitingAgent
      setReplyPending(true);
      sess.setGateOpen(false);
    },
    [send, sess.waitingAgent, sess.gateOpen, replyPending],
  );

  const canStart =
    !!currentProject &&
    !!dataPath &&
    fileExists &&
    connectionStatus === "connected";
  const scoutFieldReviewOpen =
    Boolean(sess.activeFieldReviewId) && sess.waitingAgent === "scout";
  const cleanerCleaningReviewOpen =
    Boolean(sess.activeCleaningReviewId) && sess.waitingAgent === "cleaner";
  const analystReviewOpen =
    Boolean(sess.activeAnalystReviewId) && sess.waitingAgent === "analyst";

  // CO-04: context subtitle
  const currentStage =
    sess.waitingAgent || (phase === "running" ? "analyst" : null);
  const contextSubtitle = currentStage
    ? `当前：${focusLabel(currentStage)}`
    : undefined;

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text relative">
      <PanelHeader
        title="分析"
        badge={
          contextSubtitle ? (
            <span className="text-ui-xs text-app-text-muted font-normal tracking-normal normal-case">
              {contextSubtitle}
            </span>
          ) : undefined
        }
      >
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={sess.handleReset}
            className="flex items-center gap-1 px-2 py-0.5 border border-app-border rounded text-ui-xs normal-case tracking-normal font-medium text-app-text
                hover:border-app-accent hover:text-app-accent transition-colors cursor-pointer"
          >
            <RotateCcw size={12} />
            重置分析
          </button>
          <ClearHistoryButton
            currentProject={currentProject}
            onClear={sess.handleReset}
          />
        </div>
      </PanelHeader>

      {/* ── Connection overlay ── */}
      {connectionStatus === "disconnected" && (
        <div className="absolute inset-0 bg-app-bg/90 flex flex-col items-center justify-center gap-2 z-20">
          <WifiOff size={28} className="text-app-text-muted" />
          <span className="text-ui-base text-app-error">连接断开</span>
          <span className="text-ui-xs text-app-text-muted">
            正在重新连接…
          </span>
        </div>
      )}
      {(connectionStatus === "connecting" ||
        connectionStatus === "reconnecting") && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-app-bg/80 backdrop-blur-sm">
          <Loader2 size={20} className="animate-spin text-app-accent" />
          <span className="text-ui-sm text-app-text-muted">
            正在连接服务器…
          </span>
        </div>
      )}

      {/* ── Setup: project + file selectors ── */}
      <ProjectFileSelectors
        currentProject={currentProject}
        projects={projects}
        setCurrentProject={setCurrentProject}
        setActiveView={setActiveView}
        dataPath={dataPath}
        setDataPath={setDataPath}
        selectedFileName={selectedFileName}
        projectFiles={projectFiles}
        filesLoading={filesLoading}
        showFileDropdown={showFileDropdown}
        setShowFileDropdown={setShowFileDropdown}
        showProjectDropdown={showProjectDropdown}
        setShowProjectDropdown={setShowProjectDropdown}
        uploading={uploading}
        uploadError={uploadError}
        setUploadError={setUploadError}
        fileInputRef={fileInputRef}
        dropdownRef={dropdownRef}
        projectDropdownRef={projectDropdownRef}
        handleUpload={handleUpload}
        phase={phase}
      />
      {/* ── Setup idle: start button ── */}
      <StartPanel
        phase={phase}
        currentProject={currentProject}
        dataPath={dataPath}
        canStart={canStart}
        queryText={queryText}
        setQueryText={setQueryText}
        handleStartSession={sess.handleStartSession}
      />

      {/* ── Query / running / done: conversation view ── */}
      {phase !== "setup" && (
        <>
          {/* Pipeline bar */}
          <div className="px-3 py-2 border-b border-app-border shrink-0">
            <PipelineBar
              states={sess.agentStates}
              elapsed={sess.agentElapsed}
            />
          </div>

          {/* CO-15: ThinkingStrip — single latest thought, not in ConvoFeed */}
          <ThinkingStrip text={thinkingText} />

          {/* Running progress bar */}
          {status === "running" && (
            <div className="h-0.5 bg-app-accent animate-pulse shrink-0" />
          )}

          {/* Conversation feed */}
          <ConvoFeed
            messages={messages}
            scrollFieldTableId={sess.activeFieldReviewId}
            scrollFieldTableNonce={sess.fieldReviewScrollNonce}
            onAskReply={submitUserReply}
          />

          {/* CO-16: reply pending processing bar — shown after user sends reply */}
          {replyPending && (
            <div className="flex items-center gap-2 px-3 py-2 border-t border-app-border/40 shrink-0 text-ui-xs text-app-text-muted">
              <Loader2 size={13} className="animate-spin text-app-accent" />
              <span>分析师正在处理你的回复…</span>
            </div>
          )}

          {/* Agent reply input — shown when agent is waiting AND not pending */}
          {sess.waitingAgent && !replyPending && (
            <div className="shrink-0 border-t border-app-border/60 pt-2 motion-safe:transition-colors">
            {/* Quick action buttons */}
            {cleanerCleaningReviewOpen && (
                <div className="flex flex-wrap items-center gap-2 mb-2 px-3">
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
                <div className="flex flex-wrap items-center gap-2 mb-2 px-3">
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
                      submitUserReply(
                        "已核对上表中的 p 值、效应量与置信区间，同意进入报告阶段",
                      )
                    }
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium border
                      border-app-border text-app-text hover:border-app-accent hover:text-app-accent cursor-pointer
                      motion-safe:transition-colors"
                  >
                    <FileText size={14} />
                    同意进入报告
                  </button>
                </div>
              )}
              {scoutFieldReviewOpen && !sess.gateOpen && (
                <div className="flex flex-wrap items-center gap-2 mb-2 px-3">
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
              {sess.waitingAgent === "cleaner" &&
                !cleanerCleaningReviewOpen && (
                  <div className="flex flex-wrap items-center gap-2 mb-2 px-3">
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

              {/* CO-17: InputBar replacing inline textarea */}
              <InputBar
                placeholder={focusPlaceholder(sess.waitingAgent)}
                value={sess.replyText}
                onChange={(v) => sess.setReplyText(v)}
                onSend={submitUserReply}
                inputRef={sess.replyInputRef}
                sendLabel="发送"
                footerHint={
                  scoutFieldReviewOpen
                    ? "用自然语言说明字段理解即可 · Enter 发送 · Shift+Enter 换行"
                    : "Enter 发送 · Shift+Enter 换行"
                }
              />
            </div>

          {/* Done: report link + reset */}
          {phase === "done" &&
            sess.resultReportUrl &&
            !sess.guardrailsBlocked && (
              <div className="mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-success rounded flex items-center justify-between gap-3 shrink-0">
                <div>
                  <div className="text-ui-xs text-app-success font-semibold mb-0.5">
                    分析完成
                  </div>
                  <div className="text-ui-sm text-app-text">报告已生成</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <a
                    href={sess.resultReportUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 bg-app-accent hover:bg-app-accent-hover text-white text-ui-xs rounded cursor-pointer transition-colors whitespace-nowrap flex items-center gap-1"
                  >
                    查看报告 <ArrowRight size={12} />
                  </a>
                  <button
                    onClick={sess.handleReset}
                    className="px-3 py-1.5 border border-app-border text-app-text-muted hover:text-app-text text-ui-xs rounded cursor-pointer transition-colors flex items-center gap-1"
                  >
                    <RotateCcw size={12} /> 再次分析
                  </button>
                </div>
              </div>
            )}

          {/* Done: guardrails blocked */}
          {phase === "done" && sess.guardrailsBlocked && (
            <div className="mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-warning rounded flex items-center justify-between gap-3 shrink-0">
              <div>
                <div className="text-ui-xs text-app-warning font-semibold mb-0.5 flex items-center gap-1">
                  <ShieldAlert size={12} />
                  报告未生成
                </div>
                <div className="text-ui-sm text-app-text">
                  统计护栏未通过，请查看说明
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {sess.blockedRunId && currentProject && (
                  <a
                    href={`/api/reports/${currentProject}/${sess.blockedRunId}/GUARDRAILS_BLOCKED.md`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 bg-app-warning hover:bg-app-warning-hover text-white text-ui-xs rounded cursor-pointer transition-colors whitespace-nowrap flex items-center gap-1"
                  >
                    <ShieldAlert size={12} />
                    查看护栏说明
                  </a>
                )}
                <button
                  onClick={sess.handleReset}
                  className="px-3 py-1.5 border border-app-border text-app-text-muted hover:text-app-text text-ui-xs rounded cursor-pointer transition-colors flex items-center gap-1"
                >
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
