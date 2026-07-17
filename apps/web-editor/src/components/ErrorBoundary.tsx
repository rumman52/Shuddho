import React from "react";

type Props = {
  children: React.ReactNode;
};

type State = {
  hasError: boolean;
  message?: string;
};

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error.message,
    };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("Frontend render error", error, info.componentStack);
    } else {
      console.error("Frontend render error", error.name);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
          <h1>Shuddho encountered an unexpected editor error</h1>
          <p>Reload the page to recover. If this repeats, contact support with the time of the error.</p>
          <button type="button" onClick={() => window.location.reload()}>Reload</button>
          {import.meta.env.DEV && this.state.message ? <pre style={{ whiteSpace: "pre-wrap" }}>{this.state.message}</pre> : null}
        </main>
      );
    }

    return this.props.children;
  }
}
