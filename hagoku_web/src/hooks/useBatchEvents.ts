import { useEffect, useRef, useCallback, useState } from "react";
import type { WSMessage } from "../types/events";
import { useWebSocket } from "./useWebSocket";

/**
 * Batches incoming WebSocket events via requestAnimationFrame to avoid
 * excessive re-renders under high event throughput.
 *
 * Returns the accumulated messages array, replacing on each animation frame.
 */
export function useBatchEvents() {
  const { onMessage } = useWebSocket();
  const [batch, setBatch] = useState<WSMessage[]>([]);
  const pendingRef = useRef<WSMessage[]>([]);
  const rafRef = useRef<ReturnType<typeof requestAnimationFrame> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, []);

  const flush = useCallback(() => {
    rafRef.current = null;
    if (!mountedRef.current) return;
    const snapshot = pendingRef.current;
    pendingRef.current = [];
    setBatch(snapshot);
  }, []);

  useEffect(() => {
    return onMessage((msg: WSMessage) => {
      pendingRef.current.push(msg);
      if (rafRef.current === null) {
        rafRef.current = requestAnimationFrame(flush);
      }
    });
  }, [onMessage, flush]);

  return batch;
}