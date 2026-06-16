import "./index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initWebSocket } from "./hooks/useWebSocket";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";

const root = document.getElementById("root");
if (!root) throw new Error("root element missing");

try {
  initWebSocket();
} catch (e) {
  console.error("[HaGoKu Studio] initWebSocket failed", e);
}

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
);
