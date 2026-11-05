import { useEffect, useState, type FormEvent } from "react";
import { CoworkerClient } from "./client";
import ThemeToggle from "../components/ThemeToggle";
export default function SettingsWorkspace({ client, email }: { client: CoworkerClient; email: string }) {
  const [preferences, setPreferences] = useState<{ language: string; writing_goal: string; tone_goal: string; personal_dictionary: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    client.me(controller.signal).then(profile => { if (!controller.signal.aborted) setPreferences({ language: "bn", writing_goal: "general", tone_goal: "neutral", personal_dictionary: [], ...profile.preferences }); })
      .catch(error => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Settings could not be loaded."); });
    return () => controller.abort();
  }, [client]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (!preferences || busy) return; setBusy(true); setError(""); setNotice("");
    try { await client.savePreferences(preferences); setNotice("Preferences saved."); }
    catch (error) { setError(error instanceof Error ? error.message : "Preferences could not be saved."); }
    finally { setBusy(false); }
  }
  return <section className="rukh-designed-page" aria-label="Settings"><header className="rukh-page-heading"><div><h1>Make Rukh work for you.</h1><p>Manage your account preferences and appearance.</p></div></header>
    {error && <p className="cw-error" role="alert">{error}</p>}{notice && <p className="cw-notice" role="status">{notice}</p>}
    <section className="rukh-settings-card"><h2>Account</h2><p>{email}</p><h2>Appearance</h2><ThemeToggle /></section>
    <form className="rukh-settings-card" onSubmit={save}><h2>Writing preferences</h2>{preferences ? <>
      <label>Preferred language<select aria-label="Preferred language" disabled={busy} value={preferences.language} onChange={event => setPreferences({ ...preferences, language: event.target.value })}><option value="bn">বাংলা</option><option value="en">English</option><option value="ar">العربية</option>{!["bn", "en", "ar"].includes(preferences.language) && <option value={preferences.language}>{preferences.language}</option>}</select></label>
      <label>Writing goal<select aria-label="Writing goal" disabled={busy} value={preferences.writing_goal} onChange={event => setPreferences({ ...preferences, writing_goal: event.target.value })}>{["general", "formal", "academic", "business", "casual", "social"].map(value => <option value={value} key={value}>{value}</option>)}</select></label>
      <button className="cw-primary" disabled={busy}>{busy ? "Saving…" : "Save preferences"}</button></> : <p role="status">{error ? "Preferences unavailable." : "Loading preferences…"}</p>}</form>
  </section>;
}
