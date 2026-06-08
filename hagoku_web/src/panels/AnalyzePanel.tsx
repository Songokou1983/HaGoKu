import { useState, useCallback } from "react";
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
import { fmtSize } from "./AnalyzePanel/utils";
import { PipelineBar } from "./AnalyzePanel/PipelineBar";
import { ConvoFeed } from "./AnalyzePanel/ConvoFeed";
import { ClearHistoryButton } from "./AnalyzePanel/ClearHistoryButton";
import { useFileUpload } from "./AnalyzePanel/hooks/useFileUpload";
import { useConversation } from "./AnalyzePanel/hooks/useConversation";
import { useAnalyzeSession } from "./AnalyzePanel/hooks/useAnalyzeSession";
import { useWsEventHandler } from "./AnalyzePanel/hooks/useWsEventHandler";

export default function AnalyzePanel() {
  const { send } = useWebSocket();
  const status = useWorkspaceStore((s) => s.status);
  const connectionStatus = useWorkspaceStore((s) => s.connectionStatus);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const projects = useWorkspaceStore((s) => s.projects);
  const setActiveView = useWorkspaceStore((s) => s.setActiveView);
  const resetRunUiState = useWorkspaceStore((s) => s.resetRunUiState);

  // Phase state
  const [phase, setPhase] = useState<any>("setup");
  const [queryText, setQueryText] = useState("");

  // File upload hook
  const [dataPath, setDataPath] = useState("");
  const {
    projectFiles, filesLoading, showFileDropdown, setShowFileDropdown,
    showProjectDropdown, setShowProjectDropdown, uploading, uploadError,
    setUploadError, fileExists, fileInputRef, dropdownRef, projectDropdownRef,
    loadFiles, handleUpload,
  } = useFileUpload(currentProject, dataPath, setDataPath);
  const selectedFileName = dataPath ? dataPath.split("/").pop() ?? dataPath : null;
  void loadFiles;

  // Conversation hook
  const { messages, setMessages, addSystemMsg, addUserMsg } = useConversation();

  // Analyze session hook
  const sess = useAnalyzeSession(
    send, dataPath, currentProject, queryText, setQueryText, setPhase, resetRunUiState,
  );

  // Merge messages from conversation hook into session hook
  // (both hooks need messages; session hook owns the authoritative setMessages)

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
  });

  useAgentStatusSync();

  // Submit reply handler
  const submitUserReply = useCallback(
    (raw: string) => {
      if (!sess.waitingAgent) return;
      const outgoing = raw.trim();
      if (!outgoing) return;
      sess.replySnapshotRef.current = { agent: sess.waitingAgent, gate: sess.gateOpen };
      const s = send("respond", { text: outgoing });
      if (!s) {
        sess.replySnapshotRef.current = null;
        addSystemMsg("当前未连接到服务器，回复未发出。请确认右上角连接状态后重试。");
        return;
      }
      addUserMsg(outgoing);
      sess.setReplyText("");
      setQueryText("");
      sess.setWaitingAgent(null);
      sess.setGateOpen(false);
    },
    [send, sess.waitingAgent, sess.gateOpen],
  );

  const handleReply = useCallback(() => {
    submitUserReply(sess.replyText);
  }, [submitUserReply, sess.replyText]);

  const canStart = !!currentProject && !!dataPath && fileExists && connectionStatus === "connected";
  const scoutFieldReviewOpen = Boolean(sess.activeFieldReviewId) && sess.waitingAgent === "scout";
  const cleanerCleaningReviewOpen = Boolean(sess.activeCleaningReviewId) && sess.waitingAgent === "cleaner";
  const analystReviewOpen = Boolean(sess.activeAnalystReviewId) && sess.waitingAgent === "analyst";
  const canSendReply = !!sess.waitingAgent && sess.replyText.trim().length > 0;


  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text relative">
      <PanelHeader title="分析">
        {(
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
            <ClearHistoryButton currentProject={currentProject} onClear={sess.handleReset} />
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
            onClick={sess.handleStartSession}
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
            <PipelineBar states={sess.agentStates} elapsed={sess.agentElapsed} />
          </div>

          {/* Running progress bar */}
          {status === "running" && (
            <div className="h-0.5 bg-app-accent animate-pulse shrink-0" />
          )}

          {/* Conversation feed */}
          <ConvoFeed
            messages={messages}
            scrollFieldTableId={sess.activeFieldReviewId}
            scrollFieldTableNonce={sess.fieldReviewScrollNonce}
          />

          {/* Agent reply input — shown when any agent is waiting */}
          {sess.waitingAgent && (
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
              {scoutFieldReviewOpen && !sess.gateOpen && (
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
              {sess.waitingAgent === "cleaner" && (
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
                  ref={sess.replyInputRef}
                  value={sess.replyText}
                  onChange={(e) => sess.setReplyText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter" || e.shiftKey) return;
                    // 中文输入法用 Enter 确认候选时勿 preventDefault，否则无法上屏
                    const ne = e.nativeEvent as unknown as { isComposing?: boolean; keyCode?: number };
                    if (e.nativeEvent.isComposing || ne.keyCode === 229) {
                      return;
                    }
                    e.preventDefault();
                    if (canSendReply) submitUserReply(sess.replyText);
                  }}
                  placeholder={
                    sess.waitingAgent === "cleaner" && !cleanerCleaningReviewOpen
                      ? "不同意建议？输入你的想法后 Enter 发送；进入下一阶段请点上方按钮"
                      : scoutFieldReviewOpen
                      ? "字段理解不对时输入说明，Enter 发送；进入下一阶段请点上方按钮"
                      : cleanerCleaningReviewOpen
                        ? "补充说明后 Enter 发送；确认结果请点上方按钮"
                        : analystReviewOpen
                          ? "补充关注点后 Enter 发送；确认结果请点上方按钮"
                          : sess.gateOpen && sess.waitingAgent === "scout"
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
                      : sess.gateOpen && sess.waitingAgent === "scout"
                        ? "补充说明后 Enter 发送 · Shift+Enter 换行"
                    : "Enter 发送 · Shift+Enter 换行"}
              </div>
            </div>
          )}

          {/* Done: report link + reset */}
          {phase === "done" && sess.resultReportUrl && !sess.guardrailsBlocked && (
            <div className="mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-success rounded flex items-center justify-between gap-3 shrink-0">
              <div>
                <div className="text-ui-xs text-app-success font-semibold mb-0.5">分析完成</div>
                <div className="text-ui-sm text-app-text">报告已生成</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <a href={sess.resultReportUrl} target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 bg-app-accent hover:bg-app-accent-hover text-white text-ui-xs rounded cursor-pointer transition-colors whitespace-nowrap flex items-center gap-1">
                  查看报告 <ArrowRight size={12} />
                </a>
                <button onClick={sess.handleReset}
                  className="px-3 py-1.5 border border-app-border text-app-text-muted hover:text-app-text text-ui-xs rounded cursor-pointer transition-colors flex items-center gap-1">
                  <RotateCcw size={12} /> 再次分析
                </button>
              </div>
            </div>
          )}

          {/* Done: guardrails blocked — different UI */}
          {phase === "done" && sess.guardrailsBlocked && (
            <div className="mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-warning rounded flex items-center justify-between gap-3 shrink-0">
              <div>
                <div className="text-ui-xs text-app-warning font-semibold mb-0.5 flex items-center gap-1">
                  <ShieldAlert size={12} />
                  报告未生成
                </div>
                <div className="text-ui-sm text-app-text">统计护栏未通过，请查看说明</div>
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
                <button onClick={sess.handleReset}
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
