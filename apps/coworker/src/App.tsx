import { ErrorBoundary } from "../../web-editor/src/components/ErrorBoundary";
import CoworkerGate from "../../web-editor/src/coworker/CoworkerGate";

export default function App() {
  return (
    <ErrorBoundary>
      <div className="rukh-coworker-app">
        <header className="rukh-productbar">
          <a className="rukh-product-brand" href="/coworker" aria-label="Rukh AI Coworker home">
            <span className="rukh-brand-mark" aria-hidden="true">r</span>
            <span><strong>Rukh AI</strong><small>Coworker</small></span>
          </a>
          <a className="rukh-product-switch" href="/editor">Open Editor <span aria-hidden="true">↗</span></a>
        </header>
        <CoworkerGate />
      </div>
    </ErrorBoundary>
  );
}
