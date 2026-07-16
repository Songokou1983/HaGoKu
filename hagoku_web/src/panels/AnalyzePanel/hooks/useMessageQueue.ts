import { useState, useCallback, useEffect } from "react";
import { sanitizeText } from "../../../utils/sanitize";

interface QueueDeps {
  send: (cmd: string, payload: Record<string, unknown>) => boolean;
  gateOpen: boolean;
  replyPending: boolean;
  setReplyPending: (v: boolean) => void;
  setGateOpen: (v: boolean) => void;
  addUserMsg: (text: string) => void;
}

export function useMessageQueue(deps: QueueDeps) {
  const { send, gateOpen, replyPending, setReplyPending, setGateOpen, addUserMsg } = deps;
  const [queue, setQueue] = useState<string[]>([]);

  const enqueue = useCallback((text: string) => {
    setQueue(prev => [...prev, text]);
    addUserMsg(text);
  }, [addUserMsg]);

  // 出队条件：gate 开 且 不在处理中
  useEffect(() => {
    if (!gateOpen || replyPending) return;
    let next: string | null = null;
    setQueue(prev => {
      if (prev.length === 0) return prev;
      next = prev[0];
      return prev.slice(1);
    });
    if (next) {
      send("respond", { text: next });
      setReplyPending(true);
      setGateOpen(false);
    }
  }, [gateOpen, replyPending]);

  const submit = useCallback((raw: string) => {
    const outgoing = sanitizeText(raw.trim());
    if (!outgoing) return;
    enqueue(outgoing);
  }, [enqueue]);

  return { submit, queue };
}
