import "./index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initWebSocket } from "./hooks/useWebSocket";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";

const root = document.getElementById("root");
if (!root) throw new Error("root element missing");

// Start shared WebSocket connection early
initWebSocket();

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
);