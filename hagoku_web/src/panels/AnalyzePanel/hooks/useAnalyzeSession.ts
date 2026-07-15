import { useState, useRef, useCallback, useEffect } from "react";
import type { AgentKey, AgentRunState, SessionPhase } from "../types";
import type { ConvoMessage } from "../types";
import { sanitizeText } from "../../../utils/sanitize";

const SESSION_KEY = "hagoku_session";

export function useAnalyzeSession(
  send: (cmd: string, payload: Record<string, unknown>) => boolean,
  dataPath: string,
  currentProject: string | null,
  queryText: string,
  _setQueryText: (v: string) => void,
  setPhase: (v: SessionPhase) => void,
  resetRunUiState: () => void,
  setMessages: (v: any[] | ((prev: any[]) => any[])) => void,
  setReplyPending: (v: boolean) => void,
) {
  const [agentStates, setAgentStates] = useState<Record<AgentKey, AgentRunState>>({
    scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle",
  });
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
  const [activeFieldReviewId, setActiveFieldReviewId] = useState<string | null>(null);
  const [activeFieldReviewRevision, setActiveFieldReviewRevision] = useState<number>(-1);
  const [activeCleaningReviewId, setActiveCleaningReviewId] = useState<string | null>(null);
  const [activeCleaningReviewRevision, setActiveCleaningReviewRevision] = useState<number>(-1);
  const [activeAnalystReviewId, setActiveAnalystReviewId] = useState<string | null>(null);
  const [activeAnalystReviewRevision, setActiveAnalystReviewRevision] = useState<number>(-1);
  const [gateOpen, setGateOpen] = useState(false);
  const [fieldReviewScrollNonce, setFieldReviewScrollNonce] = useState(0);
  const replySnapshotRef = useRef<{ agent: AgentKey; gate: boolean } | null>(null);
  const queryRef = useRef("");

  const handleStartSession = useCallback((sheetName?: string | number) => {
    if (!currentProject || !dataPath) return;
    setMessages([]);
    setReplyPending(false);
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
    const q = sanitizeText(queryText.trim());
    queryRef.current = q;
    send("analyze", {
      data_path: dataPath,
      query: q || "",
      project_name: currentProject || "",
      phase: "full",
      sheet_name: sheetName ?? 0,
    });
  }, [send, dataPath, currentProject, queryText, setPhase]);

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
  }, [send, resetRunUiState, setPhase]);

  return {
    agentStates, setAgentStates,
    agentElapsed, setAgentElapsed,
    agentStartTimes,
    waitingAgent, setWaitingAgent,
    replyText, setReplyText,
    resultReportUrl, setResultReportUrl,
    guardrailsBlocked, setGuardrailsBlocked,
    blockedRunId, setBlockedRunId,
    replyInputRef,
    activeFieldReviewId, setActiveFieldReviewId,
    activeFieldReviewRevision, setActiveFieldReviewRevision,
    activeCleaningReviewId, setActiveCleaningReviewId,
    activeCleaningReviewRevision, setActiveCleaningReviewRevision,
    activeAnalystReviewId, setActiveAnalystReviewId,
    activeAnalystReviewRevision, setActiveAnalystReviewRevision,
    gateOpen, setGateOpen,
    fieldReviewScrollNonce, setFieldReviewScrollNonce,
    replySnapshotRef,
    queryRef,
    handleStartSession,
    handleReset,
  };
}
