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

  // 出队：gate 开 + 不在处理中 + 队列非空
  useEffect(() => {
    if (!gateOpen || replyPending || queue.length === 0) return;
    const next = queue[0];
    setQueue(prev => prev.slice(1));
    send("respond", { text: next });
    setReplyPending(true);
    setGateOpen(false);
  }, [gateOpen, replyPending, queue.length]);

  const submit = useCallback((raw: string) => {
    const outgoing = sanitizeText(raw.trim());
    if (!outgoing) return;
    enqueue(outgoing);
  }, [enqueue]);

  return { submit, queue };
}
