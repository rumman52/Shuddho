import { ErrorBoundary } from "../../web-editor/src/components/ErrorBoundary";
import CoworkerGate from "../../web-editor/src/coworker/CoworkerGate";

function ArrowIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" fill="none">
      <path d="M4 12 12 4M5 4h7v7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function App() {
  const editorUrl = import.meta.env.VITE_EDITOR_APP_URL ?? "/editor";
  return (
    <ErrorBoundary>
      <div className="rukh-coworker-app">
        <header className="rukh-productbar">
          <a className="rukh-product-brand" href="/" aria-label="Rukh AI workspace home" target="_blank" rel="noreferrer">
            <span className="rukh-brand-mark" aria-hidden="true">r</span>
            <span><strong>Rukh AI</strong><small>AI Coworker</small></span>
          </a>
          <nav className="rukh-product-switcher" aria-label="Workspace navigation">
            <a className="rukh-product-switch rukh-product-switch--home" href="/workspaces" target="_blank" rel="noreferrer">All workspaces</a>
            <a className="rukh-product-switch" href={editorUrl} target="_blank" rel="noreferrer">Web Editor <ArrowIcon /></a>
          </nav>
        </header>
        <CoworkerGate />
      </div>
    </ErrorBoundary>
  );
}
