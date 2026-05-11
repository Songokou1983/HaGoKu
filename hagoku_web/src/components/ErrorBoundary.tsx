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
        <div className="flex flex-col items-center justify-center h-full bg-app-bg text-app-text p-8">
          <div className="text-app-error text-ui-md font-semibold mb-2">出现错误</div>
          <pre className="font-mono text-ui-sm text-app-text-muted bg-app-bg-secondary rounded p-4 max-w-lg overflow-auto mb-4">
            {this.state.error?.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-app-accent hover:bg-app-accent-hover text-white text-ui-sm rounded
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent
                       transition-colors duration-150 cursor-pointer"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
