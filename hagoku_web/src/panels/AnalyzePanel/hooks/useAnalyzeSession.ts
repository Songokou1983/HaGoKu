import { useState, useRef, useCallback, useEffect } from "react";
import type { AgentKey, AgentRunState, SessionPhase } from "../types";
import type { ConvoMessage } from "../types";
import { useWorkspaceStore } from "../../../stores/workspace";
import { sanitizeText } from "../../../utils/sanitize";
import { eventLog } from "../../../utils/eventLog";

const SESSION_KEY = "hagoku_session";

export function useAnalyzeSession(
  send: (cmd: string, payload: Record<string, unknown>) => boolean,
  dataPath: string,
  currentProject: string | null,
  queryText: string,
  _setQueryText: (v: string) => void,
  setPhase: (v: SessionPhase) => void,
  resetRunUiState: () => void,
  clearMessages: () => void,
  setReplyPending: (v: boolean) => void,
) {
  const [agentElapsed, setAgentElapsed] = useState<Record<AgentKey, number>>({
    scout: 0, cleaner: 0, analyst: 0, reporter: 0,
  });
  const agentStartTimes = useRef<Record<string, number>>({});
  const [waitingAgent, setWaitingAgent] = useState<AgentKey | null>(null);
  const [replyText, setReplyText] = useState("");
  const [resultReportUrl, setResultReportUrl] = useState<string | null>(null);
  const [guardrailsBlocked, setGuardrailsBlocked] = useState(false);
  const [blockedRunId, setBlockedRunId] = useState<string | null>(null);
  const replyInputRef = useRef<HTMLTextAreaElement>(null);
  const [gateOpen, setGateOpen] = useState(false);
  const replySnapshotRef = useRef<{ agent: AgentKey; gate: boolean } | null>(null);
  const queryRef = useRef("");

  const resetAll = useCallback(() => {
    setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
    setWaitingAgent(null);
    setReplyText("");
    setResultReportUrl(null);
    setGuardrailsBlocked(false);
    setBlockedRunId(null);
    setFieldReviewScrollNonce(0);
    setGateOpen(false);
  }, []);

  const handleStartSession = useCallback((sheetName?: string | number, auxSheets?: string[]) => {
    if (!currentProject || !dataPath) return;
    eventLog("analysis", `start project=${currentProject} data=${dataPath} sheet=${sheetName ?? 0}`);
    resetAll();
    clearMessages();
    setReplyPending(true);
    useWorkspaceStore.getState().resetAgentStates();
    setPhase("running");
    const q = sanitizeText(queryText.trim());
    queryRef.current = q;
    send("analyze", {
      data_path: dataPath,
      query: q || "",
      project_name: currentProject || "",
      phase: "full",
      sheet_name: sheetName || 0,
      aux_sheets: auxSheets ?? [],
    });
  }, [send, dataPath, currentProject, queryText, setPhase, resetAll]);

  const handleReset = useCallback(() => {
    eventLog("analysis", "stop");
    send("cancel_analysis", {});
    resetAll();
    resetRunUiState();
    setPhase("setup");
    clearMessages();
    useWorkspaceStore.getState().resetAgentStates();
  }, [send, resetAll, resetRunUiState, setPhase, clearMessages]);

  return {
    agentElapsed, setAgentElapsed,
    agentStartTimes,
    waitingAgent, setWaitingAgent,
    replyText, setReplyText,
    resultReportUrl, setResultReportUrl,
    guardrailsBlocked, setGuardrailsBlocked,
    blockedRunId, setBlockedRunId,
    replyInputRef,
    gateOpen, setGateOpen,
    replySnapshotRef,
    queryRef,
    handleStartSession,
    handleReset,
    resetAll,
  };
}
