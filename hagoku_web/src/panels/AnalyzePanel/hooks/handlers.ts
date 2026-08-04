/**
 * WebSocket event handlers — extracted from useWsEventHandler.
 * Each function receives the full WsEventDeps object and a message.
 *
 * §2 改造：不构造任何消息对象。消息由后端 state_snapshot 统一推送。
 */
import { uid } from "../utils";
import { eventLog } from "../../../utils/eventLog";
import { useWorkspaceStore } from "../../../stores/workspace";
import type { WsEventDeps, ConvoMessage, AgentStatus } from "../types";
import { resolveAgentKey } from "../parsers";
import { guardrailsRunCompletedInfo } from "../../../utils/wsGuardrails";

// ── state_snapshot ────────────────────────────────────────────

export function handleStateSnapshot(deps: WsEventDeps, msg: any): boolean {
  const snap = (msg as any).data;
  eventLog("snapshot", `arrived msgs=${Array.isArray(snap?.messages) ? snap.messages.length : 'N/A'} gate=${snap?.gate_open}`);
  if (!snap) return false;
  const {
    setMessages, setGateOpen, setPhase, setWaitingAgent,
    setCurrentProject, setCurrentDataPath,
  } = deps;

  const roleMap: Record<string, ConvoMessage["role"]> = {
    user: "user", assistant: "agent", agent: "agent",
  };

  if (snap.project_name && setCurrentProject) setCurrentProject(snap.project_name);
  if (snap.data_path && setCurrentDataPath) setCurrentDataPath(snap.data_path);
  if (Array.isArray(snap.messages)) {
    if (snap.messages.length > 0) {
      const ms: ConvoMessage[] = snap.messages.map((m: any) => ({
        id: uid(),
        role: roleMap[m.role] || "system",
        text: m.content || "",
        timestamp: m.timestamp || "",
        collapsible: m.collapsible || false,
      }));
      setMessages(ms);
      setPhase?.("running");
    } else {
      setMessages([]);
      setPhase?.("setup");
    }
  }
  if (snap.gate_open) setGateOpen(true);

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
  // 项目被删除：空 project_name + 空 messages → 清空分析面板
  if (!snap.project_name && snap.messages && snap.messages.length === 0) {
    setMessages([]);
    setPhase?.("setup");
    deps.setCurrentProject?.(null);
    useWorkspaceStore.getState().setCurrentProject(null);
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
  const { setReplyPending, replySnapshotRef, setWaitingAgent, setGateOpen } = deps;
  if (msg.type !== "error") return false;
  setReplyPending?.(false);
  const snap = replySnapshotRef.current;
  const recoverable = /No agent is waiting|No active orchestrator/i.test(typeof msg.message === "string" ? msg.message : "");
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
    deps.endStream();
  }

  // agent_thinking
  if (d.event_type === "agent_thinking") {
    const raw = (d.data as Record<string, unknown> | undefined)?.thought;
    if (typeof raw === "string" && raw.trim()) deps.onThinking?.(raw.trim());
  }

  // tool_exchange — no-op，工具结果不进快照
  if (d.event_type === "tool_exchange") {
    // no-op: snapshot 在每次 session 更新后推送
  }

  // agent_stream_delta — 流式追加
  if (d.event_type === "agent_stream_delta") {
    const data = (d.data ?? {}) as Record<string, unknown>;
    const streamId = (data.stream_id as string) || "";
    const delta = (data.delta as string) || "";
    if (streamId && delta) {
      deps.setReplyPending?.(false);
      deps.appendDelta(streamId, delta);
    }
  }

  // agent_stream_end
  if (d.event_type === "agent_stream_end") {
    eventLog("stream", "end");
    deps.endStream();
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

  // user_input_requested — 只做状态，消息由快照顾推
  if (d.event_type === "user_input_requested") {
    eventLog("gate", `open agent=${d.agent}`);
    deps.setReplyPending?.(false);
    const pausedAgent = resolveAgentKey(d.agent);
    deps.setWaitingAgent(pausedAgent);
    deps.setGateOpen(true);
    deps.setPhase("running");
    setTimeout(() => deps.replyInputRef.current?.focus(), 100);
  }

  // user_input_received — system 消息已由后端写入 Session，通过 snapshot 到达
  if (d.event_type === "user_input_received") {
    // 不做消息构造，后端通过 snapshot 推送
  }

  // run_completed
  if (d.event_type === "run_completed") {
    const runPayload = (d.data ?? {}) as Record<string, unknown>;
    if (runPayload.cancelled === true) {
      deps.setWaitingAgent(null);
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
      deps.setGateOpen(false);
      deps.setPhase("done");
    }
  }
}
