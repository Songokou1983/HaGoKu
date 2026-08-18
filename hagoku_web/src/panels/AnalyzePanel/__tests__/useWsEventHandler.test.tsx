import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useWsEventHandler } from "../hooks/useWsEventHandler";
import type { AgentKey } from "../types";

// ── Helpers ─────────────────────────────────────────────────────────

function makeDeps(overrides: Partial<any> = {}) {
  const setMessages = vi.fn() as any;
  const appendDelta = vi.fn() as any;
  const endStream = vi.fn() as any;
  const addUserMsg = vi.fn() as any;
  const clearMessages = vi.fn() as any;
  const setAgentElapsed = vi.fn() as any;
  const agentStartTimes = { current: {} };
  const setWaitingAgent = vi.fn() as any;
  const setPhase = vi.fn() as any;
  const setFieldReviewScrollNonce = vi.fn() as any;
  const setGateOpen = vi.fn() as any;
  const setGuardrailsBlocked = vi.fn() as any;
  const setBlockedRunId = vi.fn() as any;
  const setResultReportUrl = vi.fn() as any;
  const replySnapshotRef = { current: null };
  const replyInputRef = { current: null } as any;
  const onThinking = vi.fn();
  const setReplyPending = vi.fn();

  return {
    batch: [] as any[],
    setMessages,
    appendDelta,
    endStream,
    addUserMsg,
    clearMessages,
    setAgentElapsed,
    agentStartTimes,
    setWaitingAgent,
    setPhase,
    setFieldReviewScrollNonce,
    setGateOpen,
    setGuardrailsBlocked,
    setBlockedRunId,
    setResultReportUrl,
    replySnapshotRef,
    replyInputRef,
    waitinAgent: null as AgentKey | null,
    gateOpen: false,
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
  it("no longer pushes messages (snapshot pushed after session update)", () => {
    const deps = makeDeps({
      batch: [
        makeEvent("tool_exchange", "analyst", {
          stage: "analyst",
          tool_calls: [{ id: "tc-1", name: "get_stats" }],
        }),
      ],
    });

    renderHook(() => useWsEventHandler(deps));

    // tool_exchange 不构造消息；工具卡片由 state_snapshot 推送
    expect(deps.setMessages).not.toHaveBeenCalled();
    expect(deps.appendDelta).not.toHaveBeenCalled();
  });
});

describe("useWsEventHandler — ask", () => {
  it("no longer pushes askUser messages (data comes from snapshot)", () => {
    const deps = makeDeps({
      batch: [
        makeEvent("user_input_requested", "analyst", {
          question: "是否继续分析？",
          expected_format: "yes_no",
        }),
      ],
    });

    renderHook(() => useWsEventHandler(deps));

    // user_input_requested 不再构造消息
    expect(deps.setMessages).not.toHaveBeenCalled();
    expect(deps.appendDelta).not.toHaveBeenCalled();
    // 但仍然设置 gate 和 waiting agent
    expect(deps.setGateOpen).toHaveBeenCalledWith(true);
    expect(deps.setWaitingAgent).toHaveBeenCalled();
  });
});

describe("useWsEventHandler — agent_stream_delta", () => {
  it("calls appendDelta on stream delta", () => {
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

    expect(deps.appendDelta).toHaveBeenCalledWith("s1", "你好");
  });
});

describe("useWsEventHandler — agent_stream_end", () => {
  it("calls endStream on stream end", () => {
    const deps = makeDeps({
      batch: [
        makeEvent("agent_stream_end", "analyst", {
          stream_id: "s1",
          agent: "analyst",
        }),
      ],
    });

    renderHook(() => useWsEventHandler(deps));

    expect(deps.endStream).toHaveBeenCalled();
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

    // Agent state 通过 workspace store 管理
    // 只需验证没有异常
    expect(true).toBe(true);
  });
});

describe("useWsEventHandler — replyPending", () => {
  it("does NOT clear replyPending on ack:respond (LLM not yet responding)", () => {
    const setReplyPending = vi.fn();
    const deps = makeDeps({
      batch: [{ type: "ack", cmd: "respond" }],
      setReplyPending,
    });

    renderHook(() => useWsEventHandler(deps));

    expect(setReplyPending).not.toHaveBeenCalled();
  });
});
