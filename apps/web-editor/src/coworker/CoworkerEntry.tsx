import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import CoworkerWelcome, { RukhCompanionMark } from "./CoworkerWelcome";
import NavigationIcon from "./WorkspaceNavigationIcon";
import ThemeToggle from "../components/ThemeToggle";

type CoworkerEntryProps = {
  authConfigured: boolean;
  loading: boolean;
  draft: string;
  error: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  onOpenSignIn: () => void;
  workspaceIntent?: "coworker" | "fly" | "projects";
};

export default function CoworkerEntry({ authConfigured, loading, draft, error, onDraftChange, onSubmit, onOpenSignIn, workspaceIntent = "coworker" }: CoworkerEntryProps) {
  const flyIntent = workspaceIntent === "fly";
  const projectsIntent = workspaceIntent === "projects";
  const formRef = useRef<HTMLFormElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);

  useEffect(() => {
    if (!navigationOpen || typeof document === "undefined") return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(drawerRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])') ?? []);
    focusable()[0]?.focus();
    function keydown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); setNavigationOpen(false); }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1)?.focus(); }
      else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0]?.focus(); }
    }
    document.addEventListener("keydown", keydown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", keydown);
      menuRef.current?.focus();
    };
  }, [navigationOpen]);

  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); onSubmit(); }
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
      event.preventDefault();
      if (!loading && draft.trim()) formRef.current?.requestSubmit();
    }
  }
  function newChat() { onDraftChange(""); setNavigationOpen(false); composerRef.current?.focus(); }
  function accountAccess() { setNavigationOpen(false); onOpenSignIn(); }
  function projectsAccess() {
    setNavigationOpen(false);
    if (typeof window !== "undefined" && window.history?.replaceState) {
      const destination = new URL("/coworker", window.location.origin);
      destination.searchParams.set("view", "projects");
      window.history.replaceState({}, "", destination.pathname + destination.search);
    }
    onOpenSignIn();
  }
  function starter(prompt: string) { onDraftChange(prompt); composerRef.current?.focus(); }

  return <main className="rukh-entry rukh-design-entry" aria-label={flyIntent ? "Rukh AI Fly" : projectsIntent ? "Rukh AI Projects" : "Rukh AI Coworker"}>
    {navigationOpen && <button type="button" className="rukh-design-backdrop" aria-label="Close navigation" onClick={() => setNavigationOpen(false)} />}
    <aside ref={drawerRef} id="rukh-entry-navigation" className={"rukh-design-sidebar" + (navigationOpen ? " is-open" : "")}
      role={navigationOpen ? "dialog" : undefined} aria-modal={navigationOpen ? true : undefined} aria-label="Workspace navigation">
      <a href="/coworker" className="rukh-design-brand" aria-label="Rukh AI Coworker home"><RukhCompanionMark /><strong>rukh<sup>AI</sup></strong></a>
      <button type="button" className="rukh-design-new" aria-label="New chat" onClick={newChat}>+ New chat</button>
      <nav aria-label="Primary workspace navigation">
        <a href="/coworker" className={"rukh-design-nav-link" + (!flyIntent && !projectsIntent ? " is-active" : "")} aria-current={!flyIntent && !projectsIntent ? "page" : undefined}><NavigationIcon name="chat" />Coworker</a>
        <a href="/fly" className={"rukh-design-nav-link" + (flyIntent ? " is-active" : "")} aria-current={flyIntent ? "page" : undefined}><NavigationIcon name="terminal" />Fly</a>
        <a href="/writing" className="rukh-design-nav-link"><NavigationIcon name="file-text" />Writing Assistant</a>
        <button type="button" className={"rukh-design-nav-link" + (projectsIntent ? " is-active" : "")} aria-current={projectsIntent ? "page" : undefined} onClick={projectsAccess} disabled={loading} title="Sign in to open Projects"><NavigationIcon name="folder" />Projects</button>
        <button type="button" className="rukh-design-nav-link" onClick={accountAccess}><NavigationIcon name="grid" />Plugins</button>
      </nav>
      <nav className="rukh-design-workspace-links" aria-label="Workspace tools">
        <span className="rukh-design-section-label">WORKSPACE</span>
        {[["file-text", "Files"], ["target", "Goals"], ["clock", "Automations"]].map(([icon, label]) => <button key={label} type="button" className="rukh-design-nav-link" onClick={accountAccess}><NavigationIcon name={icon} />{label}</button>)}
      </nav>
      <a className="rukh-design-directory" href="/workspaces">All workspaces</a>
      <section className="rukh-design-history" aria-label="Recent chats"><span className="rukh-design-section-label">RECENT CHATS</span><p>Sign in to see your conversations.</p></section>
      <div className="rukh-design-account"><button type="button" aria-label="Sign in" onClick={accountAccess} disabled={loading}><span className="rukh-design-account-avatar">R</span><span><strong>Sign in</strong><small>Your personal workspace</small></span></button><ThemeToggle /></div>
    </aside>
    <section className="rukh-design-main" aria-hidden={navigationOpen ? true : undefined}>
      <header className="rukh-design-header">
        <button ref={menuRef} type="button" className="rukh-design-menu" aria-label="Open navigation" aria-controls="rukh-entry-navigation" aria-expanded={navigationOpen} onClick={() => setNavigationOpen(true)}><NavigationIcon name="menu" /></button>
        <strong>{flyIntent ? "Fly" : projectsIntent ? "Projects" : "Coworker"}</strong>
        <button type="button" className="rukh-design-context" onClick={onOpenSignIn} aria-label="Activity and context"><span>Activity &amp; context</span><NavigationIcon name="sliders" /></button>
      </header>
      <div className="rukh-entry-inner">
        {flyIntent ? <section className="rukh-fly-entry-welcome" aria-labelledby="rukh-fly-entry-title">
          <span className="rukh-fly-entry-kicker">RUKH AI / FLY</span>
          <h1 id="rukh-fly-entry-title">Build, run and review code.</h1>
          <p>Open a focused development workspace for source files, supported execution, isolated HTML previews and Rukh code review.</p>
          {error && <p className="rukh-entry-error" role="alert">{error}</p>}
          <button type="button" className="rukh-fly-entry-primary" onClick={onOpenSignIn} disabled={loading}>Sign in to open Fly</button>
          <p className="rukh-entry-hint" role="status">{loading ? "Checking your account…" : authConfigured ? "Sign in to open your private coding workspace." : "Account access is not configured for this deployment."}</p>
        </section> : projectsIntent ? <section className="rukh-project-entry" aria-labelledby="rukh-project-entry-title">
          <div className="rukh-project-entry-mark"><NavigationIcon name="folder" /></div>
          <span className="rukh-welcome-badge">PROJECT WORKSPACE</span>
          <h1 id="rukh-project-entry-title">Your projects, ready when you are.</h1>
          <p>Sign in to create projects and keep their conversations, instructions and files together.</p>
          {error && <p className="rukh-entry-error" role="alert">{error}</p>}
          <button type="button" className="rukh-project-entry-primary" onClick={onOpenSignIn} disabled={loading}>Sign in to open Projects</button>
          <p className="rukh-entry-hint" role="status">{loading ? "Checking your account…" : authConfigured ? "Sign in to access your saved projects." : "Account access is not configured for this deployment."}</p>
        </section> : <>
          <CoworkerWelcome disabled={loading} onChoose={starter} />
          <div className="rukh-entry-bottom">
            {error && <p className="rukh-entry-error" role="alert">{error}</p>}
            <form ref={formRef} className="rukh-entry-composer" aria-label="Start a conversation" onSubmit={submit}>
              <label className="rukh-entry-sr-only" htmlFor="rukh-first-message">Message Rukh AI</label>
              <textarea ref={composerRef} id="rukh-first-message" aria-label="Message Rukh AI" dir="auto" rows={2} maxLength={12000} value={draft} disabled={loading} placeholder="Ask Rukh to do something…" onChange={event => onDraftChange(event.target.value)} onKeyDown={handleKeyDown} />
              <div className="rukh-entry-composer-footer">
                <button type="button" className="rukh-entry-attach" aria-label="Attach files" onClick={onOpenSignIn} disabled={loading}><NavigationIcon name="plus" /><span>Attach files</span></button>
                <button type="button" className="rukh-entry-tools" onClick={onOpenSignIn} disabled={loading}>Tools <span aria-hidden="true">›</span></button>
                <button className="rukh-entry-send" type="submit" aria-label="Continue to sign in" disabled={loading || !draft.trim()}><NavigationIcon name="arrow" /></button>
              </div>
            </form>
            <p className="rukh-entry-hint" role="status" aria-live="polite">{loading ? "Checking your account…" : authConfigured ? "Sign in to send. Rukh asks before taking important actions." : "Account access is not configured for this deployment."}</p>
          </div>
        </>}
      </div>
    </section>
  </main>;
}
