/**
 * WebSocket event handlers — extracted from useWsEventHandler.
 * Each function receives the full WsEventDeps object and a message.
 */
import { uid } from "../utils";
import { eventLog } from "../../../utils/eventLog";
import { useWorkspaceStore } from "../../../stores/workspace";
import {
  resolveAgentKey,
  parsePauseInteractionRevision,
  parseFieldReview,
  parseCleaningAssessment,
  parseCleaningReview,
  parseAnalystReview,
} from "../parsers";
import {
  formatScoutUserInputFactLine,
  formatScoutAppliedUpdates,
  formatStageProceedFactLine,
} from "../utils";
import { guardrailsRunCompletedInfo } from "../../../utils/wsGuardrails";
import { escapeHtml } from "../../../utils/sanitize";
import type { WsEventDeps, ConvoMessage } from "../types";

// ── state_snapshot ────────────────────────────────────────────

export function handleStateSnapshot(deps: WsEventDeps, msg: any): boolean {
  const snap = (msg as any).data;
  eventLog("snapshot", `arrived msgs=${Array.isArray(snap?.messages) ? snap.messages.length : 'N/A'} gate=${snap?.gate_open}`);
  if (!snap) return false;
  const {
    syncFromSnapshot, _setMessages, addSystemMsg: addSys,
    addWorkflowCard, addRawMsg,
    setActiveFieldReviewId, setActiveFieldReviewRevision,
    setActiveCleaningReviewId, setActiveCleaningReviewRevision,
    setActiveAnalystReviewId, setActiveAnalystReviewRevision,
    setGateOpen, setPhase, setWaitingAgent,
    setCurrentProject, setCurrentDataPath, setFieldReviewScrollNonce,
  } = deps;
    setActiveCleaningReviewId, setActiveCleaningReviewRevision,
    setActiveAnalystReviewId, setActiveAnalystReviewRevision,
    setGateOpen, setPhase, setWaitingAgent,
    setCurrentProject, setCurrentDataPath, setFieldReviewScrollNonce,
  } = deps;

  // 项目切换时清空旧消息，断连重连不动已有消息
  if (snap.project_name && deps.currentProject && snap.project_name !== deps.currentProject) {
    deps._setMessages?.([]);
    setActiveFieldReviewId(null);
    setActiveFieldReviewRevision(-1);
    setActiveCleaningReviewId(null);
    setActiveCleaningReviewRevision(-1);
    setActiveAnalystReviewId(null);
    setActiveAnalystReviewRevision(-1);
  }
  if (snap.project_name && setCurrentProject) setCurrentProject(snap.project_name);
  if (snap.data_path && setCurrentDataPath) setCurrentDataPath(snap.data_path);
  if (Array.isArray(snap.messages) && snap.messages.length > 0) {
    // 预解析 review 数据
    const fieldReview = snap.field_review && !deps.activeFieldReviewId && snap.project_name === deps.currentProject
      ? parseFieldReview(snap.field_review) : null;
    const cleaningReview = snap.cleaning_review && !deps.activeCleaningReviewId && snap.project_name === deps.currentProject
      ? parseCleaningReview(snap.cleaning_review) : null;

    deps.syncFromSnapshot(snapMsgs);
    // 追加 review 卡片
    if (fieldReview) {
      setActiveFieldReviewId(uid());
      setActiveFieldReviewRevision(0);
      setFieldReviewScrollNonce((n: number) => n + 1);
      deps.addWorkflowCard({ fieldReview } as any);
      setWaitingAgent("scout"); setGateOpen(true);
    }
    if (cleaningReview) {
      setActiveCleaningReviewId(uid());
      setActiveCleaningReviewRevision(0);
      deps.addWorkflowCard({ cleaningReview } as any);
      setWaitingAgent("cleaner"); setGateOpen(true);
    }
    if (snap.analyst_message) {
      deps.addRawMsg?.({ id: uid(), role: "agent", text: snap.analyst_message, timestamp: new Date().toISOString() } as ConvoMessage);
      setWaitingAgent("analyst"); setGateOpen(true);
    }
  } else if (snap.messages && snap.messages.length === 0) {
    setPhase("setup");
  }
  if (snap.gate_open) setGateOpen(true);
  // askUser 由 live user_input_requested 事件添加，snapshot 不重复
  const agentOrder = ["scout", "cleaner", "analyst", "reporter"];
  const doneIdx = agentOrder.indexOf(snap.stage);
  const states: Record<string, string> = {};
  for (let i = 0; i < 4; i++) {
    const a = agentOrder[i];
    if (i < doneIdx) states[a] = "done";
    else if (i === doneIdx) states[a] = "running";
    else states[a] = "idle";
  }
  for (const [a, s] of Object.entries(states)) {
    useWorkspaceStore.getState().setAgentStatus(a, s as AgentStatus);
  }
  return true;
}

// ── ack ───────────────────────────────────────────────────────

export function handleAck(deps: WsEventDeps, msg: any): boolean {
  const { replySnapshotRef, setReplyPending } = deps;
  if (msg.type === "ack" && msg.cmd === "respond_received") {
    eventLog("ack", "respond_received");
    return true;
  }
  if (msg.type === "ack" && msg.cmd === "respond") {
    replySnapshotRef.current = null;
    setReplyPending?.(false);
    return true;
  }
  if (msg.type === "ack" && msg.cmd === "cancel_respond") {
    setReplyPending?.(false);
    return true;
  }
  return false;
}

// ── error ─────────────────────────────────────────────────────

export function handleError(deps: WsEventDeps, msg: any): boolean {
  const { setMessages, setReplyPending, replySnapshotRef, setWaitingAgent, setGateOpen } = deps;
  if (msg.type !== "error") return false;
  const detail = typeof msg.message === "string" ? msg.message.trim() : "";
  const iso = new Date().toISOString();
  setMessages((prev) => [
    ...prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
    { id: uid(), role: "system", text: detail || "服务器返回错误", timestamp: iso },
  ]);
  setReplyPending?.(false);
  const snap = replySnapshotRef.current;
  const recoverable = /No agent is waiting|No active orchestrator/i.test(detail);
  if (recoverable && snap) {
    setWaitingAgent(snap.agent);
    setGateOpen(snap.gate);
    replySnapshotRef.current = null;
  }
  return true;
}

// ── event (main dispatcher) ───────────────────────────────────

export function handleEvent(deps: WsEventDeps, msg: any): void {
  const d = msg.data;
  const { waitinAgent } = deps;
  let agentKey = resolveAgentKey(d.agent);
  if (d.event_type === "agent_started" && !d.agent) {
    agentKey = resolveAgentKey(waitinAgent ?? "scout") ?? "scout";
  }

  // agent lifecycle
  if (d.event_type === "agent_started" && agentKey) {
    deps.agentStartTimes.current[agentKey] = Date.now();
    useWorkspaceStore.getState().setAgentStatus(agentKey, "running");
    deps.onThinking?.(null);
  }
  if (d.event_type === "agent_completed" && agentKey) {
    const elapsed = Math.round((Date.now() - (deps.agentStartTimes.current[agentKey] ?? Date.now())) / 1000);
    useWorkspaceStore.getState().setAgentStatus(agentKey, "done");
    deps.setAgentElapsed((prev) => ({ ...prev, [agentKey]: elapsed }));
    deps.onThinking?.(null);
  }
  if (d.event_type === "agent_failed" && agentKey) {
    useWorkspaceStore.getState().setAgentStatus(agentKey, "error");
    deps.onThinking?.(null);
    deps.setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)));
    const detail = (d.data as Record<string, unknown>)?.error;
    if (typeof detail === "string" && detail.trim()) {
      deps.setMessages((prev) => [...prev, { id: uid(), role: "system", text: detail.trim(), timestamp: d.timestamp }]);
    }
  }

  // agent_thinking
  if (d.event_type === "agent_thinking") {
    const raw = (d.data as Record<string, unknown> | undefined)?.thought;
    if (typeof raw === "string" && raw.trim()) deps.onThinking?.(raw.trim());
  }

  // tool_exchange
  if (d.event_type === "tool_exchange") {
    const data = (d.data ?? {}) as Record<string, unknown>;
    const toolCalls = data.tool_calls as any[] | undefined;
    if (toolCalls && toolCalls.length > 0) {
      deps.setMessages((prev) => [...prev, {
        id: uid(), role: "agent", text: "", timestamp: d.timestamp,
        toolExchange: {
          stage: (data.stage as string) || d.agent || "",
          tool_calls: toolCalls.map((tc: any) => ({
            id: tc.id || uid(), name: tc.name || "",
            arguments_summary: tc.arguments_summary, result_summary: tc.result_summary,
            error: tc.error, duration_ms: tc.duration_ms,
          })),
          assistant_pre_text: (data.assistant_pre_text as string) || null,
        },
      }]);
    }
  }

  // agent_stream_delta — 用 streamId 搜索，不依赖 lastIdx
  // 用户在 LLM 流式输出中发消息时 addUserMsg 插入末尾，lastIdx 指向用户消息
  // 用 streamId 从后往前搜匹配的流式消息，避免输出被拆成两条
  if (d.event_type === "agent_stream_delta") {
    const data = (d.data ?? {}) as Record<string, unknown>;
    const streamId = (data.stream_id as string) || "";
    const delta = (data.delta as string) || "";
    if (streamId && delta) {
      deps.setReplyPending?.(false);
      deps.setMessages((prev) => {
        for (let i = prev.length - 1; i >= 0; i--) {
          if (prev[i].streaming && prev[i].streamId === streamId) {
            return prev.map((m, idx) => idx === i ? { ...m, text: m.text + delta, timestamp: d.timestamp } : m);
          }
        }
        eventLog("delta", `NEW streamId=${streamId.slice(0,12)} msgs=${prev.length} last=${prev[prev.length-1]?.role}`);
        return [...prev, { id: uid(), role: "agent", text: delta, timestamp: d.timestamp, streaming: true, streamId }];
      });
    }
  }

  // agent_stream_end
  if (d.event_type === "agent_stream_end") {
    eventLog("stream", "end");
    deps.setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)));
  }

  // reporter completed
  if (d.agent === "reporter" && d.event_type === "agent_completed") {
    const data = d.data as Record<string, unknown>;
    const elapsed = Math.round((Date.now() - (deps.agentStartTimes.current["reporter"] ?? Date.now())) / 1000);
    if (data?.skipped === true) {
      useWorkspaceStore.getState().setAgentStatus("reporter", "skipped");
      deps.setAgentElapsed((prev) => ({ ...prev, reporter: elapsed }));
      deps.setWaitingAgent(null);
      deps.setPhase("done");
    } else {
      useWorkspaceStore.getState().setAgentStatus("reporter", "done");
      deps.setAgentElapsed((prev) => ({ ...prev, reporter: elapsed }));
      const proj = (data?.project_name as string) || deps.currentProject || "";
      deps.setResultReportUrl(`/api/reports/${proj}`);
      deps.setWaitingAgent(null);
      deps.setPhase("done");
    }
  }

  // user_input_requested
  if (d.event_type === "user_input_requested") {
    eventLog("gate", `open agent=${d.agent}`);
    deps.setGateOpen(false);
    deps.setReplyPending?.(false);  // ask_user = LLM交棒，清除等待状态
    const dataObj = (d.data ?? {}) as Record<string, unknown>;
    const gatePayload = dataObj.gate as { phase?: string; prompt?: string } | undefined;
    const fr = parseFieldReview(dataObj.field_review);
    const ca = parseCleaningAssessment(dataObj.cleaning_assessment);
    const cr = parseCleaningReview(dataObj.cleaning_review);
    const ar = parseAnalystReview(dataObj.analyst_review);
    const incRev = parsePauseInteractionRevision(dataObj);
    const incomingRevision = incRev !== null ? incRev : Infinity;

    const askQuestion = dataObj.question as string | undefined;
    const askFmt = dataObj.expected_format as string | undefined;
    const isPureAsk = !!askQuestion && !!askFmt && !fr && !cr && !ar && !dataObj.field_review && !dataObj.cleaning_review && !dataObj.analyst_review;

    if (isPureAsk) {
      deps.setMessages((prev) => [...prev, {
        id: uid(), role: "workflow", text: "", timestamp: d.timestamp,
        askUser: { question: askQuestion, expected_format: askFmt, options: dataObj.options as string[] | undefined },
      }]);
    }

    if (fr) {
      const patchInPlace = deps.activeFieldReviewId !== null && (incomingRevision === deps.activeFieldReviewRevision || incomingRevision > deps.activeFieldReviewRevision);
      if (patchInPlace) {
        deps.setMessages((prev) => prev.map((m) => m.id === deps.activeFieldReviewId ? { ...m, fieldReview: fr, timestamp: d.timestamp } : m));
      } else {
        const wfId = uid();
        deps.setActiveFieldReviewId(wfId);
        deps.setMessages((prev) => [...prev, { id: wfId, role: "workflow", text: "", timestamp: d.timestamp, fieldReview: fr }]);
      }
      deps.setActiveFieldReviewRevision(incomingRevision);
      deps.setFieldReviewScrollNonce((n) => n + 1);
    } else if (!fr && dataObj.message) {
      const msgText = String(dataObj.message);
      if (msgText.trim()) {
        deps.setMessages((prev) => {
          if (prev.length > 0 && prev[prev.length - 1].text === msgText) return prev;
          return [...prev, { id: uid(), role: "workflow", text: msgText, timestamp: d.timestamp }];
        });
      }
    } else if (!gatePayload && !cr && !ar && !isPureAsk) {
      deps.setActiveFieldReviewId(null);
      deps.setActiveFieldReviewRevision(-1);
      deps.setFieldReviewScrollNonce(0);
    }

    if (cr) {
      const patchCleaning = deps.activeCleaningReviewId !== null && incRev !== null && (incRev === deps.activeCleaningReviewRevision || incRev > deps.activeCleaningReviewRevision);
      if (patchCleaning) {
        deps.setMessages((prev) => prev.map((m) => m.id === deps.activeCleaningReviewId ? { ...m, cleaningReview: cr, timestamp: d.timestamp } : m));
      } else {
        const cid = uid();
        deps.setActiveCleaningReviewId(cid);
        deps.setMessages((prev) => [...prev, { id: cid, role: "workflow", text: "", timestamp: d.timestamp, cleaningReview: cr }]);
      }
      if (incRev !== null) deps.setActiveCleaningReviewRevision(incRev);
    } else {
      deps.setActiveCleaningReviewId(null);
      deps.setActiveCleaningReviewRevision(-1);
    }

    if (ca) {
      const cid = uid();
      const colLines = ca.columns.map((c: any) => `<tr><td style="padding:4px 8px;border:1px solid #2a3040">${escapeHtml(c.column)}</td><td style="padding:4px 8px;border:1px solid #2a3040;color:#4ade80">${c.action === "clean" ? "清洗" : "不清洗"}</td><td style="padding:4px 8px;border:1px solid #2a3040">${escapeHtml(c.reason)}</td></tr>`).join("");
      const tableHtml = `<div style="margin-top:8px"><table style="width:100%;border-collapse:collapse;font-size:14px"><thead><tr style="background:#1e2430"><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">字段</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:center;width:80px">建议</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">原因</th></tr></thead><tbody>${colLines}</tbody></table></div>`;
      deps.setMessages((prev) => [...prev, { id: cid, role: "agent", text: ca.summary, html: `<p><strong>${escapeHtml(ca.summary)}</strong></p>${tableHtml}`, timestamp: d.timestamp } as ConvoMessage]);
    }

    if (ar) {
      const patchAnalyst = deps.activeAnalystReviewId !== null && incRev !== null && (incRev === deps.activeAnalystReviewRevision || incRev > deps.activeAnalystReviewRevision);
      if (patchAnalyst) {
        deps.setMessages((prev) => prev.map((m) => m.id === deps.activeAnalystReviewId ? { ...m, analystReview: ar, timestamp: d.timestamp } : m));
      } else {
        const aid = uid();
        deps.setActiveAnalystReviewId(aid);
        deps.setMessages((prev) => [...prev, { id: aid, role: "workflow", text: "", timestamp: d.timestamp, analystReview: ar }]);
      }
      if (incRev !== null) deps.setActiveAnalystReviewRevision(incRev);
    } else {
      deps.setActiveAnalystReviewId(null);
      deps.setActiveAnalystReviewRevision(-1);
    }

    if (gatePayload) {
      deps.setGateOpen(true);
      const prompt = typeof gatePayload.prompt === "string" ? gatePayload.prompt.trim() : "";
      if (prompt) {
        deps.setMessages((prev) => [...prev, { id: uid(), role: "workflow", text: prompt, timestamp: d.timestamp }]);
      }
    }

    const raw = dataObj.message;
    const agentMsg = typeof raw === "string" ? raw.trim() : "";
    if (agentMsg) {
      deps.setMessages((prev) => [...prev, { id: uid(), role: "agent", text: agentMsg, timestamp: d.timestamp }]);
    }

    const pausedAgent = resolveAgentKey(d.agent);
    deps.setWaitingAgent(pausedAgent);
    eventLog("gate", `open waitingAgent=${pausedAgent}`);
    deps.setGateOpen(true);
    deps.setPhase("running");
    setTimeout(() => deps.replyInputRef.current?.focus(), 100);
  }

  // user_input_received
  if (d.event_type === "user_input_received") {
    const inner = (d.data ?? {}) as Record<string, unknown>;
    if (agentKey === "scout") {
      const hasNewFields = "parse_applied_count" in inner || "columns_still_needing_input" in inner || "pure_confirm" in inner;
      let line = "";
      if (hasNewFields) {
        line = formatScoutUserInputFactLine(inner);
      } else {
        const applied = inner.applied_field_updates;
        const lines = Array.isArray(applied) ? applied.filter((x): x is string => typeof x === "string" && x !== null && (x as string).trim() !== "") : [];
        if (lines.length > 0) line = formatScoutAppliedUpdates(lines);
      }
      if (line) {
        deps.setMessages((prev) => [...prev, { id: uid(), role: "system", text: line, timestamp: d.timestamp }]);
      }
    } else if (agentKey === "cleaner" && typeof inner.proceed_accepted === "boolean") {
      deps.setMessages((prev) => [...prev, { id: uid(), role: "system", text: formatStageProceedFactLine("清洗", inner), timestamp: d.timestamp }]);
    } else if (agentKey === "analyst" && typeof inner.proceed_accepted === "boolean") {
      deps.setMessages((prev) => [...prev, { id: uid(), role: "system", text: formatStageProceedFactLine("统计", inner), timestamp: d.timestamp }]);
    }
  }

  // run_completed
  if (d.event_type === "run_completed") {
    const runPayload = (d.data ?? {}) as Record<string, unknown>;
    if (runPayload.cancelled === true) {
      deps.setWaitingAgent(null);
      deps.setActiveFieldReviewId(null); deps.setActiveFieldReviewRevision(-1); deps.setFieldReviewScrollNonce(0);
      deps.setActiveCleaningReviewId(null); deps.setActiveCleaningReviewRevision(-1);
      deps.setActiveAnalystReviewId(null); deps.setActiveAnalystReviewRevision(-1);
      deps.setGateOpen(false);
      deps.setPhase("setup");
      useWorkspaceStore.getState().resetAgentStates();
      deps.setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
      deps.setResultReportUrl(null);
      deps.setGuardrailsBlocked(false);
      deps.setBlockedRunId(null);
      deps.setReplyPending?.(false);
      deps.onThinking?.(null);
      return;
    }
    const gr = guardrailsRunCompletedInfo({
      event_type: d.event_type, agent: d.agent,
      data: d.data as Record<string, unknown> | undefined,
    });
    if (gr.guardrailsBlocked) {
      deps.setGuardrailsBlocked(true);
      if (gr.runId) deps.setBlockedRunId(gr.runId);
      deps.setWaitingAgent(null);
      deps.setActiveFieldReviewId(null); deps.setActiveFieldReviewRevision(-1); deps.setFieldReviewScrollNonce(0);
      deps.setActiveCleaningReviewId(null); deps.setActiveCleaningReviewRevision(-1);
      deps.setActiveAnalystReviewId(null); deps.setActiveAnalystReviewRevision(-1);
      deps.setGateOpen(false);
      deps.setPhase("done");
    }
  }
}
