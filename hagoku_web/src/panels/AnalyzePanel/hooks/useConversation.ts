import { useState } from "react";
import type { ConvoMessage } from "../types";
import { uid } from "../utils";
import { eventLog } from "../../../utils/eventLog";

eventLog("load", "useConversation");

export function useConversation(_log?: (msg: string) => void) {
  const [messages, setMessages] = useState<ConvoMessage[]>([]);

  function persist(_next: ConvoMessage[]) {
    // 前端不持久化消息。快照是唯一真相源，来自后端。
  }

  // ── 幂等方法 ──

  const addSystemMsg = (text: string, timestamp?: string) => {
    const ts = timestamp ?? new Date().toISOString();
    setMessages((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].role === "system" && prev[prev.length - 1].text === text) return prev;
      const next = [...prev, { id: uid(), role: "system", text, timestamp: ts }];
      persist(next);
      return next;
    });
  };

  const addUserMsg = (text: string) => {
    const ts = new Date().toISOString();
    eventLog("msg", `send ${text.slice(0, 40)}`);
    setMessages((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].role === "user" && prev[prev.length - 1].text === text) return prev;
      const next = [...prev, { id: uid(), role: "user", text, timestamp: ts }];
      persist(next);
      return next;
    });
  };

  const addAgentMsg = (text: string, timestamp?: string) => {
    const ts = timestamp ?? new Date().toISOString();
    setMessages((prev) => {
      // 流式追加到上一条 agent 消息
      if (prev.length > 0 && prev[prev.length - 1].role === "agent" && !prev[prev.length - 1].text?.startsWith("{")) {
        const next = [...prev.slice(0, -1), { ...prev[prev.length - 1], text: prev[prev.length - 1].text + text, timestamp: ts }];
        persist(next);
        return next;
      }
      const next = [...prev, { id: uid(), role: "agent", text, timestamp: ts }];
      persist(next);
      return next;
    });
  };

  const addWorkflowCard = (card: Partial<ConvoMessage> & { id?: string }) => {
    const id = card.id ?? uid();
    const ts = card.timestamp ?? new Date().toISOString();
    setMessages((prev) => {
      if (card.fieldReview && prev.some((m) => m.fieldReview)) return prev;
      if (card.cleaningReview && prev.some((m) => m.cleaningReview)) return prev;
      if (card.analystReview && prev.some((m) => m.analystReview)) return prev;
      if (card.askUser && prev.some((m) => m.askUser?.question === card.askUser?.question)) return prev;
      const next = [...prev, {
        id, role: "workflow", text: card.text ?? "", timestamp: ts,
        fieldReview: card.fieldReview, cleaningReview: card.cleaningReview,
        analystReview: card.analystReview, askUser: card.askUser,
      }];
      persist(next);
      return next;
    });
  };

  const updateWorkflowCard = (id: string, updates: Partial<ConvoMessage>) => {
    setMessages((prev) => {
      const next = prev.map((m) => (m.id === id ? { ...m, ...updates } : m));
      persist(next);
      return next;
    });
  };

  const clearMessages = () => { eventLog("state", "clear_messages"); setMessages([]); persist([]); };

  // ── 流结束：清除 streaming 标记 ──

  const endStream = () => {
    setMessages((prev) => {
      const next = prev.map((m) => (m.streaming ? { ...m, streaming: false } : m));
      persist(next);
      return next;
    });
  };

  // ── 原始消息追加（供 handlers 内部特殊消息使用，不推荐外部直接调） ──

  const addRawMsg = (msg: ConvoMessage) => {
    setMessages((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].id === msg.id) return prev;
      const next = [...prev, msg];
      persist(next);
      return next;
    });
  };

  // ── snapshot 同步 ──

  const syncFromSnapshot = (snapMsgs: ConvoMessage[]) => {
    setMessages((_prev) => {
      eventLog("snapshot", `sync msgs=${snapMsgs.length}`);
      persist(snapMsgs);
      return snapMsgs;
    });
  };

  return {
    messages,
    // 幂等入口（外部首选）
    addSystemMsg, addUserMsg, addAgentMsg, endStream,
    addWorkflowCard, updateWorkflowCard,
    syncFromSnapshot, clearMessages,
    // 内部入口（特殊消息类型，无幂等）
    addRawMsg,
    _setMessages: setMessages,
  };
}
