import { useEffect } from "react";
import type { AgentKey, AgentRunState } from "../types";
import type { ConvoMessage } from "../types";
import { uid } from "../utils";
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

interface WsEventDeps {
  batch: any[];
  setMessages: React.Dispatch<React.SetStateAction<ConvoMessage[]>>;
  setAgentStates: React.Dispatch<
    React.SetStateAction<Record<AgentKey, AgentRunState>>
  >;
  setAgentElapsed: React.Dispatch<
    React.SetStateAction<Record<AgentKey, number>>
  >;
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
  replySnapshotRef: React.MutableRefObject<{
    agent: AgentKey;
    gate: boolean;
  } | null>;
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
  /** CO-15: thinking text callback — agent_thinking goes here, not ConvoFeed */
  onThinking?: (text: string | null) => void;
  /** CO-16: reply pending state setter */
  setReplyPending?: React.Dispatch<React.SetStateAction<boolean>>;
  setCurrentProject?: (p: string) => void;
  setCurrentDataPath?: (p: string) => void;
}

export function useWsEventHandler(deps: WsEventDeps) {
  const {
    batch,
    setMessages,
    setAgentStates,
    setAgentElapsed,
    agentStartTimes,
    setWaitingAgent,
    setPhase,
    setActiveFieldReviewId,
    setActiveFieldReviewRevision,
    setFieldReviewScrollNonce,
    setActiveCleaningReviewId,
    setActiveCleaningReviewRevision,
    setActiveAnalystReviewId,
    setActiveAnalystReviewRevision,
    setGateOpen,
    setGuardrailsBlocked,
    setBlockedRunId,
    setResultReportUrl,
    replySnapshotRef,
    replyInputRef,
    activeFieldReviewId,
    activeFieldReviewRevision,
    activeCleaningReviewId,
    activeCleaningReviewRevision,
    activeAnalystReviewId,
    activeAnalystReviewRevision,
    currentProject,
    onThinking,
    setReplyPending,
    setCurrentProject,
    setCurrentDataPath,
    waitinAgent,
  } = deps;

  useEffect(() => {
    if (batch.length === 0) return;
    for (const msg of batch) {
      // ── state_snapshot ──────────────────────────────────────────
      if (msg.type === "state_snapshot") {
        const snap = (msg as any).data;
        if (!snap) continue;
        // 项目切换：始终清空旧内容，再恢复快照
        setMessages([]);
        setActiveFieldReviewId(null);
        setActiveFieldReviewRevision(-1);
        setActiveCleaningReviewId(null);
        setActiveCleaningReviewRevision(-1);
        setActiveAnalystReviewId(null);
        setActiveAnalystReviewRevision(-1);
        if (snap.project_name && setCurrentProject) {
          setCurrentProject(snap.project_name);
        }
        if (snap.data_path && setCurrentDataPath) {
          setCurrentDataPath(snap.data_path);
        }
        // 有消息 → 恢复对话；无消息 → 显示启动页
        if (Array.isArray(snap.messages) && snap.messages.length > 0) {
          setPhase("running");
          const replayed: ConvoMessage[] = snap.messages.map((m: any) => ({
            id: uid(),
            role: m.role === "user" ? "user" : m.role === "assistant" ? "agent" : "system",
            text: m.content || "",
            timestamp: m.timestamp || new Date().toISOString(),
          }));
          setMessages(replayed);
        } else {
          setPhase("setup");
        }
        if (snap.gate_open) setGateOpen(true);
        // 恢复 Scout 字段核对表
        if (snap.field_review) {
          const fr = parseFieldReview(snap.field_review);
          if (fr) {
            const wfId = uid();
            setActiveFieldReviewId(wfId);
            setMessages((prev) => [
              ...prev,
              {
                id: wfId,
                role: "workflow",
                text: "",
                timestamp: new Date().toISOString(),
                fieldReview: fr,
              },
            ]);
            setActiveFieldReviewRevision(0);
            setFieldReviewScrollNonce((n: number) => n + 1);
          }
          setWaitingAgent("scout");
          setGateOpen(true);
        }
        // 恢复 Cleaner 评估
        if (snap.cleaning_review) {
          const cr = parseCleaningReview(snap.cleaning_review);
          if (cr) {
            const cid = uid();
            setActiveCleaningReviewId(cid);
            setMessages((prev) => [
              ...prev,
              {
                id: cid,
                role: "workflow",
                text: "",
                timestamp: new Date().toISOString(),
                cleaningReview: cr,
              },
            ]);
            setActiveCleaningReviewRevision(0);
          }
          setWaitingAgent("cleaner");
          setGateOpen(true);
        }
        // 恢复 Analyst 消息
        if (snap.analyst_message) {
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "agent",
              text: snap.analyst_message,
              timestamp: new Date().toISOString(),
            },
          ]);
          setWaitingAgent("analyst");
          setGateOpen(true);
        }
        // CO-14: 恢复 pending ask_user
        if (snap.pending_ask_user) {
          const ask = snap.pending_ask_user;
          if (ask.question && ask.expected_format) {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "workflow",
                text: "",
                timestamp: new Date().toISOString(),
                askUser: {
                  question: ask.question,
                  expected_format: ask.expected_format,
                  options: ask.options,
                },
              },
            ]);
          }
        }
        // ── 回放对话历史（app 重启后恢复）
        // (已在 state_snapshot 块开头处理，此处不再重复)
        // Agent 状态恢复
        const agentOrder = ["scout", "cleaner", "analyst", "reporter"];
        const doneIdx = agentOrder.indexOf(snap.stage);
        const states: Record<string, string> = {};
        for (let i = 0; i < 4; i++) {
          const a = agentOrder[i];
          if (i < doneIdx) states[a] = "done";
          else if (i === doneIdx) states[a] = "running";
          else states[a] = "idle";
        }
        setAgentStates(states as any);
        continue;
      }

      // ── ack ─────────────────────────────────────────────────────
      if (msg.type === "ack" && msg.cmd === "respond") {
        replySnapshotRef.current = null;
        // CO-16: 清除 replyPending
        setReplyPending?.(false);
        continue;
      }
      if (msg.type === "ack" && msg.cmd === "cancel_respond") {
        setReplyPending?.(false);
        continue;
      }

      // ── error ───────────────────────────────────────────────────
      if (msg.type === "error") {
        const detail =
          typeof msg.message === "string" ? msg.message.trim() : "";
        const iso = new Date().toISOString();
        // CO-21: 清除残留的流式光标
        setMessages((prev) => [
          ...prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
          {
            id: uid(),
            role: "system",
            text: detail || "服务器返回错误",
            timestamp: iso,
          },
        ]);
        setReplyPending?.(false);
        const snap = replySnapshotRef.current;
        const recoverable = /No agent is waiting|No active orchestrator/i.test(
          detail,
        );
        if (recoverable && snap) {
          setWaitingAgent(snap.agent);
          setGateOpen(snap.gate);
          replySnapshotRef.current = null;
        }
        continue;
      }

      if (msg.type === "event" && msg.data) {
        const d = msg.data;
        // CO-05: Pipeline 兜底 — agent_started 无 agent 时回退
        let agentKey: AgentKey | null = resolveAgentKey(d.agent);
        if (d.event_type === "agent_started" && !d.agent) {
          agentKey = resolveAgentKey(waitinAgent ?? "scout") ?? "scout";
        }

        // ── agent lifecycle ──────────────────────────────────────
        if (d.event_type === "agent_started" && agentKey) {
          agentStartTimes.current[agentKey] = Date.now();
          setAgentStates((prev) => ({ ...prev, [agentKey]: "running" }));
          // clear thinking on new agent start
          onThinking?.(null);
        }
        if (d.event_type === "agent_completed" && agentKey) {
          const elapsed = Math.round(
            (Date.now() - (agentStartTimes.current[agentKey] ?? Date.now())) /
              1000,
          );
          setAgentStates((prev) => ({ ...prev, [agentKey]: "done" }));
          setAgentElapsed((prev) => ({ ...prev, [agentKey]: elapsed }));
          onThinking?.(null);
        }
        if (d.event_type === "agent_failed" && agentKey) {
          setAgentStates((prev) => ({ ...prev, [agentKey]: "error" }));
          onThinking?.(null);
          // CO-21: 清除残留的流式光标
          setMessages((prev) =>
            prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
          );
          const detail = (d.data as Record<string, unknown>)?.error;
          if (typeof detail === "string" && detail.trim()) {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "system",
                text: detail.trim(),
                timestamp: d.timestamp,
              },
            ]);
          }
        }

        // ── CO-15: agent_thinking → ThinkingStrip, NOT ConvoFeed ──
        if (d.event_type === "agent_thinking") {
          const raw = (d.data as Record<string, unknown> | undefined)?.thought;
          if (typeof raw === "string" && raw.trim()) {
            onThinking?.(raw.trim());
          }
        }

        // ── CO-13: tool_exchange → ConvoFeed tool block ───────────
        if (d.event_type === "tool_exchange") {
          const data = (d.data ?? {}) as Record<string, unknown>;
          const toolCalls = data.tool_calls as any[] | undefined;
          if (toolCalls && toolCalls.length > 0) {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "agent",
                text: "",
                timestamp: d.timestamp,
                toolExchange: {
                  stage: (data.stage as string) || d.agent || "",
                  tool_calls: toolCalls.map((tc: any) => ({
                    id: tc.id || uid(),
                    name: tc.name || "",
                    arguments_summary: tc.arguments_summary,
                    result_summary: tc.result_summary,
                    error: tc.error,
                    duration_ms: tc.duration_ms,
                  })),
                  assistant_pre_text:
                    (data.assistant_pre_text as string) || null,
                },
              },
            ]);
          }
        }

        // ── CO-19: agent_stream_delta → 增量渲染 ──────────────────
        if (d.event_type === "agent_stream_delta") {
          const data = (d.data ?? {}) as Record<string, unknown>;
          const streamId = (data.stream_id as string) || "";
          const delta = (data.delta as string) || "";
          if (streamId && delta) {
            setMessages((prev) => {
              // Find last streaming message with matching streamId
              const lastIdx = prev.length - 1;
              if (
                lastIdx >= 0 &&
                prev[lastIdx].streaming &&
                prev[lastIdx].streamId === streamId
              ) {
                // Append delta to existing streaming message
                return prev.map((m, i) =>
                  i === lastIdx
                    ? { ...m, text: m.text + delta, timestamp: d.timestamp }
                    : m,
                );
              }
              // Create new streaming message
              return [
                ...prev,
                {
                  id: uid(),
                  role: "agent",
                  text: delta,
                  timestamp: d.timestamp,
                  streaming: true,
                  streamId,
                },
              ];
            });
          }
        }

        // ── CO-19: agent_stream_end → 结束流式 ────────────────────
        if (d.event_type === "agent_stream_end") {
          const data = (d.data ?? {}) as Record<string, unknown>;
          const streamId = (data.stream_id as string) || "";
          if (streamId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.streaming && m.streamId === streamId
                  ? { ...m, streaming: false, streamId: undefined }
                  : m,
              ),
            );
          }
        }

        // ── reporter completed ────────────────────────────────────
        if (d.agent === "reporter" && d.event_type === "agent_completed") {
          const data = d.data as Record<string, unknown>;
          const elapsed = Math.round(
            (Date.now() -
              (agentStartTimes.current["reporter"] ?? Date.now())) /
              1000,
          );
          if (data?.skipped === true) {
            setAgentStates((prev) => ({ ...prev, reporter: "skipped" }));
            setAgentElapsed((prev) => ({ ...prev, reporter: elapsed }));
            setWaitingAgent(null);
            setPhase("done");
          } else {
            setAgentStates((prev) => ({ ...prev, reporter: "done" }));
            setAgentElapsed((prev) => ({ ...prev, reporter: elapsed }));
            const proj =
              (data?.project_name as string) ?? currentProject ?? "default";
            setResultReportUrl(`/api/reports/${proj}`);
            setWaitingAgent(null);
            setPhase("done");
          }
        }

        // ── user_input_requested ──────────────────────────────────
        if (d.event_type === "user_input_requested") {
          setGateOpen(false);
          const dataObj = (d.data ?? {}) as Record<string, unknown>;
          const gatePayload = dataObj.gate as
            | { phase?: string; prompt?: string }
            | undefined;
          const fr = parseFieldReview(dataObj.field_review);
          const ca = parseCleaningAssessment(dataObj.cleaning_assessment);
          const cr = parseCleaningReview(dataObj.cleaning_review);
          const ar = parseAnalystReview(dataObj.analyst_review);
          const incRev = parsePauseInteractionRevision(dataObj);
          const incomingRevision = incRev !== null ? incRev : Infinity;

          // Detect pure ask: has question+expected_format, no review tables
          const askQuestion = dataObj.question as string | undefined;
          const askFmt = dataObj.expected_format as string | undefined;
          const isPureAsk =
            !!askQuestion &&
            !!askFmt &&
            !fr &&
            !cr &&
            !ar &&
            !gatePayload &&
            !dataObj.field_review &&
            !dataObj.cleaning_review &&
            !dataObj.analyst_review;

          if (isPureAsk) {
            // CO-14: pure ask → AskUserPrompt
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "workflow",
                text: "",
                timestamp: d.timestamp,
                askUser: {
                  question: askQuestion,
                  expected_format: askFmt,
                  options: dataObj.options as string[] | undefined,
                },
              },
            ]);
          }

          // Field review handling (existing)
          if (fr) {
            const patchInPlace =
              activeFieldReviewId !== null &&
              (incomingRevision === activeFieldReviewRevision ||
                incomingRevision > activeFieldReviewRevision);
            if (patchInPlace) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === activeFieldReviewId
                    ? { ...m, fieldReview: fr, timestamp: d.timestamp }
                    : m,
                ),
              );
            } else {
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
          } else if (!fr && dataObj.message) {
            // 自由格式 markdown——LLM 直接输出的文本。去重：相同内容不重复追加
            const msgText = String(dataObj.message);
            if (!msgText.trim()) { /* 空消息跳过——ToolExchangeTurn 已展示 */ }
            else {
            setMessages((prev) => {
              if (prev.length > 0 && prev[prev.length - 1].text === msgText) return prev;
              return [
                ...prev,
                {
                  id: uid(),
                  role: "workflow",
                  text: msgText,
                  timestamp: d.timestamp,
                },
              ];
            });
            }
          } else if (!gatePayload && !cr && !ar && !isPureAsk) {
            setActiveFieldReviewId(null);
            setActiveFieldReviewRevision(-1);
            setFieldReviewScrollNonce(0);
          }

          // Cleaning review
          if (cr) {
            const patchCleaning =
              activeCleaningReviewId !== null &&
              incRev !== null &&
              (incRev === activeCleaningReviewRevision ||
                incRev > activeCleaningReviewRevision);
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

          // Cleaning assessment
          if (ca) {
            const cid = uid();
            const colLines = ca.columns
              .map(
                (c) =>
                  `<tr><td style="padding:4px 8px;border:1px solid #2a3040">${escapeHtml(c.column)}</td><td style="padding:4px 8px;border:1px solid #2a3040;color:#4ade80">${c.action === "clean" ? "清洗" : "不清洗"}</td><td style="padding:4px 8px;border:1px solid #2a3040">${escapeHtml(c.reason)}</td></tr>`,
              )
              .join("");
            const tableHtml = `<div style="margin-top:8px"><table style="width:100%;border-collapse:collapse;font-size:14px"><thead><tr style="background:#1e2430"><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">字段</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:center;width:80px">建议</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">原因</th></tr></thead><tbody>${colLines}</tbody></table></div>`;
            setMessages((prev) => [
              ...prev,
              {
                id: cid,
                role: "agent",
                text: ca.summary,
                html: `<p><strong>${escapeHtml(ca.summary)}</strong></p>${tableHtml}`,
                timestamp: d.timestamp,
              } as ConvoMessage,
            ]);
          }

          // Analyst review
          if (ar) {
            const patchAnalyst =
              activeAnalystReviewId !== null &&
              incRev !== null &&
              (incRev === activeAnalystReviewRevision ||
                incRev > activeAnalystReviewRevision);
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

          // Gate prompt
          if (gatePayload) {
            setGateOpen(true);
            const prompt =
              typeof gatePayload.prompt === "string"
                ? gatePayload.prompt.trim()
                : "";
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

          // Agent message text
          const raw = dataObj.message;
          const agentMsg = typeof raw === "string" ? raw.trim() : "";
          if (agentMsg) {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "agent",
                text: agentMsg,
                timestamp: d.timestamp,
              },
            ]);
          }

          const pausedAgent = resolveAgentKey(d.agent);
          setWaitingAgent(pausedAgent);
          setGateOpen(true);
          setPhase("running");
          setTimeout(() => replyInputRef.current?.focus(), 100);
        }

        // ── user_input_received ───────────────────────────────────
        if (d.event_type === "user_input_received") {
          const inner = (d.data ?? {}) as Record<string, unknown>;
          if (agentKey === "scout") {
            const hasNewFields =
              "parse_applied_count" in inner ||
              "columns_still_needing_input" in inner ||
              "pure_confirm" in inner;
            let line = "";
            if (hasNewFields) {
              line = formatScoutUserInputFactLine(inner);
            } else {
              const applied = inner.applied_field_updates;
              const lines = Array.isArray(applied)
                ? applied.filter(
                    (x): x is string =>
                      typeof x === "string" &&
                      x !== null &&
                      (x as string).trim() !== "",
                  )
                : [];
              if (lines.length > 0) {
                line = formatScoutAppliedUpdates(lines);
              }
            }
            if (line) {
              setMessages((prev) => [
                ...prev,
                {
                  id: uid(),
                  role: "system",
                  text: line,
                  timestamp: d.timestamp,
                },
              ]);
            }
          } else if (
            agentKey === "cleaner" &&
            typeof inner.proceed_accepted === "boolean"
          ) {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "system",
                text: formatStageProceedFactLine("清洗", inner),
                timestamp: d.timestamp,
              },
            ]);
          } else if (
            agentKey === "analyst" &&
            typeof inner.proceed_accepted === "boolean"
          ) {
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

        // ── run_completed ─────────────────────────────────────────
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
            setAgentStates({
              scout: "idle",
              cleaner: "idle",
              analyst: "idle",
              reporter: "idle",
            });
            setAgentElapsed({
              scout: 0,
              cleaner: 0,
              analyst: 0,
              reporter: 0,
            });
            setResultReportUrl(null);
            setGuardrailsBlocked(false);
            setBlockedRunId(null);
            setReplyPending?.(false);
            onThinking?.(null);
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
}
