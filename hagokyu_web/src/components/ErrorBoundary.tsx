import { Component, type ErrorInfo, type ReactNode } from "react";

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
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            height: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            background: "#1e1e1e",
            color: "#cccccc",
            fontFamily: "monospace",
            padding: 32,
          }}
        >
          <h2 style={{ color: "#f44747", marginBottom: 8 }}>Something went wrong</h2>
          <p style={{ color: "#888", fontSize: 13, maxWidth: 600, textAlign: "center" }}>
            {this.state.error?.message}
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: 16,
              padding: "6px 16px",
              background: "#3a3a3a",
              color: "#d4d4d4",
              border: "1px solid #555",
              borderRadius: 4,
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}