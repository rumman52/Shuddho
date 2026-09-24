import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoworkerClient, WorkspaceError, type ActionInput, type ActionRecipient, type Artifact, type ConnectedAccount, type EmailDraft, type ExternalAction } from "./client";
import { beginGoogleConnection, finishGoogleCallback } from "./googleCallback";
import { beginMicrosoftConnection, finishMicrosoftCallback } from "./microsoftCallback";
import { beginLinkedInConnection, finishLinkedInCallback } from "./linkedinCallback";

const labels: Record<ExternalAction["state"], string> = { awaiting_approval: "Needs your approval", queued: "Approved · queued", executing: "Executing", succeeded: "Confirmed", failed: "Not completed", cancelled: "Cancelled", expired: "Expired", outcome_unknown: "Result uncertain" };
const message = (error: unknown) => error instanceof Error ? error.message : "This action could not finish. Please try again.";
const recipients = (text: string) => text.split(/[;,\n]/).map(value => value.trim()).filter(Boolean);
const isCalendar = (kind: ExternalAction["kind"]) => kind === "calendar_create" || kind === "calendar_create_with_reminder";
const isDocumentShare = (kind: ExternalAction["kind"]) => kind === "document_share";
const isEmail = (kind: ExternalAction["kind"]) => kind === "email_send" || kind === "email_send_with_attachments" || kind === "email_thread_reply";
const isSocial = (kind: ExternalAction["kind"]) => kind === "social_publish_linkedin";
const title = (item: ExternalAction) => item.preview.payload.kind === "document_share"
  ? item.preview.shared_artifact?.filename ?? "Shared document"
  : item.preview.payload.kind === "social_publish_linkedin"
    ? "LinkedIn post"
    : "title" in item.preview.payload ? item.preview.payload.title : item.preview.payload.subject;
const reminderLabel = (minutes: number) => minutes === 1440 ? "1 day before start" : minutes >= 60 ? `${minutes / 60} ${minutes === 60 ? "hour" : "hours"} before start` : `${minutes} minutes before start`;

export default function ActionWorkspace({ client, account, emailDraft, socialDraft, focusActionId, onFocused }: { client: CoworkerClient; account: string; emailDraft: EmailDraft | null; socialDraft: string | null; focusActionId?: string | null; onFocused?: () => void }) {
  const [enabled, setEnabled] = useState(false);
  const [connections, setConnections] = useState<ConnectedAccount[]>([]);
  const [history, setHistory] = useState<ExternalAction[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [attachmentsEnabled, setAttachmentsEnabled] = useState(false);
  const [remindersEnabled, setRemindersEnabled] = useState(false);
  const [recipientDirectoryEnabled, setRecipientDirectoryEnabled] = useState(false);
  const [documentSharingEnabled, setDocumentSharingEnabled] = useState(false);
  const [threadingEnabled, setThreadingEnabled] = useState(false);
  const [socialPublishingEnabled, setSocialPublishingEnabled] = useState(false);
  const [replyParentId, setReplyParentId] = useState<string | null>(null);
  const [savedRecipients, setSavedRecipients] = useState<ActionRecipient[]>([]);
  const [recipientName, setRecipientName] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [selectedAttachments, setSelectedAttachments] = useState<string[]>([]);
  const [selectedSharedArtifact, setSelectedSharedArtifact] = useState("");
  const [shareRecipient, setShareRecipient] = useState("");
  const selectedAttachmentsRef = useRef<string[]>([]);
  const [action, setAction] = useState<ExternalAction | null>(null);
  const [mode, setMode] = useState<"email" | "calendar" | "drive" | "social">("email");
  const microsoftEnabled = import.meta.env.VITE_MICROSOFT_ACTIONS_ENABLED === "true";
  const [provider, setProvider] = useState<"google" | "microsoft" | "linkedin">("google");
  const [to, setTo] = useState(""); const [cc, setCc] = useState(""); const [bcc, setBcc] = useState("");
  const [subject, setSubject] = useState(emailDraft?.subject ?? ""); const [body, setBody] = useState(emailDraft?.body ?? "");
  const [socialText, setSocialText] = useState(socialDraft ?? "");
  const [eventTitle, setEventTitle] = useState(""); const [description, setDescription] = useState("");
  const [location, setLocation] = useState(""); const [attendees, setAttendees] = useState("");
  const [start, setStart] = useState(""); const [end, setEnd] = useState("");
  const [timeZone, setTimeZone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [reminderMinutes, setReminderMinutes] = useState<0 | 5 | 10 | 15 | 30 | 60 | 120 | 1440>(0);
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
      const linkedInResult = await finishLinkedInCallback(client, account);
      if (alive && (result || microsoftResult || linkedInResult)) setNotice(linkedInResult ?? microsoftResult ?? result ?? "");
    })().catch(failure => { if (alive) setError(message(failure)); }).finally(() => {
      if (!alive) return;
      const directory = client.actionRecipients(controller.signal).catch(failure => {
        if (failure instanceof WorkspaceError && failure.status === 404) return { enabled: false, recipients: [] as ActionRecipient[] };
        throw failure;
      });
      Promise.all([client.connections(controller.signal), client.actions(controller.signal), client.actionArtifacts(controller.signal), directory]).then(([value, recent, available, recipientDirectory]) => {
        if (!alive) return;
        setEnabled(value.enabled); setRemindersEnabled(value.reminders_enabled); setDocumentSharingEnabled(value.document_sharing_enabled); setThreadingEnabled(value.threading_enabled); setSocialPublishingEnabled(value.social_publishing_enabled); setConnections(value.connections); setHistory(recent.actions);
        setAttachmentsEnabled(available.attachments_enabled); setDocumentSharingEnabled(current => current || available.document_sharing_enabled); setArtifacts(available.artifacts);
        setRecipientDirectoryEnabled(recipientDirectory.enabled); setSavedRecipients(recipientDirectory.recipients); setLoaded(true);
      }).catch(failure => { if (alive) { setError(message(failure)); setLoaded(true); } });
    });
    return () => { alive = false; controller.abort(); };
  }, [client, account, reload]);

  useEffect(() => {
    if (socialDraft === null) return;
    setProvider("linkedin");
    setMode("social");
    setSocialText(socialDraft);
    setReplyParentId(null);
    setComposing(true);
    setAction(null);
    setChecked(false);
    setError("");
    submission.current = undefined;
  }, [socialDraft]);

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

  function setAttachmentSelection(ids: string[]) {
    selectedAttachmentsRef.current = ids;
    setSelectedAttachments(ids);
  }

  function startNewAction(clearAttachments = true, clearReplyParent = true) {
    setComposing(true); setAction(null); setChecked(false); setError(""); submission.current = undefined;
    if (clearReplyParent) setReplyParentId(null);
    if (clearAttachments) {
      setAttachmentSelection([]);
      setReminderMinutes(0);
    }
  }

  function addSavedRecipient(value: ActionRecipient) {
    const current = recipients(mode === "email" ? to : mode === "calendar" ? attendees : shareRecipient);
    if (current.some(item => item.toLowerCase() === value.email.toLowerCase())) return;
    if (current.length >= 20) { setError("Remove a recipient before adding another one."); return; }
    const next = [...current, value.email].join(", ");
    if (mode === "email") setTo(next);
    else if (mode === "calendar") setAttendees(next);
    else setShareRecipient(value.email);
  }

  async function saveRecipient() {
    if (!recipientName.trim() || !recipientEmail.trim()) { setError("Enter a recipient name and complete email address."); return; }
    await run("save-recipient", async () => {
      const value = await client.createActionRecipient(recipientName, recipientEmail);
      setSavedRecipients(previous => [...previous, value].sort((a, b) => a.name.localeCompare(b.name)));
      setRecipientName(""); setRecipientEmail("");
      setNotice(`Saved ${value.name}. The exact address is still shown in every action preview.`);
    });
  }

  async function removeSavedRecipient(value: ActionRecipient) {
    if (!window.confirm(`Remove saved recipient "${value.name}"? Existing action previews will not change.`)) return;
    await run("delete-recipient", async () => {
      await client.deleteActionRecipient(value.id);
      setSavedRecipients(previous => previous.filter(item => item.id !== value.id));
      setNotice(`Removed ${value.name} from saved recipients.`);
    });
  }

  function startThreadReply(parent: ExternalAction) {
    const payload = parent.preview.payload;
    if (
      !threadingEnabled
      || parent.state !== "succeeded"
      || parent.preview.provider !== "google"
      || !isEmail(parent.kind)
      || !parent.receipt?.thread_id
      || !("to" in payload)
    ) return;
    setProvider("google"); setMode("email"); setReplyParentId(parent.id);
    setTo(payload.to.join(", ")); setCc(payload.cc.join(", ")); setBcc("");
    setSubject(payload.subject); setBody(""); setAttachmentSelection([]);
    setSelectedSharedArtifact(""); setReminderMinutes(0); setNotice("Replying inside a Shuddho-owned Gmail thread. No mailbox-read permission is used.");
    setComposing(true); setAction(null); setChecked(false); setError(""); submission.current = undefined;
  }

  async function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentConnection) return;
    // React may defer the state commit after a checkbox event. Keep a synchronous
    // selection mirror so an immediate submit cannot silently downgrade an
    // attachment email into a legacy plain email.
    const attachmentIds = mode === "email" ? [...selectedAttachmentsRef.current] : [];
    const artifactIds = mode === "drive" && selectedSharedArtifact ? [selectedSharedArtifact] : [];
    const input: ActionInput = {
      connection_id: currentConnection.id,
      attachment_ids: attachmentIds,
      artifact_ids: artifactIds,
      payload: mode === "email"
        ? replyParentId
          ? { kind: "email_thread_reply", parent_action_id: replyParentId, to: recipients(to), cc: recipients(cc), bcc: [], subject, body }
          : { kind: attachmentIds.length ? "email_send_with_attachments" : "email_send", to: recipients(to), cc: recipients(cc), bcc: recipients(bcc), subject, body }
        : mode === "calendar"
          ? reminderMinutes !== 0
            ? { kind: "calendar_create_with_reminder", title: eventTitle, description, location, start_at: start, end_at: end, time_zone: timeZone, attendees: recipients(attendees), reminder_minutes_before_start: reminderMinutes }
            : { kind: "calendar_create", title: eventTitle, description, location, start_at: start, end_at: end, time_zone: timeZone, attendees: recipients(attendees) }
          : mode === "drive"
            ? { kind: "document_share", recipients: recipients(shareRecipient) }
            : { kind: "social_publish_linkedin", text: socialText },
    };
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
      if (p.kind === "social_publish_linkedin") {
        setMode("social"); setSocialText(p.text); setAttachmentSelection([]); setSelectedSharedArtifact(""); setReminderMinutes(0); setReplyParentId(null);
      } else if (p.kind === "document_share") {
        setMode("drive"); setAttachmentSelection([]); setSelectedSharedArtifact(action.preview.shared_artifact?.id ?? ""); setShareRecipient(p.recipients[0] ?? ""); setReminderMinutes(0);
      } else if (!("title" in p)) {
        setMode("email"); setTo(p.to.join(", ")); setCc(p.cc.join(", ")); setBcc(p.bcc.join(", ")); setSubject(p.subject); setBody(p.body); setAttachmentSelection((action.preview.attachments ?? []).map(item => item.id)); setSelectedSharedArtifact(""); setReminderMinutes(0);
        setReplyParentId(p.kind === "email_thread_reply" ? p.parent_action_id : null);
      } else {
        setMode("calendar"); setAttachmentSelection([]); setSelectedSharedArtifact(""); setEventTitle(p.title); setDescription(p.description); setLocation(p.location); setAttendees(p.attendees.join(", ")); setStart(p.start_at.slice(0, 16)); setEnd(p.end_at.slice(0, 16)); setTimeZone(p.time_zone); setReminderMinutes(p.kind === "calendar_create_with_reminder" && remindersEnabled ? p.reminder_minutes_before_start : 0);
      }
      startNewAction(false, false); setReload(x => x + 1);
    });
  }

  const payload = action?.preview.payload;
  return <section className="cw-actions" aria-label={socialPublishingEnabled ? "Approved external actions" : documentSharingEnabled ? "Email, calendar, and document sharing actions" : "Email and calendar actions"}>
    <div className="cw-action-intro"><div><span className="cw-eyebrow">Your final say</span><h2>From a good draft to done.</h2><p>Prepare an external action, review every detail, then approve it.</p></div></div>
    {error && <p className="cw-error" role="alert">{error}</p>}{notice && <p className="cw-notice" role="status">{notice}</p>}
    {!loaded ? <p role="status">Loading connections…</p> : !enabled && <p className="cw-notice">New actions are not enabled in this workspace. Saved previews and receipts remain available.</p>}
    {(microsoftEnabled || socialPublishingEnabled) && <label>Provider<select aria-label="Action provider" value={provider} onChange={event => {
      const next = event.target.value as "google" | "microsoft" | "linkedin";
      setProvider(next);
      setReplyParentId(null);
      if (next === "linkedin") setMode("social");
      else if (mode === "social" || (next === "microsoft" && mode === "drive")) setMode("email");
    }} disabled={Boolean(busy) || Boolean(replyParentId)}>
      <option value="google">Google</option>
      {microsoftEnabled && <option value="microsoft">Microsoft</option>}
      {socialPublishingEnabled && <option value="linkedin">LinkedIn</option>}
    </select></label>}
    <div className="cw-connection-grid">{(
      provider === "google"
        ? (["email", "calendar", "drive"] as const)
        : provider === "microsoft"
          ? (["email", "calendar"] as const)
          : (["social"] as const)
    ).map(capability => {
      const connected = connections.find(value => value.provider === provider && value.capability === capability);
      const label = provider === "linkedin"
        ? "LinkedIn"
        : capability === "email"
          ? (provider === "google" ? "Gmail" : "Outlook / Microsoft Mail")
          : capability === "calendar"
            ? (provider === "google" ? "Google Calendar" : "Microsoft Calendar")
            : "Google Drive";
      const accountLabel = provider === "linkedin" ? "Connected personal member" : connected?.email;
      const description = capability === "social"
        ? "Publish public text posts only after explicit approval"
        : capability === "email"
          ? "Send emails you approve"
          : capability === "calendar"
            ? "Create events in your primary calendar"
            : "Share one approved Shuddho artifact";
      return <div className="cw-connection" key={provider + capability}><div><strong>{label}</strong><small>{connected ? accountLabel : description}</small></div>
        {connected ? <button className="cw-text-button" disabled={Boolean(busy)} onClick={() => {
          if (!window.confirm(`Disconnect ${label}? Pending actions will be cancelled. An action already executing may still finish.`)) return;
          void run("disconnect", async () => { const result = await client.disconnect(connected.id); setNotice(result.message); setReload(x => x + 1); if (action) updateAction(await client.action(action.id)); });
        }}>Disconnect {label}</button> : <button className="cw-secondary" disabled={!enabled || Boolean(busy)} onClick={() => void run("connect", () => provider === "google"
          ? beginGoogleConnection(client, account, capability as "email" | "calendar" | "drive")
          : provider === "microsoft"
            ? beginMicrosoftConnection(client, account, capability as "email" | "calendar")
            : beginLinkedInConnection(client, account))}>Connect {label}</button>}
      </div>;
    })}</div>
    <p className="cw-fineprint">{provider === "google"
      ? <>Google permissions can also be removed in your <a href="https://myaccount.google.com/connections" target="_blank" rel="noreferrer">Google Account</a>.</>
      : provider === "microsoft"
        ? <>Microsoft permissions can also be reviewed in your Microsoft account's app permissions.</>
        : <>LinkedIn publishing uses only your connected personal member and the post text you explicitly approve. No feed-read, company-page, media, comments, likes, scheduling, edit, or delete permission is used.</>}</p>
    <div className="cw-layout"><div className="cw-compose cw-action-compose">
      <div className="cw-card-title"><span className="cw-step-number">01</span><div><h2>{composing ? "Prepare an action" : "Action details"}</h2><p>{composing ? "Nothing is sent when you prepare a preview." : "This preview is saved exactly as shown."}</p></div></div>
      {composing ? <form onSubmit={prepare}>
        <label>Action type<select aria-label="Action type" value={mode} onChange={event => setMode(event.target.value as "email" | "calendar" | "drive" | "social")} disabled={Boolean(busy) || Boolean(replyParentId)}>
          {provider === "linkedin" ? <option value="social">Publish a LinkedIn post</option> : <>
            <option value="email">Send an email</option><option value="calendar">Create a calendar event</option>{provider === "google" && documentSharingEnabled && <option value="drive">Share a document</option>}
          </>}
        </select></label>
        <p className="cw-action-account">{currentConnection ? <>{mode === "social" ? <strong>Connected LinkedIn personal member</strong> : <>From <strong>{currentConnection.email}</strong></>}{mode === "calendar" && " · Primary calendar"}{mode === "drive" && " · Google Drive"}</> : `Connect ${provider === "linkedin" ? "LinkedIn" : provider === "google" ? (mode === "email" ? "Gmail" : mode === "calendar" ? "Google Calendar" : "Google Drive") : (mode === "email" ? "Microsoft Mail" : "Microsoft Calendar")} above to continue.`}</p>
        {mode !== "social" && !replyParentId && (recipientDirectoryEnabled || savedRecipients.length > 0) && <fieldset className="cw-agent-files">
          <legend>Saved recipients</legend>
          {recipientDirectoryEnabled && <><div className="cw-action-row">
            <label>Name<input dir="auto" value={recipientName} onChange={event => setRecipientName(event.target.value)} maxLength={80} placeholder="e.g. Finance team" /></label>
            <label>Email<input dir="ltr" type="email" value={recipientEmail} onChange={event => setRecipientEmail(event.target.value)} maxLength={254} placeholder="name@example.com" /></label>
          </div>
          <button type="button" className="cw-secondary" disabled={Boolean(busy) || !recipientName.trim() || !recipientEmail.trim()} onClick={() => void saveRecipient()}>{busy === "save-recipient" ? "Saving…" : "Save recipient"}</button></>}
          {savedRecipients.length > 0 ? <div className="cw-connection-grid">{savedRecipients.map(item => <div className="cw-connection" key={item.id}>
            <div><strong dir="auto">{item.name}</strong><small dir="ltr">{item.email}</small></div>
            <div><button type="button" className="cw-text-button" disabled={Boolean(busy) || !recipientDirectoryEnabled} onClick={() => addSavedRecipient(item)}>{mode === "email" ? "Add to To" : mode === "calendar" ? "Add guest" : "Use recipient"}</button>
              <button type="button" className="cw-text-button" disabled={Boolean(busy)} onClick={() => void removeSavedRecipient(item)}>Remove</button></div>
          </div>)}</div> : recipientDirectoryEnabled && <small>No saved recipients yet.</small>}
          <small>Saved recipients are private Shuddho shortcuts. Selecting one only copies its exact email address into this draft; the final immutable preview is still what you approve. Agents cannot resolve or select saved recipients.</small>
        </fieldset>}
        {mode === "email" ? <>
          {replyParentId && <p className="cw-notice">This reply keeps the original To/Cc recipients and subject. Bcc and attachments are disabled so the approved Gmail thread cannot be widened.</p>}
          <label>To<input dir="ltr" value={to} onChange={event => setTo(event.target.value)} required readOnly={Boolean(replyParentId)} maxLength={5100} placeholder="name@example.com" /></label>
          <div className="cw-action-row"><label>Cc<input dir="ltr" value={cc} onChange={event => setCc(event.target.value)} readOnly={Boolean(replyParentId)} maxLength={5100} /></label><label>Bcc<input dir="ltr" value={bcc} onChange={event => setBcc(event.target.value)} readOnly={Boolean(replyParentId)} maxLength={5100} /></label></div>
          <small>{replyParentId ? "Thread authority comes only from the confirmed Shuddho parent email; Shuddho does not read your mailbox." : "Use full email addresses, separated by commas. Up to 20 recipients in total."}</small>
          <label>Subject<input dir="auto" value={subject} onChange={event => setSubject(event.target.value)} required readOnly={Boolean(replyParentId)} maxLength={300} /></label>
          <label>Message<textarea dir="auto" rows={9} value={body} onChange={event => setBody(event.target.value)} required maxLength={20000} /></label>
          {!replyParentId && attachmentsEnabled && artifacts.length > 0 && <fieldset className="cw-agent-files"><legend>Attach Shuddho artifacts (optional)</legend>
            {artifacts.filter(item => {
              const type = item.content_type.split(";", 1)[0].toLowerCase();
              return ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/plain"].includes(type);
            }).slice(0, 30).map(item => {
              const selected = selectedAttachments.includes(item.id);
              const selectedBytes = artifacts.filter(value => selectedAttachments.includes(value.id)).reduce((sum, value) => sum + value.byte_size, 0);
              const unavailable = !selected && (selectedAttachments.length >= 3 || selectedBytes + item.byte_size > 2 * 1024 * 1024);
              return <label key={item.id}><input type="checkbox" name="attachment_id" value={item.id} checked={selected} disabled={Boolean(busy) || unavailable}
                onChange={event => {
                  const next = event.target.checked
                    ? [...selectedAttachmentsRef.current, item.id]
                    : selectedAttachmentsRef.current.filter(id => id !== item.id);
                  setAttachmentSelection([...new Set(next)]);
                }} />
                <span>{item.filename} · {(item.byte_size / 1024).toFixed(0)} KB · SHA {item.sha256.slice(0, 8)}{item.created_at ? ` · ${new Date(item.created_at).toLocaleDateString()}` : ""}</span></label>;
            })}
            <small>Up to 3 existing Shuddho artifacts, 2 MB total. The exact artifact hashes are bound to approval.</small>
          </fieldset>}
          <p className="cw-fineprint">Plain-text email, sent immediately after approval.{attachmentsEnabled ? " Attachments must already exist in this Shuddho workspace." : " Attachments are disabled in this deployment."}</p>
        </> : mode === "calendar" ? <>
          <label>Event title<input dir="auto" required maxLength={300} value={eventTitle} onChange={event => setEventTitle(event.target.value)} /></label>
          <div className="cw-action-row"><label>Starts<input type="datetime-local" required value={start} onChange={event => setStart(event.target.value)} /></label><label>Ends<input type="datetime-local" required value={end} onChange={event => setEnd(event.target.value)} /></label></div>
          <label>Time zone<input required maxLength={80} value={timeZone} onChange={event => setTimeZone(event.target.value)} placeholder="Asia/Dhaka" /></label>
          <small>Use an IANA time zone such as Asia/Dhaka, Asia/Kolkata or America/New_York.</small>
          <label>Guests<input dir="ltr" value={attendees} onChange={event => setAttendees(event.target.value)} maxLength={5100} placeholder="Optional email addresses, separated by commas" /></label>
          <label>Location<input dir="auto" value={location} onChange={event => setLocation(event.target.value)} maxLength={500} /></label>
          <label>Event description<textarea dir="auto" rows={4} value={description} onChange={event => setDescription(event.target.value)} maxLength={20000} /></label>
          {remindersEnabled && <label>Reminder<select aria-label="Reminder" value={reminderMinutes} onChange={event => setReminderMinutes(Number(event.target.value) as 0 | 5 | 10 | 15 | 30 | 60 | 120 | 1440)} disabled={Boolean(busy)}>
            <option value={0}>None</option><option value={5}>5 minutes before</option><option value={10}>10 minutes before</option><option value={15}>15 minutes before</option><option value={30}>30 minutes before</option><option value={60}>1 hour before</option><option value={120}>2 hours before</option><option value={1440}>1 day before</option>
          </select></label>}
          <p className="cw-fineprint">A single event in your primary calendar. Invitations are sent to all listed guests, who can see each other.{remindersEnabled ? " You may add one explicit reminder." : " Reminders are disabled in this deployment."} No video link is requested.</p>
        </> : mode === "drive" ? <>
          <label>Recipient<input dir="ltr" type="email" value={shareRecipient} onChange={event => setShareRecipient(event.target.value)} required maxLength={254} placeholder="name@example.com" /></label>
          <fieldset className="cw-agent-files"><legend>Document to share</legend>
            {artifacts.filter(item => {
              const type = item.content_type.split(";", 1)[0].toLowerCase();
              return item.byte_size <= 8 * 1024 * 1024 && ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/plain"].includes(type);
            }).slice(0, 30).map(item => <label key={item.id}><input type="radio" name="shared_artifact_id" value={item.id} checked={selectedSharedArtifact === item.id} disabled={Boolean(busy)} onChange={() => setSelectedSharedArtifact(item.id)} /><span>{item.filename} · {(item.byte_size / 1024).toFixed(0)} KB · SHA {item.sha256.slice(0, 8)}</span></label>)}
            <small>Exactly one existing Shuddho artifact, up to 8 MB. Its full SHA-256 is bound to your approval.</small>
          </fieldset>
          <p className="cw-fineprint">Google Drive only. Shuddho uploads this exact artifact and grants this exact recipient reader access. No public link, folder browsing, writer access, or contact lookup.</p>
        </> : <>
          <label>LinkedIn post<textarea dir="auto" rows={10} value={socialText} onChange={event => setSocialText(event.target.value)} required minLength={1} maxLength={3000} /></label>
          <span className="cw-field-meta">{socialText.length.toLocaleString()} / 3,000 characters</span>
          <p className="cw-fineprint">Personal LinkedIn profile only. Public text post only. The exact text and connected member are bound to your immutable approval preview. No media, organization page, feed read, scheduling, comments, reactions, edit, delete, or Agent publishing authority.</p>
        </>}
        <button className="cw-primary" disabled={!enabled || !currentConnection || Boolean(busy) || (mode === "drive" && (!selectedSharedArtifact || recipients(shareRecipient).length !== 1))}>{busy === "prepare" ? "Preparing…" : "Review action"}<span aria-hidden="true">→</span></button>
      </form> : action ? <>
        <dl className="cw-action-details"><dt>Account</dt><dd><bdi>{action.preview.account}</bdi></dd>
          {payload?.kind === "social_publish_linkedin" ? <><dt>Provider</dt><dd>LinkedIn</dd><dt>Author</dt><dd>Connected personal member</dd><dt>Visibility</dt><dd>Public</dd><dt>Media</dt><dd>None</dd><dt>Timing</dt><dd>Publish immediately after approval</dd></> : payload?.kind === "document_share" ? <><dt>Document</dt><dd>{action.preview.shared_artifact?.filename}</dd><dt>Artifact SHA-256</dt><dd><code>{action.preview.shared_artifact?.sha256}</code></dd><dt>Recipient</dt><dd>{payload.recipients[0]}</dd><dt>Access</dt><dd>Reader only</dd><dt>Notification</dt><dd>Notify the recipient</dd><dt>Timing</dt><dd>Share immediately after approval</dd></> : payload && !("title" in payload) ? <><dt>To</dt><dd>{payload.to.join(", ")}</dd><dt>Cc</dt><dd>{payload.cc.join(", ") || "None"}</dd><dt>Bcc</dt><dd>{payload.bcc.join(", ") || "None"}</dd><dt>Attachments</dt><dd>{(action.preview.attachments ?? []).length ? (action.preview.attachments ?? []).map(item => item.filename).join(", ") : "None"}</dd><dt>Timing</dt><dd>Send immediately after approval</dd></> : payload && "title" in payload && <>
            <dt>Calendar</dt><dd>Primary calendar</dd><dt>Starts</dt><dd>{payload.start_at.replace("T", " ")}</dd><dt>Ends</dt><dd>{payload.end_at.replace("T", " ")}</dd><dt>Time zone</dt><dd>{payload.time_zone}</dd><dt>Guests</dt><dd>{payload.attendees.join(", ") || "None"}</dd><dt>Invitations</dt><dd>Notify all listed guests; guests can see each other</dd><dt>Location</dt><dd dir="auto">{payload.location || "None"}</dd><dt>Reminder</dt><dd>{payload.kind === "calendar_create_with_reminder" ? reminderLabel(payload.reminder_minutes_before_start) : "None"}</dd><dt>Video</dt><dd>None added</dd>
          </>}
        </dl>
        <div className="cw-action-content" dir="auto"><h3>{title(action)}</h3>{payload?.kind !== "document_share" && <p>{payload?.kind === "social_publish_linkedin" ? payload.text : payload && "title" in payload ? payload.description : payload?.body}</p>}</div>
        {action.state === "awaiting_approval" && <button type="button" className="cw-secondary" disabled={Boolean(busy)} onClick={() => void edit()}>Edit details</button>}
      </> : null}
    </div>
    <div className="cw-output-column"><section className="cw-result cw-action-review" aria-label="Action review">
      <span className="cw-eyebrow">02 · Review and approve</span><h2>{action ? labels[action.state] : "You stay in control."}</h2>
      {composing || !action ? <p>Your preview will appear here. Check the full message or event details before approving.</p> : <>
        <p role="status">{action.message}</p>
        {action.state === "awaiting_approval" && <>
          <p className="cw-fineprint">Preview expires {new Date(action.preview.expires_at).toLocaleTimeString()}. Approval starts execution within five minutes.</p>
          <label className="cw-approval-check"><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} />{isSocial(action.kind) ? "I reviewed the connected LinkedIn member, exact post text, public visibility and immediate publish timing." : isDocumentShare(action.kind) ? "I reviewed the account, exact document hash, recipient and reader access." : "I reviewed the account, recipients, content and timing."}</label>
          <button className="cw-primary" disabled={!checked || !enabled || Boolean(busy)} onClick={() => void run("approve", async () => updateAction(await client.approveAction(action)))}>{busy === "approve" ? "Approving…" : isSocial(action.kind) ? "Approve & publish to LinkedIn" : isEmail(action.kind) ? "Approve & send email" : isDocumentShare(action.kind) ? "Approve & share document" : "Approve & create event"}</button>
        </>}
        {["awaiting_approval", "queued"].includes(action.state) && <button className="cw-text-button cw-cancel" disabled={Boolean(busy)} onClick={() => void run("cancel", async () => updateAction(await client.cancelAction(action.id)))}>Cancel action</button>}
        {action.state === "outcome_unknown" && (isCalendar(action.kind) || isDocumentShare(action.kind)) && action.preview.provider === "google" && <button className="cw-secondary" disabled={Boolean(busy) || !enabled} onClick={() => void run("reconcile", async () => updateAction(await client.reconcileAction(action.id)))}>{busy === "reconcile" ? (isDocumentShare(action.kind) ? "Checking Drive…" : "Checking calendar…") : (isDocumentShare(action.kind) ? "Check Drive result" : "Check calendar result")}</button>}
        {threadingEnabled && action.state === "succeeded" && action.preview.provider === "google" && isEmail(action.kind) && action.receipt?.thread_id && <button type="button" className="cw-secondary" disabled={Boolean(busy)} onClick={() => startThreadReply(action)}>Reply in this Gmail thread</button>}
        {action.receipt && <div className="cw-receipt"><strong>{isSocial(action.kind) ? "Published on LinkedIn" : isDocumentShare(action.kind) ? "Shared in Google Drive" : action.preview.provider === "microsoft" ? (isEmail(action.kind) ? "Accepted by Microsoft Graph" : "Created in Microsoft Calendar") : (isEmail(action.kind) ? "Accepted by Gmail" : "Created in Google Calendar")}</strong><p>{isSocial(action.kind) ? "LinkedIn confirmed creation of the approved public post. Shuddho does not read engagement, comments, reactions, or your feed." : isDocumentShare(action.kind) ? `Google Drive confirmed reader access for ${action.receipt.recipient ?? "the approved recipient"}. This does not mean the recipient opened the document.` : action.preview.provider === "microsoft" ? (isEmail(action.kind) ? "This confirms Microsoft Graph accepted the send request. It does not confirm delivery or reading." : "Microsoft Graph confirmed the event. Guest attendance is not yet confirmed.") : (isEmail(action.kind) ? "This confirms Gmail accepted the message. It does not confirm delivery or that it was read." : "Google confirmed the event. Guest attendance is not yet confirmed.")}</p><small>{new Date(action.receipt.confirmed_at).toLocaleString()}</small>{action.receipt.provider_id && <code>Receipt: {action.receipt.provider_id}</code>}</div>}
        {action.audit && <details className="cw-action-audit"><summary>Action history</summary><ol>{action.audit.map((item, index) => <li key={index}>{item.action.replace("action.", "").replaceAll("_", " ")} · {new Date(item.created_at).toLocaleString()}</li>)}</ol></details>}
      </>}
    </section>
    <section className="cw-history"><div className="cw-history-title"><h2>Recent actions</h2><button className="cw-text-button" onClick={() => { setReload(x => x + 1); if (action) void run("refresh", async () => updateAction(await client.action(action.id))); }}>Refresh actions</button></div>
      {history.length ? <ul>{history.map(item => <li key={item.id}><button aria-pressed={action?.id === item.id} disabled={Boolean(busy)} onClick={() => void run("open", async () => openAction(await client.action(item.id)))}><div><strong dir="auto">{title(item)}</strong><small>{isSocial(item.kind) ? "LinkedIn post" : isEmail(item.kind) ? "Email" : isDocumentShare(item.kind) ? "Document" : "Calendar"} · {isSocial(item.kind) ? "personal member" : item.preview.account}</small></div><span className="cw-status">{labels[item.state]}</span></button></li>)}</ul> : <p className="cw-fineprint">Your approved actions and receipts will appear here.</p>}
      {!composing && action && <button type="button" className="cw-secondary cw-new-action" disabled={Boolean(busy)} onClick={() => startNewAction()}>Prepare another action</button>}
    </section></div></div>
  </section>;
}
