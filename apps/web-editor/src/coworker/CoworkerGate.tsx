import { useEffect, useMemo, useState, type FormEvent } from "react";
import { type Session } from "@supabase/supabase-js";
import { getRukhAuthClient } from "@rukh/auth";
import CoworkerWorkspace from "./CoworkerWorkspace";
import { CoworkerClient } from "./client";


export default function CoworkerGate() {
  const auth = useMemo(() => getRukhAuthClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY), []);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(Boolean(auth));
  const [mode, setMode] = useState<"signin" | "signup" | "reset" | "recovery">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const client = useMemo(() => auth && session ? new CoworkerClient(
    import.meta.env.VITE_COWORKER_API_BASE_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "/backend"),
    async () => {
      const current = (await auth.auth.getSession()).data.session;
      return current?.user.id === session.user.id ? current.access_token : null;
    },
  ) : null, [auth, session?.user.id]);

  useEffect(() => {
    if (!auth) return;
    let alive = true;
    auth.auth.getSession().then(({ data, error: failure }) => {
      if (!alive) return;
      setSession(data.session); setLoading(false);
      if (failure) setError("Please sign in again to open your workspace.");
    }).catch(() => { if (alive) { setLoading(false); setError("Sign-in could not be reached. Please try again."); } });
    const { data } = auth.auth.onAuthStateChange((event, next) => {
      if (!alive) return;
      setSession(next); setLoading(false); setPassword("");
      if (event === "PASSWORD_RECOVERY") setMode("recovery");
    });
    return () => { alive = false; data.subscription.unsubscribe(); };
  }, [auth]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!auth || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      if (mode === "reset") {
        const { error } = await auth.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
        if (error) throw error;
        setNotice("Check your email for the password reset link.");
      } else if (mode === "recovery") {
        const { error } = await auth.auth.updateUser({ password });
        if (error) throw error;
        setMode("signin"); setPassword("");
      } else if (mode === "signup") {
        const { error, data } = await auth.auth.signUp({ email, password, options: { emailRedirectTo: window.location.origin } });
        if (error) throw error;
        if (!data.session) setNotice("Check your email to confirm your account, then sign in.");
      } else {
        const { error } = await auth.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Sign-in could not finish. Please try again."); }
    finally { setBusy(false); }
  }

  if (loading) return <p className="cw-loading" role="status">Opening your workspace…</p>;
  if (session && client && mode !== "recovery") return <CoworkerWorkspace key={session.user.id} client={client} email={session.user.email ?? "Your account"}
    signOut={async () => {
      const { error } = await auth!.auth.signOut({ scope: "local" });
      if (error) throw error;
      setSession(null); setNotice("");
    }} />;
  return <main className="cw-auth">
    <div className="cw-auth-story"><span className="cw-eyebrow">A coworker for complex work.</span>
      <h1>Move complex work<br />forward, with context.</h1>
      <p>Keep conversations, source material and Agent activity in one private workspace. Rukh helps you organize the work, prepare deliverables and review the next step.</p>
      <div className="cw-auth-output"><span>01</span><div><strong>Context that stays together</strong><p>Your brief, files and decisions stay connected.</p></div></div>
      <div className="cw-auth-output"><span>02</span><div><strong>Work you can review</strong><p>Track Agent progress and approve external actions.</p></div></div>
    </div>
    <section className="cw-auth-card" aria-label="Account access">
      {!auth ? <><h2>Sign-in is not configured for this environment.</h2><p>The Coworker account service is unavailable in this deployment. You can still open Web Editor or contact your workspace administrator.</p></> : <>
        <span className="cw-eyebrow">Your personal workspace</span>
        <h2>{mode === "signup" ? "Make room for better work." : mode === "reset" ? "Reset your password." : mode === "recovery" ? "Choose a new password." : "Welcome back."}</h2>
        <form onSubmit={submit}>
          {mode !== "recovery" && <label>Email<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={event => setEmail(event.target.value)} /></label>}
          {mode !== "reset" && <label>Password<input type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} minLength={mode === "signin" ? 1 : 12} required maxLength={128} value={password} onChange={event => setPassword(event.target.value)} />{mode !== "signin" && <small>Use at least 12 characters.</small>}</label>}
          <button className="cw-primary" disabled={busy} type="submit">{busy ? "Please wait…" : mode === "signup" ? "Create account" : mode === "reset" ? "Send reset link" : mode === "recovery" ? "Save password" : "Sign in"}</button>
        </form>
        {error && <p className="cw-error" role="alert">{error}</p>}{notice && <p className="cw-notice" role="status">{notice}</p>}
        {mode !== "recovery" && <div className="cw-auth-links">
          <button onClick={() => { setMode(mode === "signup" ? "signin" : "signup"); setError(""); setNotice(""); }}>{mode === "signup" ? "Already have an account? Sign in" : "Create an account"}</button>
          <button onClick={() => { setMode(mode === "reset" ? "signin" : "reset"); setError(""); setNotice(""); }}>{mode === "reset" ? "Back to sign in" : "Forgot password?"}</button>
        </div>}
      </>}
    </section>
  </main>;
}
