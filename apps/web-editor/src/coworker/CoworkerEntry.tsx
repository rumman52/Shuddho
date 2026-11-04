import { useRef, type FormEvent, type KeyboardEvent } from "react";

type CoworkerEntryProps = {
  authConfigured: boolean;
  loading: boolean;
  draft: string;
  error: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  onOpenSignIn: () => void;
};

const starters = [
  { label: "Research a topic", ariaLabel: "Start with a research brief", value: "Research this topic and summarize the key findings: " },
  { label: "Write a draft", ariaLabel: "Start with a writing draft", value: "Help me draft a clear, professional message about: " },
  { label: "Plan a task", ariaLabel: "Start with a plan", value: "Help me create a practical plan for: " },
  { label: "বাংলায় লিখুন", ariaLabel: "Start in Bangla", value: "বাংলায় আমাকে সাহায্য করুন: " },
];

export default function CoworkerEntry({
  authConfigured,
  loading,
  draft,
  error,
  onDraftChange,
  onSubmit,
  onOpenSignIn,
}: CoworkerEntryProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
      event.preventDefault();
      if (!loading && draft.trim()) formRef.current?.requestSubmit();
    }
  }

  return (
    <main className="rukh-entry" aria-label="Rukh AI Coworker">
      <div className="rukh-entry-inner">
        <div className="rukh-entry-intro">
          <span className="rukh-entry-eyebrow">YOUR AI COWORKER</span>
          <h1>What would you like to work on?</h1>
          <p>Start with a question, a draft, or an idea. Your first message opens a private conversation with Rukh.</p>
        </div>

        <form ref={formRef} className="rukh-entry-composer" aria-label="Start a conversation" onSubmit={submit}>
          <label className="rukh-entry-sr-only" htmlFor="rukh-first-message">Message Rukh AI</label>
          <textarea
            ref={composerRef}
            id="rukh-first-message"
            aria-label="Message Rukh AI"
            dir="auto"
            rows={4}
            maxLength={12000}
            value={draft}
            disabled={loading}
            placeholder="Ask Rukh to help you think, write, research, or plan…"
            onChange={event => onDraftChange(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <div className="rukh-entry-composer-footer">
            <span className="rukh-entry-hint" role="status" aria-live="polite">
              {loading
                ? "Checking your account…"
                : authConfigured
                  ? "Your draft stays here while you sign in. It is not sent yet."
                  : "Account access is not configured for this deployment."}
            </span>
            <button type="submit" aria-label="Continue to sign in" disabled={loading || !draft.trim()}>
              <span>Continue</span><span aria-hidden="true">↗</span>
            </button>
          </div>
        </form>

        <section className="rukh-entry-starters" aria-label="Prompt starters">
          <span className="rukh-entry-starters-label">Start with an idea</span>
          <div className="rukh-entry-starter-grid">
            {starters.map(starter => (
              <button
                key={starter.ariaLabel}
                type="button"
                aria-label={starter.ariaLabel}
                disabled={loading}
                onClick={() => {
                  onDraftChange(starter.value);
                  composerRef.current?.focus();
                }}
              >
                {starter.label}
              </button>
            ))}
          </div>
        </section>

        {error && <p className="rukh-entry-error" role="alert">{error}</p>}

        <footer className="rukh-entry-footer">
          <span>Messages are saved only after you sign in and send them.</span>
          {authConfigured
            ? <button type="button" className="rukh-entry-signin" onClick={onOpenSignIn} disabled={loading}>Sign in</button>
            : <span className="rukh-entry-signin-unavailable">Sign-in unavailable</span>}
        </footer>
      </div>
    </main>
  );
}
