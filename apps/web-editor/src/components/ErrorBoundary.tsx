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
    console.error("Frontend render error", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
          <h1>Shuddho could not load</h1>
          <p>A frontend error occurred. Please check the backend URL and reload.</p>
          {this.state.message ? <pre style={{ whiteSpace: "pre-wrap" }}>{this.state.message}</pre> : null}
        </main>
      );
    }

    return this.props.children;
  }
}
