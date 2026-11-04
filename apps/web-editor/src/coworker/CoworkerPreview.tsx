import { useRef, useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import "./coworker-preview.css";

const starters = [
  ["Plan a project", "Help me plan a project. My goal is "],
  ["Improve my writing", "Help me improve this draft while preserving its meaning:\n\n"],
  ["Prepare a research brief", "Prepare a research brief about "],
] as const;

/** Public, memory-only draft surface. Never creates an auth/API client. */
export default function CoworkerPreview() {
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);

  async function copyDraft() {
    try {
      await navigator.clipboard.writeText(draft);
      setNotice("Draft copied. Keep a copy before leaving this page.");
    } catch {
      input.current?.focus();
      input.current?.select();
      setNotice("Copy could not finish. Your draft is selected; use your device’s copy command.");
    }
  }

  return <div className="rukh-coworker-app cw-preview">
    <header className="rukh-productbar">
      <a className="rukh-product-brand" href="/workspaces" aria-label="Rukh AI workspace home">
        <span className="rukh-brand-mark" aria-hidden="true">r</span>
        <span><strong>Rukh AI</strong><small>AI Coworker</small></span>
      </a>
      <nav className="rukh-product-switcher" aria-label="Workspace navigation">
        <a className="rukh-product-switch" href="/workspaces">All workspaces</a>
        <a className="rukh-product-switch" href="/editor">Web Editor</a>
        <ThemeToggle />
      </nav>
    </header>
    <div className="cw-preview-layout">
      <aside className="cw-preview-rail" aria-label="Workspace availability">
        <span className="cw-eyebrow">Your workspace</span>
        <strong>AI Coworker</strong>
        <p>Prepare your next brief here. Conversations and AI replies will be available after the service opens.</p>
        <a className="cw-secondary" href="/editor">Write in Web Editor</a>
      </aside>
      <main className="cw-preview-main" aria-labelledby="cw-preview-title">
        <div className="cw-preview-status" role="status"><strong>AI replies are unavailable in this deployment.</strong><span>You can draft and copy your brief. Nothing is sent to an AI service.</span></div>
        <section className="cw-preview-welcome">
          <span className="cw-eyebrow">A clear brief is a good beginning</span>
          <h1 id="cw-preview-title">What would you like to work on?</h1>
          <p>Start with your goal, add the context that matters, and describe the result you need.</p>
          {!draft && <div className="cw-preview-starters" aria-label="Brief starters">{starters.map(([label, value]) =>
            <button type="button" key={label} onClick={() => { setDraft(value); setNotice(""); input.current?.focus(); }}>{label}<span aria-hidden="true">↗</span></button>
          )}</div>}
        </section>
        <section className="cw-preview-composer" aria-label="Draft composer">
          <label htmlFor="cw-preview-draft">Your brief</label>
          <textarea ref={input} id="cw-preview-draft" dir="auto" rows={4} maxLength={20000} value={draft}
            aria-describedby="cw-preview-help" placeholder="Describe what you want to accomplish…"
            onChange={event => { setDraft(event.target.value); setNotice(""); }} />
          <div className="cw-preview-composer-footer"><span id="cw-preview-help">Draft only · Not saved after leaving this page</span>
            <button type="button" className="cw-primary" disabled={!draft.trim()} onClick={copyDraft}>Copy draft</button>
          </div>
          {notice && <p className="cw-preview-notice" role="status">{notice}</p>}
        </section>
      </main>
    </div>
  </div>;
}
