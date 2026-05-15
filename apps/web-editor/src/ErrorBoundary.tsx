import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    error: null,
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Shuddho web editor crashed", error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="app-shell">
          <section className="error-boundary-panel" role="alert">
            <p className="eyebrow">Shuddho</p>
            <h1>The editor could not finish loading.</h1>
            <p>
              A frontend error occurred, so the blank page has been replaced with this recovery message.
              Refresh the page or check the browser console for details.
            </p>
            <pre>{this.state.error.message}</pre>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}
