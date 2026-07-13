import { useEffect } from "react";
import type { WsEventDeps } from "../types";
import {
  handleStateSnapshot,
  handleAck,
  handleError,
  handleEvent,
} from "./handlers";

export function useWsEventHandler(deps: WsEventDeps) {
  const { batch } = deps;

  useEffect(() => {
    if (!batch || batch.length === 0) return;
    for (const msg of batch) {
      if (msg.type === "state_snapshot") {
        if (handleStateSnapshot(deps, msg)) continue;
      }
      if (msg.type === "ack") {
        if (handleAck(deps, msg)) continue;
      }
      if (msg.type === "error") {
        if (handleError(deps, msg)) continue;
      }
      if (msg.type === "event" && msg.data) {
        handleEvent(deps, msg);
      }
    }
  }, [batch]);
}
