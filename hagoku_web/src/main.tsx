import "./index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initWebSocket } from "./hooks/useWebSocket";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { eventLog } from "./utils/eventLog";

eventLog("app", "start");

const root = document.getElementById("root");
if (!root) throw new Error("root element missing");

try {
  initWebSocket();
  eventLog("app", "ws_init_ok");
} catch (e) {
  eventLog("app", `ws_init_fail ${String(e)}`);
}

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
);
