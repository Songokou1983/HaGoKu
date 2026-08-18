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

export function useConversation(_log?: (msg: string) => void) {
  const [messages, setMessages] = useState<ConvoMessage[]>([]);

  // ── 全量替换（snapshot 到达时调用）──
  const _set = (msgs: ConvoMessage[]) => {
    setMessages(msgs);
    try { localStorage.setItem(_storageKey(), JSON.stringify(msgs.slice(-100))); } catch {}
    eventLog("persist", `${msgs.length} msgs`);
  };

  // ── 乐观显示用户消息 ──
  const addUserMsg = (text: string) => {
    const ts = new Date().toISOString();
    eventLog("msg", `send ${text.slice(0, 40)}`);
    setMessages((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].role === "user" && prev[prev.length - 1].text === text) return prev;
      const next: ConvoMessage[] = [...prev, { id: uid(), role: "user", text, timestamp: ts }];
      return next;
    });
  };

  // ── 流式追加（按 streamId 搜索追加或新建）──
  const appendDelta = (streamId: string, delta: string) => {
    setMessages((prev) => {
      for (let i = prev.length - 1; i >= 0; i--) {
        if (prev[i].streaming && prev[i].streamId === streamId) {
          return prev.map((m, idx) => idx === i ? { ...m, text: m.text + delta } : m);
        }
      }
      return [...prev, { id: uid(), role: "agent", text: delta, timestamp: new Date().toISOString(), streaming: true, streamId }];
    });
  };

  // ── 流结束：清除 streaming 标记 ──
  const endStream = () => {
    setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)));
  };

  const clearMessages = () => { eventLog("state", "clear_messages"); setMessages([]); try { localStorage.removeItem(_storageKey()); } catch {} };

  return {
    messages,
    setMessages: _set,
    addUserMsg,
    appendDelta,
    endStream,
    clearMessages,
  };
}
