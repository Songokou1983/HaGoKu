import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useWsEventHandler } from "../hooks/useWsEventHandler";
import type { ConvoMessage } from "../types";
import type { AgentKey } from "../types";

// ── Helpers ─────────────────────────────────────────────────────────

function makeDeps(overrides: Partial<any> = {}) {
  const setMessages = vi.fn() as any;
  const setAgentStates = vi.fn() as any;
  const setAgentElapsed = vi.fn() as any;
  const agentStartTimes = { current: {} };
  const setWaitingAgent = vi.fn() as any;
  const setPhase = vi.fn() as any;
  const setActiveFieldReviewId = vi.fn() as any;
  const setActiveFieldReviewRevision = vi.fn() as any;
  const setFieldReviewScrollNonce = vi.fn() as any;
  const setActiveCleaningReviewId = vi.fn() as any;
  const setActiveCleaningReviewRevision = vi.fn() as any;
  const setActiveAnalystReviewId = vi.fn() as any;
  const setActiveAnalystReviewRevision = vi.fn() as any;
  const setGateOpen = vi.fn() as any;
  const setGuardrailsBlocked = vi.fn() as any;
  const setBlockedRunId = vi.fn() as any;
  const setResultReportUrl = vi.fn() as any;
  const replySnapshotRef = { current: null };
  const replyInputRef = { current: null };
  const onThinking = vi.fn();
  const setReplyPending = vi.fn();

  return {
    batch: [] as any[],
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
    waitinAgent: null as AgentKey | null,
    gateOpen: false,
    activeFieldReviewId: null as string | null,
    activeFieldReviewRevision: -1,
    activeCleaningReviewId: null as string | null,
    activeCleaningReviewRevision: -1,
    activeAnalystReviewId: null as string | null,
    activeAnalystReviewRevision: -1,
    currentProject: null as string | null,
    onThinking,
    setReplyPending,
    ...overrides,
  };
}

function makeEvent(event_type: string, agent: string, data: Record<string, unknown> = {}) {
  return {
    type: "event",
    data: {
      event_id: "evt-1",
      event_type,
      timestamp: new Date().toISOString(),
      agent,
      data,
      parent_id: null,
    },
  };
}

// ── Tests ───────────────────────────────────────────────────────────

describe("useWsEventHandler — tool_exchange", () => {
  it("pushes a ConvoMessage with toolExchange when tool_exchange event arrives", () => {
    const deps = makeDeps({
      batch: [
        makeEvent("tool_exchange", "analyst", {
          stage: "analyst",
          revision: 0,
          timestamp: new Date().toISOString(),
          assistant_pre_text: "让我看看数据",
          tool_calls: [
            {
              id: "tc-1",
              name: "get_stats",
              arguments_summary: '{"col":"Revenue"}',
              result_summary: "mean=100.5",
              error: null,
              duration_ms: 120,
            },
          ],
        }),
      ],
    });

    renderHook(() => useWsEventHandler(deps));

    expect(deps.setMessages).toHaveBeenCalled();
    const updater = deps.setMessages.mock.calls[0][0];
    const prev: ConvoMessage[] = [];
    const next = typeof updater === "function" ? updater(prev) : updater;
    expect(next).toHaveLength(1);
    expect(next[0].role).toBe("agent");
    expect(next[0].toolExchange).toBeDefined();
    expect(next[0].toolExchange!.tool_calls).toHaveLength(1);
    expect(next[0].toolExchange!.tool_calls[0].name).toBe("get_stats");
  });
});

describe("useWsEventHandler — ask (pure)", () => {
  it("pushes an askUser message for pure ask payload (no review tables)", () => {
    const deps = makeDeps({
      batch: [
        makeEvent("user_input_requested", "analyst", {
          question: "是否继续分析？",
          expected_format: "yes_no",
        }),
      ],
    });

    renderHook(() => useWsEventHandler(deps));

    expect(deps.setMessages).toHaveBeenCalled();
    const updater = deps.setMessages.mock.calls[0][0];
    const prev: ConvoMessage[] = [];
    const next = typeof updater === "function" ? updater(prev) : updater;
    // Should have at least 1 message: the askUser message
    const askMsg = next.find((m: ConvoMessage) => m.askUser);
    expect(askMsg).toBeDefined();
    expect(askMsg!.askUser!.question).toBe("是否继续分析？");
    expect(askMsg!.askUser!.expected_format).toBe("yes_no");
  });

  it("does NOT create askUser message when review tables are present", () => {
    const deps = makeDeps({
      batch: [
        makeEvent("user_input_requested", "scout", {
          question: "确认字段？",
          expected_format: "yes_no",
          field_review: {
            n_rows: 100,
            n_cols: 5,
            analysis_fields_summary: "test",
            rows: [
              {
                field_name: "col1",
                chinese_name: "列1",
                meaning: "test",
                suggested_role: "feature",
                used_in_analysis: true,
              },
            ],
          },
        }),
      ],
      activeFieldReviewId: null,
      activeFieldReviewRevision: -1,
    });

    renderHook(() => useWsEventHandler(deps));

    // Should have messages but no askUser message
    const updater = deps.setMessages.mock.calls[0][0];
    const prev: ConvoMessage[] = [];
    const next = typeof updater === "function" ? updater(prev) : updater;
    const askMsg = next.find((m: ConvoMessage) => m.askUser);
    expect(askMsg).toBeUndefined();
  });
});

describe("useWsEventHandler — agent_stream_delta", () => {
  it("creates a new streaming message on first delta", () => {
    const deps = makeDeps({
      batch: [
        makeEvent("agent_stream_delta", "analyst", {
          stream_id: "s1",
          delta: "你好",
          agent: "analyst",
        }),
      ],
    });

    renderHook(() => useWsEventHandler(deps));

    const updater = deps.setMessages.mock.calls[0][0];
    const prev: ConvoMessage[] = [];
    const next = typeof updater === "function" ? updater(prev) : updater;
    expect(next).toHaveLength(1);
    expect(next[0].streaming).toBe(true);
    expect(next[0].streamId).toBe("s1");
    expect(next[0].text).toBe("你好");
  });

  it("appends delta to existing streaming message", () => {
    const existingMsg: ConvoMessage = {
      id: "m1",
      role: "agent",
      text: "你好",
      timestamp: "",
      streaming: true,
      streamId: "s1",
    };

    const deps = makeDeps({
      batch: [
        makeEvent("agent_stream_delta", "analyst", {
          stream_id: "s1",
          delta: "，世界",
          agent: "analyst",
        }),
      ],
    });

    // Capture the updater to check it appends
    renderHook(() => useWsEventHandler(deps));

    const updater = deps.setMessages.mock.calls[0][0];
    const next = typeof updater === "function" ? updater([existingMsg]) : updater;
    expect(next).toHaveLength(1);
    expect(next[0].text).toBe("你好，世界");
    expect(next[0].streaming).toBe(true);
  });

  it("creates new streaming message if streamId differs", () => {
    const existingMsg: ConvoMessage = {
      id: "m1",
      role: "agent",
      text: "旧内容",
      timestamp: "",
      streaming: true,
      streamId: "old-stream",
    };

    const deps = makeDeps({
      batch: [
        makeEvent("agent_stream_delta", "analyst", {
          stream_id: "new-stream",
          delta: "新内容",
          agent: "analyst",
        }),
      ],
    });

    renderHook(() => useWsEventHandler(deps));

    const updater = deps.setMessages.mock.calls[0][0];
    const next = typeof updater === "function" ? updater([existingMsg]) : updater;
    expect(next).toHaveLength(2);
  });
});

describe("useWsEventHandler — agent_stream_end", () => {
  it("sets streaming=false on the matching message", () => {
    const existingMsg: ConvoMessage = {
      id: "m1",
      role: "agent",
      text: "完整内容",
      timestamp: "",
      streaming: true,
      streamId: "s1",
    };

    const deps = makeDeps({
      batch: [
        makeEvent("agent_stream_end", "analyst", {
          stream_id: "s1",
          agent: "analyst",
        }),
      ],
    });

    renderHook(() => useWsEventHandler(deps));

    const updater = deps.setMessages.mock.calls[0][0];
    const next = typeof updater === "function" ? updater([existingMsg]) : updater;
    expect(next[0].streaming).toBe(false);
    expect(next[0].streamId).toBeUndefined();
  });
});

describe("useWsEventHandler — agent_thinking", () => {
  it("calls onThinking callback instead of pushing to messages", () => {
    const onThinking = vi.fn();
    const deps = makeDeps({
      batch: [
        makeEvent("agent_thinking", "analyst", {
          thought: "正在分析数据...",
        }),
      ],
      onThinking,
    });

    renderHook(() => useWsEventHandler(deps));

    expect(onThinking).toHaveBeenCalledWith("正在分析数据...");
    // Should NOT push to messages
    expect(deps.setMessages).not.toHaveBeenCalled();
  });
});

describe("useWsEventHandler — CO-05 pipeline fallback", () => {
  it("resolves agent when agent_started has empty agent field", () => {
    const deps = makeDeps({
      batch: [
        {
          type: "event",
          data: {
            event_id: "evt-1",
            event_type: "agent_started",
            timestamp: new Date().toISOString(),
            agent: "",
            data: {},
            parent_id: null,
          },
        },
      ],
    });

    renderHook(() => useWsEventHandler(deps));

    // Should still set agent state to running
    expect(deps.setAgentStates).toHaveBeenCalled();
  });
});

describe("useWsEventHandler — replyPending", () => {
  it("clears replyPending on ack:respond", () => {
    const setReplyPending = vi.fn();
    const deps = makeDeps({
      batch: [{ type: "ack", cmd: "respond" }],
      setReplyPending,
    });

    renderHook(() => useWsEventHandler(deps));

    expect(setReplyPending).toHaveBeenCalledWith(false);
  });
});
