import { useEffect, useRef, useState, type FormEvent } from "react";
import type { BrowserCommand, BrowserFormField, BrowserSession, CoworkerClient } from "./client";

const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Browser workspace action failed.";

export default function BrowserWorkspace({ client }: { client: CoworkerClient }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [sessions, setSessions] = useState<BrowserSession[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<BrowserSession | null>(null);
  const [commands, setCommands] = useState<BrowserCommand[]>([]);
  const [purpose, setPurpose] = useState<"research" | "form_prepare">("research");
  const [startUrl, setStartUrl] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [fields, setFields] = useState<BrowserFormField[]>([{ by: "label", field: "", value: "" }]);
  const [takeoverReason, setTakeoverReason] = useState<"login" | "mfa" | "captcha" | "sensitive_input">("login");
  const [takeoverBy, setTakeoverBy] = useState<"label" | "name">("label");
  const [takeoverField, setTakeoverField] = useState("");
  const [takeoverValue, setTakeoverValue] = useState("");
  const [takeoverSubmit, setTakeoverSubmit] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const createKey = useRef("");

  async function load(signal?: AbortSignal) {
    const result = await client.browserSessions(signal);
    setEnabled(result.enabled);
    setSessions(result.sessions);
    setSelectedId(current => current && result.sessions.some(item => item.id === current) ? current : result.sessions[0]?.id ?? "");
  }

  async function loadSelected(id: string, signal?: AbortSignal) {
    const [session, history] = await Promise.all([
      client.browserSession(id, signal),
      client.browserCommands(id, signal),
    ]);
    setSelected(session);
    setCommands(history.commands);
    setTargetUrl(session.last_url || session.start_url);
  }

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!selectedId) { setSelected(null); setCommands([]); return; }
    const controller = new AbortController();
    loadSelected(selectedId, controller.signal).catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, [client, selectedId]);

  useEffect(() => {
    if (!selectedId || !selected || !["queued", "running"].includes(selected.state)) return;
    const timer = window.setInterval(() => {
      void loadSelected(selectedId).catch(error => setError(errorMessage(error)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [client, selectedId, selected?.state]);

  async function createSession(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy("create"); setError(""); setNotice("");
    if (!createKey.current) createKey.current = crypto.randomUUID();
    try {
      const session = await client.createBrowserSession(purpose, startUrl, createKey.current);
      createKey.current = "";
      setSessions(previous => [session, ...previous.filter(item => item.id !== session.id)]);
      setSelectedId(session.id);
      setSelected(session);
      setTargetUrl(session.start_url);
      setNotice("Supervised browser session prepared. No page action is consequential by itself.");
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(""); }
  }

  async function act(label: string, operation: () => Promise<unknown>, message: string) {
    if (busy) return;
    setBusy(label); setError(""); setNotice("");
    try {
      await operation();
      if (selectedId) await loadSelected(selectedId);
      await load();
      setNotice(message);
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(""); }
  }

  async function navigate(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    await act("navigate", () => client.navigateBrowser(selected.id, targetUrl), "Navigation command prepared for the isolated browser worker.");
  }

  async function prepareForm(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const clean = fields.filter(item => item.field.trim());
    if (!clean.length) { setError("Add at least one form field."); return; }
    await act("form", () => client.prepareBrowserForm(selected.id, targetUrl, clean), "Form fields prepared without submitting the form.");
  }

  async function startTakeover() {
    if (!selected) return;
    await act("takeover", () => client.requestBrowserTakeover(selected.id, takeoverReason), "Browser execution paused for supervised user takeover.");
  }

  async function submitTakeoverInput(event: FormEvent) {
    event.preventDefault();
    if (!selected || !takeoverField.trim() || !takeoverValue) return;
    if (busy) return;
    setBusy("takeover-input"); setError(""); setNotice("");
    try {
      await client.prepareBrowserTakeoverInput(selected.id, {
        by: takeoverBy,
        field: takeoverField.trim(),
        value: takeoverValue,
        submit: takeoverSubmit,
      });
      setTakeoverValue("");
      await loadSelected(selected.id);
      await load();
      setNotice("Sensitive input was sealed for the isolated browser worker and is not stored in command history.");
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(""); }
  }

  function updateField(index: number, patch: Partial<BrowserFormField>) {
    setFields(previous => previous.map((field, current) => current === index ? { ...field, ...patch } : field));
  }

  return <section className="cw-service-workspace" aria-label="Supervised browser">
    <div className="cw-card-title">
      <span className="cw-step-number">07</span>
      <div><h2>Supervised browser</h2><p>Navigate and prepare ordinary form fields inside the isolated browser boundary.</p></div>
    </div>
    {error && <p className="cw-error" role="alert">{error}</p>}
    {notice && <p className="cw-notice" role="status">{notice}</p>}
    {enabled === false ? <div className="cw-agent-run"><strong>Browser capability is disabled.</strong><p className="cw-fineprint">The production-safe default remains off until controlled browser staging and recovery evidence are complete.</p></div> :
    <div className="cw-layout">
      <section className="cw-compose">
        <form onSubmit={createSession}>
          <label>Purpose<select value={purpose} onChange={event => { setPurpose(event.target.value as "research" | "form_prepare"); createKey.current = ""; }}>
            <option value="research">Research / navigation</option><option value="form_prepare">Form preparation</option>
          </select></label>
          <label>Start URL<input type="url" required value={startUrl} onChange={event => { setStartUrl(event.target.value); createKey.current = ""; }} /></label>
          <button className="cw-primary" type="submit" disabled={Boolean(busy)}>{busy === "create" ? "Preparing…" : "Start supervised session"}<span aria-hidden="true">↗</span></button>
          <p className="cw-fineprint">Only clean HTTPS targets are accepted. Internal addresses, direct IPs, arbitrary scripts and downloads remain blocked.</p>
        </form>

        {selected && <div className="cw-agent-run">
          <strong>Selected session</strong>
          <div className="cw-agent-meta"><span>{selected.state}</span><span>{selected.purpose}</span><span>expires {new Date(selected.expires_at).toLocaleTimeString()}</span><span>{selected.execution.authenticated_state_available ? "session continuity protected" : "no authenticated state saved"}</span></div>
          <p><bdi>{selected.last_title || selected.last_url || selected.start_url}</bdi></p>
          <p className="cw-fineprint">Browser cookies and local storage are kept server-side in encrypted, owner-bound session state. They are never shown in this workspace and are destroyed when the session is cancelled or expires.</p>
          {selected.takeover_required ? <div>
            <p className="cw-fineprint">Takeover reason: {selected.takeover_reason || "sensitive input"}. Secrets entered below are sent only to the authenticated backend, encrypted at rest, delivered to the isolated browser worker, and omitted from browser history.</p>
            {selected.takeover_reason === "captcha" ? <p className="cw-fineprint">CAPTCHA still requires a future interactive browser surface. Secret injection is intentionally unavailable for CAPTCHA challenges.</p> :
            <form onSubmit={submitTakeoverInput}>
              <label>Find sensitive field by<select value={takeoverBy} onChange={event => setTakeoverBy(event.target.value as "label" | "name")}><option value="label">Exact label</option><option value="name">Exact name attribute</option></select></label>
              <label>Field identifier<input maxLength={160} required value={takeoverField} onChange={event => setTakeoverField(event.target.value)} /></label>
              <label>Sensitive value<input type="password" autoComplete="off" maxLength={1000} required value={takeoverValue} onChange={event => setTakeoverValue(event.target.value)} /></label>
              <label><input type="checkbox" checked={takeoverSubmit} onChange={event => setTakeoverSubmit(event.target.checked)} /> Submit authentication form after filling</label>
              <button className="cw-secondary" type="submit" disabled={Boolean(busy)}>{busy === "takeover-input" ? "Sending securely…" : "Send sensitive input"}</button>
            </form>}
            <button className="cw-secondary" disabled={Boolean(busy)} onClick={() => act("resume", () => client.resumeBrowser(selected.id), "Session resumed without sending sensitive input.")}>Resume without input</button>
            <button className="cw-text-button" disabled={Boolean(busy)} onClick={() => act("cancel", () => client.cancelBrowser(selected.id), "Browser session cancelled.")}>Cancel session</button>
          </div> :
          !["cancelled", "completed", "expired", "failed"].includes(selected.state) && <div>
            <label>Takeover reason<select value={takeoverReason} onChange={event => setTakeoverReason(event.target.value as typeof takeoverReason)}>
              <option value="login">Login / password</option><option value="mfa">MFA / OTP</option><option value="sensitive_input">Other sensitive input</option><option value="captcha">CAPTCHA</option>
            </select></label>
            <button className="cw-secondary" disabled={Boolean(busy)} onClick={() => void startTakeover()}>Request takeover</button>
            <button className="cw-text-button" disabled={Boolean(busy)} onClick={() => act("cancel", () => client.cancelBrowser(selected.id), "Browser session cancelled.")}>Cancel session</button>
          </div>}
        </div>}

        {selected && !["cancelled", "completed", "expired", "failed", "takeover"].includes(selected.state) && <form onSubmit={navigate}>
          <label>Navigate within approved origin<input type="url" required value={targetUrl} onChange={event => setTargetUrl(event.target.value)} /></label>
          <button className="cw-secondary" type="submit" disabled={Boolean(busy)}>Prepare navigation</button>
        </form>}

        {selected?.purpose === "form_prepare" && !["cancelled", "completed", "expired", "failed", "takeover"].includes(selected.state) && <form onSubmit={prepareForm}>
          <h3>Prepare fields</h3>
          <p className="cw-fineprint">This fills ordinary text fields only. Passwords, OTPs, payment fields and form submission require a separate supervised/approval path.</p>
          {fields.map((field, index) => <fieldset key={index}>
            <legend>Field {index + 1}</legend>
            <label>Find by<select value={field.by} onChange={event => updateField(index, { by: event.target.value as "label" | "name" })}><option value="label">Exact label</option><option value="name">Exact name attribute</option></select></label>
            <label>Field identifier<input maxLength={160} value={field.field} onChange={event => updateField(index, { field: event.target.value })} /></label>
            <label>Value<input maxLength={1000} value={field.value} onChange={event => updateField(index, { value: event.target.value })} /></label>
            {fields.length > 1 && <button type="button" className="cw-text-button" onClick={() => setFields(previous => previous.filter((_, current) => current !== index))}>Remove field</button>}
          </fieldset>)}
          {fields.length < 10 && <button type="button" className="cw-text-button" onClick={() => setFields(previous => [...previous, { by: "label", field: "", value: "" }])}>Add field</button>}
          <button className="cw-secondary" type="submit" disabled={Boolean(busy)}>Prepare form fields</button>
        </form>}
      </section>

      <div className="cw-output-column">
        <div className="cw-history-title"><h2>Browser sessions</h2><button className="cw-text-button" type="button" disabled={Boolean(busy)} onClick={() => void load().catch(error => setError(errorMessage(error)))}>Refresh</button></div>
        {sessions.length === 0 ? <section className="cw-empty"><h2>No browser session yet.</h2><p>Create a supervised session to navigate or prepare a form.</p></section> :
        <div className="cw-history"><ul>{sessions.map(item => <li key={item.id}><button type="button" aria-pressed={selectedId === item.id} onClick={() => setSelectedId(item.id)}><div><strong>{item.last_title || item.start_url}</strong><small>{item.purpose} · {item.state} · {new Date(item.created_at).toLocaleString()}</small></div></button></li>)}</ul></div>}

        {selected && <><div className="cw-history-title"><h2>Verified command history</h2></div>
        {commands.length === 0 ? <p className="cw-fineprint">No commands recorded for this session.</p> :
        <div className="cw-history"><ul>{commands.map(command => <li key={command.id}><div className="cw-agent-run">
          <strong>#{command.sequence} {command.kind}</strong>
          <div className="cw-agent-meta"><span>{command.state}</span><span>attempts {command.attempts}</span>{command.error_code && <span>{command.error_code}</span>}</div>
          <p><bdi>{command.result.title || command.result.final_url || command.target_url || "No visible result yet"}</bdi></p>
          {command.result.prepared_fields?.length ? <p className="cw-fineprint">Prepared fields: {command.result.prepared_fields.join(", ")}</p> : null}
        </div></li>)}</ul></div>}</>}
      </div>
    </div>}
  </section>;
}
