import { useState, useCallback, useEffect, useRef } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { eventLog } from "../utils/eventLog";
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
  ShieldAlert,
} from "lucide-react";
import { ConvoFeed } from "./AnalyzePanel/ConvoFeed";
import { ClearHistoryButton } from "./AnalyzePanel/ClearHistoryButton";
import { ProjectFileSelectors } from "./AnalyzePanel/ProjectFileSelectors";
import { StartPanel } from "./AnalyzePanel/StartPanel";
import { useFileUpload } from "./AnalyzePanel/hooks/useFileUpload";
import { useConversation } from "./AnalyzePanel/hooks/useConversation";
import { useAnalyzeSession } from "./AnalyzePanel/hooks/useAnalyzeSession";
import { useWsEventHandler } from "./AnalyzePanel/hooks/useWsEventHandler";
import { sanitizeText } from "../utils/sanitize";
import { uid } from "./AnalyzePanel/utils";

export default function AnalyzePanel() {
  const { send, log } = useWebSocket();
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

  // 当前激活的提示词预设
  const [presetName, setPresetName] = useState("");

  // ── 项目切换：监听 snapshot 恢复状态 ──
  // ── 挂载时拉快照 ──
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
  const reloadFiles = useCallback(() => loadFiles(currentProject!), [loadFiles, currentProject]);

  // ── Excel 多 sheet 选择 ──
  const [excelSheets, setExcelSheets] = useState<string[]>([]);
  const [sheetName, setSheetName] = useState<string>("");
  const [auxSheets, setAuxSheets] = useState<string[]>([]);
  useEffect(() => {
    setExcelSheets([]);
    setSheetName("");
    if (!dataPath || !dataPath.match(/\.(xlsx|xls)$/i)) return;
    const fn = dataPath.split("/").pop() || dataPath;
    fetch(`/api/projects/${currentProject}/sheets?file=${encodeURIComponent(fn)}`)
      .then(r => r.json())
      .then(d => {
        if (d.sheets && d.sheets.length > 1) {
          setExcelSheets(d.sheets);
          setSheetName(d.sheets[0]);
        }
      })
      .catch((e) => { eventLog("fetch_error", `preview sheets: ${e}`); });
  }, [dataPath, currentProject]);

  const startAnalysis = () => {
    sess.handleStartSession(sheetName, auxSheets);
  };

  // Conversation hook
  const { messages, addSystemMsg, addUserMsg, addAgentMsg, addWorkflowCard, updateWorkflowCard, syncFromSnapshot, clearMessages, addRawMsg, _setMessages } =
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
    clearMessages,
    setReplyPending,
  );

  // ── 项目切换：重置 UI 状态（不含 messages — 铁律 13：消息唯一写入点 = handleStateSnapshot）──
  const prevProjectRef = useRef<string | null>(null);
  useEffect(() => {
    const prev = prevProjectRef.current;
    prevProjectRef.current = currentProject;
    // 跳过：首次挂载、同项目不变、清空项目
    if (prev === currentProject) return;
    if (prev === null && currentProject) return;
    if (!currentProject) return;
    // 真正切换
    setPhase("setup");
    setQueryText("");
    setThinkingText(null);
    setReplyPending(false);
    _setDataPath("");
    setExcelSheets([]);
    setSheetName("");
    setAuxSheets([]);
    setPresetName("");
    sess.resetAll();
    setCurrentDataPath("");
    useWorkspaceStore.getState().resetRunUiState();
    useWorkspaceStore.getState().setLastError(null);
    useWorkspaceStore.getState().setReportFiles([]);
    useWorkspaceStore.getState().setSnapshot(null);
  }, [currentProject]);

  // WS event handler hook
  useWsEventHandler({
    batch: useBatchEvents(),
    addWorkflowCard,
    updateWorkflowCard,
    syncFromSnapshot,
    addSystemMsg,
    addAgentMsg,
    addRawMsg,
    _setMessages,
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
    setCurrentProject,
    setCurrentDataPath,
    log,
  });

  // Submit reply handler — 不拦截，后端 respond 锁保证排队
  const submitUserReply = useCallback(
    (raw: string) => {
      const outgoing = sanitizeText(raw.trim());
      if (!outgoing) return;
      sess.replySnapshotRef.current = {
        agent: "analyst",
        gate: sess.gateOpen,
      };
      // 先保存到后端 session（HTTP POST，不依赖 WS）
      eventLog("submit", `gateOpen=${sess.gateOpen} replyPending=${replyPending} text=${outgoing.slice(0, 40)}`);
      fetch("/api/save_user_msg", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ text: outgoing }),
      }).catch((e) => { eventLog("fetch_error", `save_user_msg: ${e}`); });
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
      setReplyPending(true);
      sess.setGateOpen(false);
    },
    [send, log, sess.gateOpen],
  );

  const canStart =
    !!currentProject &&
    !!dataPath &&
    fileExists &&
    connectionStatus === "connected";
  const scoutFieldReviewOpen =
    Boolean(sess.activeFieldReviewId);
  const cleanerCleaningReviewOpen =
    Boolean(sess.activeCleaningReviewId);
  const analystReviewOpen =
    Boolean(sess.activeAnalystReviewId);


  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text relative">
      <PanelHeader
        title="分析"
      >
        {presetName && (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-ui-xs bg-app-accent/10 text-app-accent font-medium mr-2">
            {presetName}
          </span>
        )}
        <div className="flex items-center gap-2">
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
        dataPath={dataPath}
        setDataPath={setDataPath}
        selectedFileName={selectedFileName}
        projectFiles={projectFiles}
        filesLoading={filesLoading}
        showFileDropdown={showFileDropdown}
        setShowFileDropdown={setShowFileDropdown}
        uploading={uploading}
        uploadError={uploadError}
        setUploadError={setUploadError}
        fileInputRef={fileInputRef}
        dropdownRef={dropdownRef}
        handleUpload={handleUpload}
        phase={phase}
        excelSheets={excelSheets}
        sheetName={sheetName}
        setSheetName={setSheetName}
        auxSheets={auxSheets}
        setAuxSheets={setAuxSheets}
        onDeleteFile={() => reloadFiles()}
      />
      {/* ── Setup idle: start button ── */}
      <StartPanel
        phase={phase}
        currentProject={currentProject}
        dataPath={dataPath}
        canStart={canStart}
        queryText={queryText}
        setQueryText={setQueryText}
        handleStartSession={startAnalysis}
      />

      {/* ── Query / running / done: conversation view ── */}
      {phase !== "setup" && (
        <>
          {/* CO-15: ThinkingStrip — single latest thought, not in ConvoFeed */}
          <ThinkingStrip text={thinkingText} />

          {/* Running progress bar */}
          {status === "running" && (
            <div className="h-0.5 bg-app-accent animate-pulse shrink-0" />
          )}

          {/* Conversation feed + input — absolute 定位，输入框永远在底部 */}
          <div className="flex-1 min-h-0 relative">
            <div className="absolute inset-0 pb-[100px]">
              <ConvoFeed
                messages={messages}
                scrollFieldTableId={sess.activeFieldReviewId}
                scrollFieldTableNonce={sess.fieldReviewScrollNonce}
                onAskReply={submitUserReply}
              />
            </div>
            <div className="absolute bottom-0 left-0 right-0 bg-app-bg border-t border-app-border/60 pt-2">
              {/* CO-16: reply pending */}
              {replyPending && (
                <div className="flex items-center gap-2 px-3 py-2 border-t border-app-border/40 text-ui-xs text-app-text-muted">

                  <Loader2 size={13} className="animate-spin text-app-accent" /><span>分析师正在处理你的回复…</span>
                  <button type="button" onClick={() => { send("cancel_respond", {}); setReplyPending(false); }}
                    className="ml-auto px-2 py-0.5 border border-app-border rounded text-ui-xs hover:border-app-error hover:text-app-error cursor-pointer transition-colors">停止</button>
                </div>
              )}
              {/* 用户通过输入框自由回复，不预设固定文本 */}
              <InputBar
                placeholder="输入回复后 Enter 发送"
                value={sess.replyText}
                onChange={(v) => sess.setReplyText(v)}
                onSend={submitUserReply}
                inputRef={sess.replyInputRef}
                sendLabel="发送"
                log={log}
                footerHint={scoutFieldReviewOpen ? "用自然语言说明字段理解即可 · Enter 发送 · Shift+Enter 换行" : "Enter 发送 · Shift+Enter 换行"}
              />
            </div>
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
