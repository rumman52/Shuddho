import { ErrorBoundary } from "../../web-editor/src/components/ErrorBoundary";
import CoworkerGate from "../../web-editor/src/coworker/CoworkerGate";

export default function App() {
  const editorUrl = import.meta.env.VITE_EDITOR_APP_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:5175" : "/editor");
  return (
    <ErrorBoundary>
      <div className="rukh-coworker-app">
        <header className="rukh-productbar">
          <a className="rukh-product-brand" href="/coworker" aria-label="Rukh AI Coworker home">
            <span className="rukh-brand-mark" aria-hidden="true">r</span>
            <span><strong>Rukh AI</strong><small>Coworker</small></span>
          </a>
          <a className="rukh-product-switch" href={editorUrl}>Open Editor <span aria-hidden="true">↗</span></a>
        </header>
        <CoworkerGate />
      </div>
    </ErrorBoundary>
  );
}
