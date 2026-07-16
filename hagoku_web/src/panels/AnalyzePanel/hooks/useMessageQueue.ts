import { useRef, useCallback, useEffect, useMemo } from "react";
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
  const pending = useRef<string[]>([]);

  const flush = useCallback(() => {
    console.log("[queue] flush gateOpen=", gateOpen, "replyPending=", replyPending, "pending.length=", pending.current.length);
    if (!gateOpen || replyPending) return;
    const msgs = pending.current;
    if (msgs.length === 0) return;
    const next = msgs.shift()!;
    console.log("[queue] flush sending:", next.slice(0, 30));
    send("respond", { text: next });
    setReplyPending(true);
    setGateOpen(false);
  }, [send, gateOpen, replyPending, setReplyPending, setGateOpen]);

  // gate 或处理状态变化时尝试消费队列
  useEffect(() => { flush(); }, [flush]);

  const submit = useCallback((raw: string) => {
    const outgoing = sanitizeText(raw.trim());
    if (!outgoing) return;
    console.log("[queue] submit", outgoing.slice(0, 30));
    addUserMsg(outgoing);
    pending.current.push(outgoing);
    console.log("[queue] pending.length=", pending.current.length, "gateOpen=", gateOpen, "replyPending=", replyPending);
    flush();
    console.log("[queue] after flush, pending.length=", pending.current.length);
  }, [addUserMsg, flush]);

  const pendingCount = pending.current.length;

  return { submit, pendingCount };
}
