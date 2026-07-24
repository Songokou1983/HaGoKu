import { useState } from "react";
import type { ConvoMessage } from "../types";
import { uid } from "../utils";
import { eventLog } from "../../../utils/eventLog";
import { useWorkspaceStore } from "../../../stores/workspace";

eventLog("load", "useConversation");

const BASE_KEY = "hagoku_session";

function _storageKey(): string {
  const proj = useWorkspaceStore.getState().currentProject;
  return proj ? `${BASE_KEY}_${proj}` : BASE_KEY;
}

function loadSession(): ConvoMessage[] {
  try {
    // 优先读项目隔离的 key，回退旧的非隔离 key（迁移兼容）
    const key = _storageKey();
    const raw = localStorage.getItem(key)
      ?? (key !== BASE_KEY ? localStorage.getItem(BASE_KEY) : null);
    if (raw) return JSON.parse(raw) as ConvoMessage[];
  } catch {}
  return [];
}

export function useConversation(_log?: (msg: string) => void) {
  const [messages, setMessages] = useState<ConvoMessage[]>(loadSession);

  // 同步持久化 — useEffect 是异步的，断连时可能没来得及执行
  // 改为每次写入时直接在 setMessages 回调中同步写 localStorage
  function persist(next: ConvoMessage[]) {
    try { localStorage.setItem(_storageKey(), JSON.stringify(next.slice(-100))); } catch {}
    eventLog("persist", `${next.length} msgs`);
  }

  const addSystemMsg = (text: string, timestamp?: string) => {
    const ts = timestamp ?? new Date().toISOString();
    setMessages((prev) => {
      // 去重：相同文本不重复追加
      if (prev.length > 0 && prev[prev.length - 1].text === text && prev[prev.length - 1].role === "system") {
        return prev;
      }
      const next = [...prev, { id: uid(), role: "system", text, timestamp: ts }];
      persist(next);
      return next;
    });
  };

  const addUserMsg = (text: string) => {
    const ts = new Date().toISOString();
    eventLog("msg", `send ${text.slice(0,40)}`);
    setMessages((prev) => {
      const next = [...prev, { id: uid(), role: "user", text, timestamp: ts }];
      persist(next);
      return next;
    });
  };

  const addAgentMsg = (text: string, html?: string, timestamp?: string) => {
    const ts = timestamp ?? new Date().toISOString();
    const msg: ConvoMessage = { id: uid(), role: "agent", text, timestamp: ts };
    if (html) (msg as any).html = html;
    setMessages((prev) => {
      const next = [...prev, msg];
      persist(next);
      return next;
    });
  };

  const addWorkflowCard = (card: Partial<ConvoMessage> & { id?: string }) => {
    const id = card.id ?? uid();
    const ts = card.timestamp ?? new Date().toISOString();
    setMessages((prev) => {
      // 去重：相同类型卡片不重复追加
      if (card.fieldReview && prev.some((m) => m.fieldReview)) return prev;
      if (card.cleaningReview && prev.some((m) => m.cleaningReview)) return prev;
      if (card.analystReview && prev.some((m) => m.analystReview)) return prev;
      if (card.askUser && prev.some((m) => m.askUser?.question === card.askUser?.question)) return prev;
      const next = [...prev, {
        id, role: "workflow", text: card.text ?? "", timestamp: ts,
        fieldReview: card.fieldReview,
        cleaningReview: card.cleaningReview,
        analystReview: card.analystReview,
        askUser: card.askUser,
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

  return {
    messages, setMessages,
    addSystemMsg, addUserMsg, addAgentMsg, addWorkflowCard, updateWorkflowCard,
    clearMessages,
  };
}
