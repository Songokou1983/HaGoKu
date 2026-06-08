import { useEffect } from "react";
import type { AgentKey, AgentRunState } from "../types";
import type { ConvoMessage } from "../types";
import { uid } from "../utils";
import { resolveAgentKey, parsePauseInteractionRevision, parseFieldReview, parseCleaningAssessment, parseCleaningReview, parseAnalystReview } from "../parsers";
import { formatScoutUserInputFactLine, formatStageProceedFactLine } from "../utils";
import { guardrailsRunCompletedInfo } from "../../../utils/wsGuardrails";

interface WsEventDeps {
  batch: any[];
  setMessages: React.Dispatch<React.SetStateAction<ConvoMessage[]>>;
  setAgentStates: React.Dispatch<React.SetStateAction<Record<AgentKey, AgentRunState>>>;
  setAgentElapsed: React.Dispatch<React.SetStateAction<Record<AgentKey, number>>>;
  agentStartTimes: React.MutableRefObject<Record<string, number>>;
  setWaitingAgent: React.Dispatch<React.SetStateAction<AgentKey | null>>;
  setPhase: React.Dispatch<React.SetStateAction<any>>;
  setActiveFieldReviewId: React.Dispatch<React.SetStateAction<string | null>>;
  setActiveFieldReviewRevision: React.Dispatch<React.SetStateAction<number>>;
  setFieldReviewScrollNonce: React.Dispatch<React.SetStateAction<number>>;
  setActiveCleaningReviewId: React.Dispatch<React.SetStateAction<string | null>>;
  setActiveCleaningReviewRevision: React.Dispatch<React.SetStateAction<number>>;
  setActiveAnalystReviewId: React.Dispatch<React.SetStateAction<string | null>>;
  setActiveAnalystReviewRevision: React.Dispatch<React.SetStateAction<number>>;
  setGateOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setGuardrailsBlocked: React.Dispatch<React.SetStateAction<boolean>>;
  setBlockedRunId: React.Dispatch<React.SetStateAction<string | null>>;
  setResultReportUrl: React.Dispatch<React.SetStateAction<string | null>>;
  replySnapshotRef: React.MutableRefObject<{ agent: AgentKey; gate: boolean } | null>;
  replyInputRef: React.MutableRefObject<HTMLTextAreaElement | null>;
  waitinAgent: AgentKey | null;
  gateOpen: boolean;
  activeFieldReviewId: string | null;
  activeFieldReviewRevision: number;
  activeCleaningReviewId: string | null;
  activeCleaningReviewRevision: number;
  activeAnalystReviewId: string | null;
  activeAnalystReviewRevision: number;
  currentProject: string | null;
}

export function useWsEventHandler(deps: WsEventDeps) {
  const {
    batch, setMessages, setAgentStates, setAgentElapsed,
    agentStartTimes, setWaitingAgent, setPhase,
    setActiveFieldReviewId, setActiveFieldReviewRevision,
    setFieldReviewScrollNonce, setActiveCleaningReviewId,
    setActiveCleaningReviewRevision, setActiveAnalystReviewId,
    setActiveAnalystReviewRevision, setGateOpen,
    setGuardrailsBlocked, setBlockedRunId, setResultReportUrl,
    replySnapshotRef, replyInputRef,
    activeFieldReviewId, activeFieldReviewRevision,
    activeCleaningReviewId, activeCleaningReviewRevision,
    activeAnalystReviewId, activeAnalystReviewRevision,
    currentProject,
  } = deps;

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
          { id: uid(), role: "system", text: detail || "服务器返回错误", timestamp: iso },
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

        if (d.event_type === "user_input_requested") {
          setGateOpen(false);
          const dataObj = (d.data ?? {}) as Record<string, unknown>;
          const gatePayload = dataObj.gate as { phase?: string; prompt?: string } | undefined;
          const fr = parseFieldReview(dataObj.field_review);
          const ca = parseCleaningAssessment(dataObj.cleaning_assessment);
          const cr = parseCleaningReview(dataObj.cleaning_review);
          const ar = parseAnalystReview(dataObj.analyst_review);
          const incRev = parsePauseInteractionRevision(dataObj);
          const incomingRevision = incRev !== null ? incRev : Infinity;
          if (fr) {
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
              const wfId = uid();
              setActiveFieldReviewId(wfId);
              setMessages((prev) => [
                ...prev,
                { id: wfId, role: "workflow", text: "", timestamp: d.timestamp, fieldReview: fr },
              ]);
            }
            setActiveFieldReviewRevision(incomingRevision);
            setFieldReviewScrollNonce((n) => n + 1);
          } else if (!gatePayload && !cr && !ar) {
            setActiveFieldReviewId(null);
            setActiveFieldReviewRevision(-1);
            setFieldReviewScrollNonce(0);
          }
          if (cr) {
            const patchCleaning =
              activeCleaningReviewId !== null
              && incRev !== null
              && (incRev === activeCleaningReviewRevision || incRev > activeCleaningReviewRevision);
            if (patchCleaning) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === activeCleaningReviewId ? { ...m, cleaningReview: cr, timestamp: d.timestamp } : m,
                ),
              );
            } else {
              const cid = uid();
              setActiveCleaningReviewId(cid);
              setMessages((prev) => [
                ...prev,
                { id: cid, role: "workflow", text: "", timestamp: d.timestamp, cleaningReview: cr },
              ]);
            }
            if (incRev !== null) setActiveCleaningReviewRevision(incRev);
          } else {
            setActiveCleaningReviewId(null);
            setActiveCleaningReviewRevision(-1);
          }
          if (ca) {
            const cid = uid();
            const colLines = ca.columns.map((c) =>
              `<tr><td style="padding:4px 8px;border:1px solid #2a3040">${c.column}</td><td style="padding:4px 8px;border:1px solid #2a3040;color:#4ade80">${c.action === "clean" ? "清洗" : "不清洗"}</td><td style="padding:4px 8px;border:1px solid #2a3040">${c.reason}</td></tr>`
            ).join("");
            const tableHtml = `<div style="margin-top:8px"><table style="width:100%;border-collapse:collapse;font-size:14px"><thead><tr style="background:#1e2430"><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">字段</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:center;width:80px">建议</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">原因</th></tr></thead><tbody>${colLines}</tbody></table></div>`;
            setMessages((prev) => [
              ...prev,
              { id: cid, role: "agent", text: ca.summary, html: `<p><strong>${ca.summary}</strong></p>${tableHtml}`, timestamp: d.timestamp } as ConvoMessage,
            ]);
          }
          if (ar) {
            const patchAnalyst =
              activeAnalystReviewId !== null
              && incRev !== null
              && (incRev === activeAnalystReviewRevision || incRev > activeAnalystReviewRevision);
            if (patchAnalyst) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === activeAnalystReviewId ? { ...m, analystReview: ar, timestamp: d.timestamp } : m,
                ),
              );
            } else {
              const aid = uid();
              setActiveAnalystReviewId(aid);
              setMessages((prev) => [
                ...prev,
                { id: aid, role: "workflow", text: "", timestamp: d.timestamp, analystReview: ar },
              ]);
            }
            if (incRev !== null) setActiveAnalystReviewRevision(incRev);
          } else {
            setActiveAnalystReviewId(null);
            setActiveAnalystReviewRevision(-1);
          }
          if (gatePayload) {
            setGateOpen(true);
            const prompt = typeof gatePayload.prompt === "string" ? gatePayload.prompt.trim() : "";
            if (prompt) {
              const gateId = uid();
              setMessages((prev) => [
                ...prev,
                { id: gateId, role: "workflow", text: prompt, timestamp: d.timestamp },
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
              { id: uid(), role: "system", text: formatStageProceedFactLine("清洗", inner), timestamp: d.timestamp },
            ]);
          } else if (agentKey === "analyst" && typeof inner.proceed_accepted === "boolean") {
            setMessages((prev) => [
              ...prev,
              { id: uid(), role: "system", text: formatStageProceedFactLine("统计", inner), timestamp: d.timestamp },
            ]);
          }
        }

        if (d.event_type === "run_completed") {
          const runPayload = (d.data ?? {}) as Record<string, unknown>;
          if (runPayload.cancelled === true) {
            setWaitingAgent(null);
            setActiveFieldReviewId(null); setActiveFieldReviewRevision(-1); setFieldReviewScrollNonce(0);
            setActiveCleaningReviewId(null); setActiveCleaningReviewRevision(-1);
            setActiveAnalystReviewId(null); setActiveAnalystReviewRevision(-1);
            setGateOpen(false);
            setPhase("setup");
            setAgentStates({ scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" });
            setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
            setResultReportUrl(null); setGuardrailsBlocked(false); setBlockedRunId(null);
            continue;
          }
          const gr = guardrailsRunCompletedInfo({
            event_type: d.event_type, agent: d.agent,
            data: d.data as Record<string, unknown> | undefined,
          });
          if (gr.guardrailsBlocked) {
            setGuardrailsBlocked(true);
            if (gr.runId) setBlockedRunId(gr.runId);
            setWaitingAgent(null);
            setActiveFieldReviewId(null); setActiveFieldReviewRevision(-1); setFieldReviewScrollNonce(0);
            setActiveCleaningReviewId(null); setActiveCleaningReviewRevision(-1);
            setActiveAnalystReviewId(null); setActiveAnalystReviewRevision(-1);
            setGateOpen(false);
            setPhase("done");
          }
        }
      }
    }
  }, [batch]);
}
