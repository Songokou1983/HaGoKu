import { Component, type CSSProperties, type ErrorInfo, type ReactNode } from "react";
import { eventLog } from "../utils/eventLog";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    eventLog("error", `${error.message} stack=${info.componentStack?.slice(0,100)}`);
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      const shell: CSSProperties = {
        minHeight: "100vh",
        boxSizing: "border-box",
        backgroundColor: "#121826",
        color: "#e2e5eb",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
        fontFamily: "system-ui, sans-serif",
      };
      return (
        <div style={shell}>
          <div style={{ color: "#ef4444", fontSize: "15px", fontWeight: 600, marginBottom: "0.5rem" }}>
            出现错误
          </div>
          <pre
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "13px",
              color: "#b8bfca",
              background: "#131a28",
              borderRadius: "8px",
              padding: "1rem",
              maxWidth: "32rem",
              overflow: "auto",
              marginBottom: "1rem",
            }}
          >
            {this.state.error?.message}
          </pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              padding: "0.5rem 1rem",
              background: "#3b82f6",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              fontSize: "13px",
              cursor: "pointer",
            }}
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
