import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoworkerClient, type ActionInput, type Artifact, type ConnectedAccount, type EmailDraft, type ExternalAction } from "./client";
import { beginGoogleConnection, finishGoogleCallback } from "./googleCallback";
import { beginMicrosoftConnection, finishMicrosoftCallback } from "./microsoftCallback";

const labels: Record<ExternalAction["state"], string> = { awaiting_approval: "Needs your approval", queued: "Approved · queued", executing: "Executing", succeeded: "Confirmed", failed: "Not completed", cancelled: "Cancelled", expired: "Expired", outcome_unknown: "Result uncertain" };
const message = (error: unknown) => error instanceof Error ? error.message : "This action could not finish. Please try again.";
const recipients = (text: string) => text.split(/[;,\n]/).map(value => value.trim()).filter(Boolean);
const isEmail = (kind: ExternalAction["kind"]) => kind !== "calendar_create";
const title = (item: ExternalAction) => item.preview.payload.kind === "calendar_create" ? item.preview.payload.title : item.preview.payload.subject;

export default function ActionWorkspace({ client, account, emailDraft, focusActionId, onFocused }: { client: CoworkerClient; account: string; emailDraft: EmailDraft | null; focusActionId?: string | null; onFocused?: () => void }) {
  const [enabled, setEnabled] = useState(false);
  const [connections, setConnections] = useState<ConnectedAccount[]>([]);
  const [history, setHistory] = useState<ExternalAction[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [attachmentsEnabled, setAttachmentsEnabled] = useState(false);
  const [selectedAttachments, setSelectedAttachments] = useState<string[]>([]);
  const [action, setAction] = useState<ExternalAction | null>(null);
  const [mode, setMode] = useState<"email" | "calendar">("email");
  const microsoftEnabled = import.meta.env.VITE_MICROSOFT_ACTIONS_ENABLED === "true";
  const [provider, setProvider] = useState<"google" | "microsoft">("google");
  const [to, setTo] = useState(""); const [cc, setCc] = useState(""); const [bcc, setBcc] = useState("");
  const [subject, setSubject] = useState(emailDraft?.subject ?? ""); const [body, setBody] = useState(emailDraft?.body ?? "");
  const [eventTitle, setEventTitle] = useState(""); const [description, setDescription] = useState("");
  const [location, setLocation] = useState(""); const [attendees, setAttendees] = useState("");
  const [start, setStart] = useState(""); const [end, setEnd] = useState("");
  const [timeZone, setTimeZone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [checked, setChecked] = useState(false); const [busy, setBusy] = useState("");
  const [composing, setComposing] = useState(true);
  const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false); const [reload, setReload] = useState(0);
  const submission = useRef<{ fingerprint: string; key: string }>();
  const currentConnection = connections.find(
    value => value.provider === provider && value.capability === mode,
  );
  const pending = action?.state === "queued" || action?.state === "executing";

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    (async () => {
      const result = await finishGoogleCallback(client, account);
      const microsoftResult = microsoftEnabled
        ? await finishMicrosoftCallback(client, account)
        : null;
      if (alive && (result || microsoftResult)) setNotice(microsoftResult ?? result ?? "");
    })().catch(failure => { if (alive) setError(message(failure)); }).finally(() => {
      if (!alive) return;
      Promise.all([client.connections(controller.signal), client.actions(controller.signal), client.actionArtifacts(controller.signal)]).then(([value, recent, available]) => {
        if (!alive) return;
        setEnabled(value.enabled); setConnections(value.connections); setHistory(recent.actions);
        setAttachmentsEnabled(available.attachments_enabled); setArtifacts(available.artifacts); setLoaded(true);
      }).catch(failure => { if (alive) { setError(message(failure)); setLoaded(true); } });
    });
    return () => { alive = false; controller.abort(); };
  }, [client, account, reload]);

  useEffect(() => {
    if (!focusActionId) return;
    let alive = true;
    client.action(focusActionId).then(value => {
      if (!alive) return;
      openAction(value);
      onFocused?.();
    }).catch(failure => { if (alive) setError(message(failure)); });
    return () => { alive = false; };
  }, [client, focusActionId]);

  useEffect(() => {
    if (!action || !pending) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await client.action(action.id, controller.signal);
        if (controller.signal.aborted) return;
        setAction(result); setHistory(previous => [result, ...previous.filter(item => item.id !== result.id)]);
      } catch (failure) { if (!controller.signal.aborted) setError(message(failure)); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 2500);
    };
    timer = setTimeout(poll, 700);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [client, action?.id, pending]);

  async function run(name: string, operation: () => Promise<void>) {
    if (busy) return;
    setBusy(name); setError("");
    try { await operation(); } catch (failure) { setError(message(failure)); }
    finally { setBusy(""); }
  }

  function updateAction(value: ExternalAction) {
    setAction(value); setChecked(false);
    setHistory(previous => [value, ...previous.filter(item => item.id !== value.id)]);
  }

  function openAction(value: ExternalAction) {
    setComposing(false);
    updateAction(value);
  }

  function startNewAction(clearAttachments = true) {
    setComposing(true); setAction(null); setChecked(false); setError(""); submission.current = undefined;
    if (clearAttachments) setSelectedAttachments([]);
  }

  async function prepare(event: FormEvent) {
    event.preventDefault();
    if (!currentConnection) return;
    const attachmentIds = mode === "email" ? selectedAttachments : [];
    const input: ActionInput = { connection_id: currentConnection.id, attachment_ids: attachmentIds, payload: mode === "email" ?
      { kind: attachmentIds.length ? "email_send_with_attachments" : "email_send", to: recipients(to), cc: recipients(cc), bcc: recipients(bcc), subject, body } :
      { kind: "calendar_create", title: eventTitle, description, location, start_at: start, end_at: end, time_zone: timeZone, attendees: recipients(attendees) } };
    const fingerprint = JSON.stringify(input);
    if (submission.current?.fingerprint !== fingerprint) submission.current = { fingerprint, key: crypto.randomUUID() };
    await run("prepare", async () => openAction(await client.prepareAction(input, submission.current!.key)));
  }

  async function edit() {
    if (!action) return;
    await run("edit", async () => {
      if (action.state === "awaiting_approval") await client.cancelAction(action.id);
      const p = action.preview.payload;
      setProvider(action.preview.provider);
      if (p.kind !== "calendar_create") { setMode("email"); setTo(p.to.join(", ")); setCc(p.cc.join(", ")); setBcc(p.bcc.join(", ")); setSubject(p.subject); setBody(p.body); setSelectedAttachments((action.preview.attachments ?? []).map(item => item.id)); }
      else { setMode("calendar"); setSelectedAttachments([]); setEventTitle(p.title); setDescription(p.description); setLocation(p.location); setAttendees(p.attendees.join(", ")); setStart(p.start_at.slice(0, 16)); setEnd(p.end_at.slice(0, 16)); setTimeZone(p.time_zone); }
      startNewAction(false); setReload(x => x + 1);
    });
  }

  const payload = action?.preview.payload;
  return <section className="cw-actions" aria-label="Email and calendar actions">
    <div className="cw-action-intro"><div><span className="cw-eyebrow">Your final say</span><h2>From a good draft to done.</h2><p>Prepare an email or event, review the details, then approve the action.</p></div></div>
    {error && <p className="cw-error" role="alert">{error}</p>}{notice && <p className="cw-notice" role="status">{notice}</p>}
    {!loaded ? <p role="status">Loading connections…</p> : !enabled && <p className="cw-notice">New actions are not enabled in this workspace. Saved previews and receipts remain available.</p>}
    {microsoftEnabled && <label>Provider<select aria-label="Action provider" value={provider} onChange={event => setProvider(event.target.value as "google" | "microsoft")} disabled={Boolean(busy)}><option value="google">Google</option><option value="microsoft">Microsoft</option></select></label>}
    <div className="cw-connection-grid">{(["email", "calendar"] as const).map(capability => {
      const connected = connections.find(value => value.provider === provider && value.capability === capability);
      const google = provider === "google";
      const label = capability === "email" ? (google ? "Gmail" : "Outlook / Microsoft Mail") : (google ? "Google Calendar" : "Microsoft Calendar");
      const controlLabel = microsoftEnabled ? label : (capability === "email" ? "Gmail" : "Calendar");
      return <div className="cw-connection" key={provider + capability}><div><strong>{label}</strong><small>{connected?.email ?? (capability === "email" ? "Send emails you approve" : "Create events in your primary calendar")}</small></div>
        {connected ? <button className="cw-text-button" disabled={Boolean(busy)} onClick={() => {
          if (!window.confirm(`Disconnect ${connected.email} for ${capability}? Pending actions will be cancelled. An action already executing may still finish.`)) return;
          void run("disconnect", async () => { const result = await client.disconnect(connected.id); setNotice(result.message); setReload(x => x + 1); if (action) updateAction(await client.action(action.id)); });
        }}>Disconnect {controlLabel}</button> : <button className="cw-secondary" disabled={!enabled || Boolean(busy)} onClick={() => void run("connect", () => provider === "google" ? beginGoogleConnection(client, account, capability) : beginMicrosoftConnection(client, account, capability))}>Connect {controlLabel}</button>}
      </div>;
    })}</div>
    <p className="cw-fineprint">{provider === "google" ? <>Google permissions can also be removed in your <a href="https://myaccount.google.com/connections" target="_blank" rel="noreferrer">Google Account</a>.</> : <>Microsoft permissions can also be reviewed in your Microsoft account's app permissions.</>}</p>
    <div className="cw-layout"><div className="cw-compose cw-action-compose">
      <div className="cw-card-title"><span className="cw-step-number">01</span><div><h2>{composing ? "Prepare an action" : "Action details"}</h2><p>{composing ? "Nothing is sent when you prepare a preview." : "This preview is saved exactly as shown."}</p></div></div>
      {composing ? <form onSubmit={prepare}>
        <label>Action type<select aria-label="Action type" value={mode} onChange={event => setMode(event.target.value as "email" | "calendar")} disabled={Boolean(busy)}><option value="email">Send an email</option><option value="calendar">Create a calendar event</option></select></label>
        <p className="cw-action-account">{currentConnection ? <>From <strong>{currentConnection.email}</strong>{mode === "calendar" && " · Primary calendar"}</> : `Connect ${provider === "google" ? (mode === "email" ? "Gmail" : "Google Calendar") : (mode === "email" ? "Microsoft Mail" : "Microsoft Calendar")} above to continue.`}</p>
        {mode === "email" ? <>
          <label>To<input dir="ltr" value={to} onChange={event => setTo(event.target.value)} required maxLength={5100} placeholder="name@example.com" /></label>
          <div className="cw-action-row"><label>Cc<input dir="ltr" value={cc} onChange={event => setCc(event.target.value)} maxLength={5100} /></label><label>Bcc<input dir="ltr" value={bcc} onChange={event => setBcc(event.target.value)} maxLength={5100} /></label></div>
          <small>Use full email addresses, separated by commas. Up to 20 recipients in total.</small>
          <label>Subject<input dir="auto" value={subject} onChange={event => setSubject(event.target.value)} required maxLength={300} /></label>
          <label>Message<textarea dir="auto" rows={9} value={body} onChange={event => setBody(event.target.value)} required maxLength={20000} /></label>
          {attachmentsEnabled && artifacts.length > 0 && <fieldset className="cw-agent-files"><legend>Attach Shuddho artifacts (optional)</legend>
            {artifacts.filter(item => {
              const type = item.content_type.split(";", 1)[0].toLowerCase();
              return ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/plain"].includes(type);
            }).slice(0, 30).map(item => {
              const selected = selectedAttachments.includes(item.id);
              const selectedBytes = artifacts.filter(value => selectedAttachments.includes(value.id)).reduce((sum, value) => sum + value.byte_size, 0);
              const unavailable = !selected && (selectedAttachments.length >= 3 || selectedBytes + item.byte_size > 2 * 1024 * 1024);
              return <label key={item.id}><input type="checkbox" checked={selected} disabled={Boolean(busy) || unavailable}
                onChange={event => setSelectedAttachments(previous => event.target.checked ? [...previous, item.id] : previous.filter(id => id !== item.id))} />
                <span>{item.filename} · {(item.byte_size / 1024).toFixed(0)} KB · SHA {item.sha256.slice(0, 8)}{item.created_at ? ` · ${new Date(item.created_at).toLocaleDateString()}` : ""}</span></label>;
            })}
            <small>Up to 3 existing Shuddho artifacts, 2 MB total. The exact artifact hashes are bound to approval.</small>
          </fieldset>}
          <p className="cw-fineprint">Plain-text email, sent immediately after approval.{attachmentsEnabled ? " Attachments must already exist in this Shuddho workspace." : " Attachments are disabled in this deployment."}</p>
        </> : <>
          <label>Event title<input dir="auto" required maxLength={300} value={eventTitle} onChange={event => setEventTitle(event.target.value)} /></label>
          <div className="cw-action-row"><label>Starts<input type="datetime-local" required value={start} onChange={event => setStart(event.target.value)} /></label><label>Ends<input type="datetime-local" required value={end} onChange={event => setEnd(event.target.value)} /></label></div>
          <label>Time zone<input required maxLength={80} value={timeZone} onChange={event => setTimeZone(event.target.value)} placeholder="Asia/Dhaka" /></label>
          <small>Use an IANA time zone such as Asia/Dhaka, Asia/Kolkata or America/New_York.</small>
          <label>Guests<input dir="ltr" value={attendees} onChange={event => setAttendees(event.target.value)} maxLength={5100} placeholder="Optional email addresses, separated by commas" /></label>
          <label>Location<input dir="auto" value={location} onChange={event => setLocation(event.target.value)} maxLength={500} /></label>
          <label>Event description<textarea dir="auto" rows={4} value={description} onChange={event => setDescription(event.target.value)} maxLength={20000} /></label>
          <p className="cw-fineprint">A single event in your primary calendar. Invitations are sent to all listed guests, who can see each other. No reminder is added; no video link is requested.</p>
        </>}
        <button className="cw-primary" disabled={!enabled || !currentConnection || Boolean(busy)}>{busy === "prepare" ? "Preparing…" : "Review action"}<span aria-hidden="true">→</span></button>
      </form> : action ? <>
        <dl className="cw-action-details"><dt>Account</dt><dd><bdi>{action.preview.account}</bdi></dd>
          {payload && payload.kind !== "calendar_create" ? <><dt>To</dt><dd>{payload.to.join(", ")}</dd><dt>Cc</dt><dd>{payload.cc.join(", ") || "None"}</dd><dt>Bcc</dt><dd>{payload.bcc.join(", ") || "None"}</dd><dt>Attachments</dt><dd>{(action.preview.attachments ?? []).length ? (action.preview.attachments ?? []).map(item => item.filename).join(", ") : "None"}</dd><dt>Timing</dt><dd>Send immediately after approval</dd></> : payload?.kind === "calendar_create" && <>
            <dt>Calendar</dt><dd>Primary calendar</dd><dt>Starts</dt><dd>{payload.start_at.replace("T", " ")}</dd><dt>Ends</dt><dd>{payload.end_at.replace("T", " ")}</dd><dt>Time zone</dt><dd>{payload.time_zone}</dd><dt>Guests</dt><dd>{payload.attendees.join(", ") || "None"}</dd><dt>Invitations</dt><dd>Notify all listed guests; guests can see each other</dd><dt>Location</dt><dd dir="auto">{payload.location || "None"}</dd><dt>Reminders / video</dt><dd>None added</dd>
          </>}
        </dl>
        <div className="cw-action-content" dir="auto"><h3>{title(action)}</h3><p>{payload?.kind === "calendar_create" ? payload.description : payload?.body}</p></div>
        {action.state === "awaiting_approval" && <button type="button" className="cw-secondary" disabled={Boolean(busy)} onClick={() => void edit()}>Edit details</button>}
      </> : null}
    </div>
    <div className="cw-output-column"><section className="cw-result cw-action-review" aria-label="Action review">
      <span className="cw-eyebrow">02 · Review and approve</span><h2>{action ? labels[action.state] : "You stay in control."}</h2>
      {composing || !action ? <p>Your preview will appear here. Check the full message or event details before approving.</p> : <>
        <p role="status">{action.message}</p>
        {action.state === "awaiting_approval" && <>
          <p className="cw-fineprint">Preview expires {new Date(action.preview.expires_at).toLocaleTimeString()}. Approval starts execution within five minutes.</p>
          <label className="cw-approval-check"><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} />I reviewed the account, recipients, content and timing.</label>
          <button className="cw-primary" disabled={!checked || !enabled || Boolean(busy)} onClick={() => void run("approve", async () => updateAction(await client.approveAction(action)))}>{busy === "approve" ? "Approving…" : isEmail(action.kind) ? "Approve & send email" : "Approve & create event"}</button>
        </>}
        {["awaiting_approval", "queued"].includes(action.state) && <button className="cw-text-button cw-cancel" disabled={Boolean(busy)} onClick={() => void run("cancel", async () => updateAction(await client.cancelAction(action.id)))}>Cancel action</button>}
        {action.state === "outcome_unknown" && action.kind === "calendar_create" && action.preview.provider === "google" && <button className="cw-secondary" disabled={Boolean(busy) || !enabled} onClick={() => void run("reconcile", async () => updateAction(await client.reconcileAction(action.id)))}>{busy === "reconcile" ? "Checking calendar…" : "Check calendar result"}</button>}
        {action.receipt && <div className="cw-receipt"><strong>{action.preview.provider === "microsoft" ? (isEmail(action.kind) ? "Accepted by Microsoft Graph" : "Created in Microsoft Calendar") : (isEmail(action.kind) ? "Accepted by Gmail" : "Created in Google Calendar")}</strong><p>{action.preview.provider === "microsoft" ? (isEmail(action.kind) ? "This confirms Microsoft Graph accepted the send request. It does not confirm delivery or reading." : "Microsoft Graph confirmed the event. Guest attendance is not yet confirmed.") : (isEmail(action.kind) ? "This confirms Gmail accepted the message. It does not confirm delivery or that it was read." : "Google confirmed the event. Guest attendance is not yet confirmed.")}</p><small>{new Date(action.receipt.confirmed_at).toLocaleString()}</small>{action.receipt.provider_id && <code>Receipt: {action.receipt.provider_id}</code>}</div>}
        {action.audit && <details className="cw-action-audit"><summary>Action history</summary><ol>{action.audit.map((item, index) => <li key={index}>{item.action.replace("action.", "").replaceAll("_", " ")} · {new Date(item.created_at).toLocaleString()}</li>)}</ol></details>}
      </>}
    </section>
    <section className="cw-history"><div className="cw-history-title"><h2>Recent actions</h2><button className="cw-text-button" onClick={() => { setReload(x => x + 1); if (action) void run("refresh", async () => updateAction(await client.action(action.id))); }}>Refresh actions</button></div>
      {history.length ? <ul>{history.map(item => <li key={item.id}><button aria-pressed={action?.id === item.id} disabled={Boolean(busy)} onClick={() => void run("open", async () => openAction(await client.action(item.id)))}><div><strong dir="auto">{title(item)}</strong><small>{isEmail(item.kind) ? "Email" : "Calendar"} · {item.preview.account}</small></div><span className="cw-status">{labels[item.state]}</span></button></li>)}</ul> : <p className="cw-fineprint">Your approved actions and receipts will appear here.</p>}
      {!composing && action && <button type="button" className="cw-secondary cw-new-action" disabled={Boolean(busy)} onClick={() => startNewAction()}>Prepare another action</button>}
    </section></div></div>
  </section>;
}
