import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { type Session } from "@supabase/supabase-js";
import { getRukhAuthClient } from "@rukh/auth";
import { RukhCompanionMark } from "./CoworkerWelcome";
import CoworkerEntry from "./CoworkerEntry";
import CoworkerWorkspace from "./CoworkerWorkspace";
import { CoworkerClient } from "./client";

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState("");
  const [entryError, setEntryError] = useState("");
  const [authOpen, setAuthOpen] = useState(false);
  const authDialogRef = useRef<HTMLElement | null>(null);

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
    setAuthOpen(false);
    setPassword("");
    setError("");
    setNotice("");
    if (mode !== "recovery") setMode("signin");
  }

  useEffect(() => {
    if (!authOpen || typeof document === "undefined") return;
    const dialog = authDialogRef.current;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const getFocusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    ) ?? []);
    const first = dialog?.querySelector<HTMLElement>("input:not([disabled])") ?? getFocusable()[0];
    (first ?? dialog)?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeAuth();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = getFocusable();
      if (!focusable.length) {
        event.preventDefault();
        dialog?.focus();
        return;
      }
      const firstFocusable = focusable[0];
      const lastFocusable = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === firstFocusable) {
        event.preventDefault();
        lastFocusable.focus();
      } else if (!event.shiftKey && document.activeElement === lastFocusable) {
        event.preventDefault();
        firstFocusable.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousBodyOverflow;
      if (previous?.isConnected) previous.focus();
    };
  }, [authOpen, mode]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!auth || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "reset") {
        const { error } = await auth.auth.resetPasswordForEmail(email, { redirectTo: new URL("/coworker", window.location.origin).href });
        if (error) throw error;
        setNotice("Check your email for the password reset link.");
      } else if (mode === "recovery") {
        const { error } = await auth.auth.updateUser({ password });
        if (error) throw error;
        setMode("signin");
        setPassword("");
        setAuthOpen(false);
      } else if (mode === "signup") {
        const { error, data } = await auth.auth.signUp({ email, password, options: { emailRedirectTo: new URL("/coworker", window.location.origin).href } });
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

  return (
    <>
      <div aria-hidden={authOpen ? true : undefined}>
        <CoworkerEntry
          authConfigured={Boolean(auth)}
          loading={loading}
          draft={draft}
          error={entryError}
          onDraftChange={value => { setDraft(value); setEntryError(""); }}
          onSubmit={requestFirstMessage}
          onOpenSignIn={openAuth}
        />
      </div>

      {authOpen && auth && (
        <div
          className="rukh-auth-overlay"
          onMouseDown={event => { if (event.target === event.currentTarget) closeAuth(); }}
        >
          <section
            ref={authDialogRef}
            className="cw-auth-card rukh-auth-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rukh-auth-dialog-title"
            aria-describedby="rukh-auth-dialog-description"
            tabIndex={-1}
          >
            <button type="button" className="rukh-auth-dialog-close" aria-label="Close sign-in" onClick={closeAuth}>×</button>
            <aside className="rukh-auth-story"><RukhCompanionMark /><strong>rukh AI</strong><h2>A little less busy.<br />A lot more possible.</h2><p>Your ideas, your projects, your AI coworker. One calm place to move things forward.</p><div><h3>One conversation. Real progress.</h3><p>Start with a message. Rukh helps you plan, create, and follow through — with you in control.</p></div></aside>
            <div className="rukh-auth-form-content">
            <span className="cw-eyebrow">Your personal workspace</span>
            <h2 id="rukh-auth-dialog-title">
              {mode === "signup" ? "Make room for better work." : mode === "reset" ? "Reset your password." : mode === "recovery" ? "Choose a new password." : "Welcome back."}
            </h2>
            <p id="rukh-auth-dialog-description">Your draft stays in the composer. It will not be sent until you press Send in your conversation.</p>
            <form aria-label="Account access" onSubmit={submit}>
              {mode !== "recovery" && (
                <label>Email
                  <input type="email" autoComplete="email" required maxLength={254} value={email} onChange={event => setEmail(event.target.value)} />
                </label>
              )}
              {mode !== "reset" && (
                <label>Password
                  <input type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} minLength={mode === "signin" ? 1 : 12} required maxLength={128} value={password} onChange={event => setPassword(event.target.value)} />
                  {mode !== "signin" && <small>Use at least 12 characters.</small>}
                </label>
              )}
              <button className="cw-primary" disabled={busy} type="submit">
                {busy ? "Please wait…" : mode === "signup" ? "Create account" : mode === "reset" ? "Send reset link" : mode === "recovery" ? "Save password" : "Sign in"}
              </button>
            </form>
            {error && <p className="cw-error" role="alert">{error}</p>}
            {notice && <p className="cw-notice" role="status">{notice}</p>}
            {mode !== "recovery" && (
              <div className="cw-auth-links">
                <button type="button" onClick={() => { setMode(mode === "signup" ? "signin" : "signup"); setError(""); setNotice(""); }}>
                  {mode === "signup" ? "Already have an account? Sign in" : "Create an account"}
                </button>
                <button type="button" onClick={() => { setMode(mode === "reset" ? "signin" : "reset"); setError(""); setNotice(""); }}>
                  {mode === "reset" ? "Back to sign in" : "Forgot password?"}
                </button>
              </div>
            )}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
