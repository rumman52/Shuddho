import { useEffect, useMemo, useState, type FormEvent } from "react";
import { type Session } from "@supabase/supabase-js";
import { getRukhAuthClient } from "@rukh/auth";
import { RukhCompanionMark } from "./CoworkerWelcome";
import CoworkerEntry from "./CoworkerEntry";
import CoworkerWorkspace from "./CoworkerWorkspace";
import { CoworkerClient } from "./client";

const ENTRY_DRAFT_STORAGE_KEY = "rukh-coworker-entry-draft:v1";

export type CoworkerGateProps = {
  authClientFactory?: typeof getRukhAuthClient;
};

export default function CoworkerGate({ authClientFactory = getRukhAuthClient }: CoworkerGateProps = {}) {
  const auth = useMemo(
    () => authClientFactory(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY),
    [authClientFactory],
  );
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(Boolean(auth));
  const [mode, setMode] = useState<"signin" | "signup" | "reset" | "recovery">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState(() => {
    try { return typeof window === "undefined" ? "" : window.sessionStorage.getItem(ENTRY_DRAFT_STORAGE_KEY) ?? ""; }
    catch { return ""; }
  });
  const [entryError, setEntryError] = useState("");
  const [authOpen, setAuthOpen] = useState(false);
  const currentPath = typeof window === "undefined" ? "/" : String(window.location?.pathname ?? "/");
  const currentSearch = typeof window === "undefined" ? "" : String(window.location?.search ?? "");
  const flyIntent = currentPath.replace(/\/+$/, "") === "/fly";
  const projectsIntent = !flyIntent && new URLSearchParams(currentSearch).get("view") === "projects";
  const authReturnUrl = () => {
    const destination = new URL(flyIntent ? "/fly" : "/coworker", window.location.origin);
    if (!flyIntent && new URLSearchParams(window.location.search ?? "").get("view") === "projects") {
      destination.searchParams.set("view", "projects");
    }
    return destination.href;
  };

  const client = useMemo(() => auth && session ? new CoworkerClient(
    import.meta.env.VITE_COWORKER_API_BASE_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "/backend"),
    async () => {
      const current = (await auth.auth.getSession()).data.session;
      return current?.user.id === session.user.id ? current.access_token : null;
    },
  ) : null, [auth, session?.user.id]);

  useEffect(() => {
    if (!auth) {
      setLoading(false);
      return;
    }
    let alive = true;
    auth.auth.getSession().then(({ data, error: failure }) => {
      if (!alive) return;
      setSession(data.session);
      setLoading(false);
      if (failure) setEntryError("Please sign in again to open your workspace.");
    }).catch(() => {
      if (alive) {
        setLoading(false);
        setEntryError("Sign-in could not be reached. Please try again.");
      }
    });
    const { data } = auth.auth.onAuthStateChange((event, next) => {
      if (!alive) return;
      setSession(next);
      setLoading(false);
      setPassword("");
      if (event === "PASSWORD_RECOVERY") {
        setMode("recovery");
        setAuthOpen(true);
      } else if (next) {
        setAuthOpen(false);
        setError("");
        setNotice("");
        setEntryError("");
      }
    });
    return () => { alive = false; data.subscription.unsubscribe(); };
  }, [auth]);

  // A Projects deep link must never silently fall back to the Coworker landing
  // screen. Wait for session restoration, then request authentication while
  // retaining ?view=projects for the post-login workspace.
  useEffect(() => {
    if (!loading && auth && !session && projectsIntent && mode !== "recovery") {
      setAuthOpen(true);
    }
  }, [auth, loading, session?.user.id, projectsIntent, mode]);

  useEffect(() => {
    try {
      if (draft) window.sessionStorage.setItem(ENTRY_DRAFT_STORAGE_KEY, draft);
      else window.sessionStorage.removeItem(ENTRY_DRAFT_STORAGE_KEY);
    } catch { /* Session storage is optional; the in-memory draft remains available. */ }
  }, [draft]);

  function openAuth() {
    if (!auth) {
      setEntryError("Sign-in is not configured for this deployment. Your draft has not been sent.");
      return;
    }
    setEntryError("");
    setError("");
    setNotice("");
    if (mode !== "recovery") setMode("signin");
    setAuthOpen(true);
  }

  function requestFirstMessage() {
    if (!draft.trim() || loading) return;
    if (!auth) {
      setEntryError("Sign-in is not configured for this deployment. Your draft has not been sent.");
      return;
    }
    setEntryError("");
    setError("");
    setNotice("");
    setMode("signin");
    setAuthOpen(true);
  }

  function closeAuth() {
    if (projectsIntent && typeof window !== "undefined" && window.history?.replaceState) {
      window.history.replaceState({}, "", "/coworker");
    }
    setAuthOpen(false);
    setPassword("");
    setShowPassword(false);
    setError("");
    setNotice("");
    if (mode !== "recovery") setMode("signin");
  }

  async function signInWithGoogle() {
    if (!auth || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const { error } = await auth.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: authReturnUrl() },
      });
      if (error) throw error;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Google sign-in could not start. Please use email instead.");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!auth || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "reset") {
        const { error } = await auth.auth.resetPasswordForEmail(email, { redirectTo: authReturnUrl() });
        if (error) throw error;
        setNotice("Check your email for the password reset link.");
      } else if (mode === "recovery") {
        const { error } = await auth.auth.updateUser({ password });
        if (error) throw error;
        setMode("signin");
        setPassword("");
        setAuthOpen(false);
      } else if (mode === "signup") {
        const { error, data } = await auth.auth.signUp({ email, password, options: { emailRedirectTo: authReturnUrl() } });
        if (error) throw error;
        if (!data.session) setNotice("Check your email to confirm your account, then sign in.");
      } else {
        const { error } = await auth.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Sign-in could not finish. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (session && client && mode !== "recovery") {
    return (
      <CoworkerWorkspace
        key={session.user.id}
        client={client}
        email={session.user.email ?? "Your account"}
        initialDraft={draft}
        onInitialDraftChange={setDraft}
        signOut={async () => {
          const { error } = await auth!.auth.signOut({ scope: "local" });
          if (error) throw error;
          setSession(null);
          setNotice("");
          setEntryError("");
          setAuthOpen(false);
        }}
      />
    );
  }

  if (authOpen && auth) {
    return (
      <main className="rukh-login-page" aria-label="Rukh AI sign in">
        <aside className="rukh-login-story">
          <div className="rukh-login-brand"><RukhCompanionMark /><strong>rukh AI</strong></div>
          <div className="rukh-login-story-copy">
            <h1>A little less busy.<br />A lot more possible.</h1>
            <p>Your ideas, your projects, your AI coworker. One calm place to move things forward.</p>
            <section>
              <h2>One conversation. Real progress.</h2>
              <p>Start with a message. Rukh helps you plan, create, and follow through — with you in control.</p>
            </section>
          </div>
          <p className="rukh-login-story-footer">Designed around the way you work.</p>
        </aside>
        <section className="rukh-login-form-panel">
          {mode !== "recovery" && <button type="button" className="rukh-login-back" onClick={closeAuth}>← Back to {flyIntent ? "Fly" : projectsIntent ? "Projects" : "Coworker"}</button>}
          <div className="rukh-login-form-content">
            <h2 id="rukh-login-title">
              {mode === "signup" ? "Create your account" : mode === "reset" ? "Reset your password" : mode === "recovery" ? "Choose a new password" : "Welcome back"}
            </h2>
            <p id="rukh-login-description">
              {mode === "signup" ? (flyIntent ? "Create an account to open Fly." : projectsIntent ? "Create an account to open Projects." : "Create an account to open your personal AI workspace.") : mode === "reset" ? "Enter your email and we will send you a password reset link." : mode === "recovery" ? "Choose a new password for your Rukh account." : (flyIntent ? "Sign in to open Fly." : projectsIntent ? "Sign in to open Projects." : "Sign in to your AI coworker.")}
            </p>
            {mode === "signin" && (
              <>
                <button type="button" className="rukh-login-google" disabled={busy} onClick={() => void signInWithGoogle()}>
                  <svg className="rukh-google-mark" viewBox="0 0 48 48" aria-hidden="true"><path fill="#4285F4" d="M43.6 24.5c0-1.4-.1-2.7-.4-4H24v7.5h11a9.4 9.4 0 0 1-4.1 6.2v5h6.6c3.9-3.6 6.1-8.9 6.1-14.7Z"/><path fill="#34A853" d="M24 44c5.5 0 10.1-1.8 13.5-4.8l-6.6-5c-1.8 1.2-4 2-6.9 2-5.3 0-9.8-3.6-11.4-8.4H5.8v5.2C9.2 39.6 16 44 24 44Z"/><path fill="#FBBC05" d="M12.6 27.8a12 12 0 0 1 0-7.6V15H5.8a20 20 0 0 0 0 18l6.8-5.2Z"/><path fill="#EA4335" d="M24 11.8c3 0 5.6 1 7.7 3l5.8-5.8C34 5.7 29.5 4 24 4 16 4 9.2 8.4 5.8 15l6.8 5.2c1.6-4.8 6.1-8.4 11.4-8.4Z"/></svg> Continue with Google
                </button>
                <div className="rukh-login-divider"><span>or use email</span></div>
              </>
            )}
            <form aria-label="Account access" aria-describedby="rukh-login-description" onSubmit={submit}>
              {mode !== "recovery" && (
                <label htmlFor="rukh-login-email">Email address
                  <input id="rukh-login-email" type="email" autoComplete="email" placeholder="you@example.com" required maxLength={254} value={email} onChange={event => setEmail(event.target.value)} autoFocus />
                </label>
              )}
              {mode !== "reset" && (
                <div className="rukh-login-password-group">
                  <label htmlFor="rukh-login-password">Password</label>
                  <span className="rukh-login-password-field">
                    <input id="rukh-login-password" type={showPassword ? "text" : "password"} autoComplete={mode === "signin" ? "current-password" : "new-password"} placeholder={mode === "signin" ? "Enter your password" : "Choose a password"} minLength={mode === "signin" ? 1 : 12} required maxLength={128} value={password} onChange={event => setPassword(event.target.value)} />
                    <button type="button" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword(value => !value)}>{showPassword ? "Hide" : "Show"}</button>
                  </span>
                  {mode !== "signin" && <small>Use at least 12 characters.</small>}
                </div>
              )}
              <button className="cw-primary rukh-login-submit" aria-label={mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : mode === "reset" ? "Send reset link" : "Save password"} disabled={busy} type="submit">
                {busy ? "Please wait…" : mode === "signup" ? "Create account" : mode === "reset" ? "Send reset link" : mode === "recovery" ? "Save password" : "Sign in →"}
              </button>
            </form>
            {error && <p className="cw-error" role="alert">{error}</p>}
            {notice && <p className="cw-notice" role="status">{notice}</p>}
            {mode !== "recovery" && (
              <div className="rukh-login-links">
                <button type="button" onClick={() => { setMode(mode === "signup" ? "signin" : "signup"); setError(""); setNotice(""); }}>
                  {mode === "signup" ? "Already have an account? Sign in" : "New here? Create an account"}
                </button>
                <button type="button" onClick={() => { setMode(mode === "reset" ? "signin" : "reset"); setError(""); setNotice(""); }}>
                  {mode === "reset" ? "Back to sign in" : "Forgot password?"}
                </button>
              </div>
            )}
            <p className="rukh-login-legal">By continuing, you agree to our Terms and Privacy Policy.</p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <CoworkerEntry
      authConfigured={Boolean(auth)}
      loading={loading}
      draft={draft}
      error={entryError}
      onDraftChange={value => { setDraft(value); setEntryError(""); }}
      onSubmit={requestFirstMessage}
      onOpenSignIn={openAuth}
      workspaceIntent={flyIntent ? "fly" : projectsIntent ? "projects" : "coworker"}
    />
  );
}
