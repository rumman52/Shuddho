import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { CoworkerClient, type AgentNotification, type BrowserPushConfig, type ConnectorReadGrant, type NotificationDigest, type NotificationPreferences, type PersonalAutomation, type PersonalGoal } from "./client";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const message = (error: unknown) => error instanceof Error ? error.message : "This automation action could not finish.";

function applicationServerKey(value: string): ArrayBuffer {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const decoded = atob(normalized + "=".repeat((4 - normalized.length % 4) % 4));
  const bytes = Uint8Array.from(decoded, char => char.charCodeAt(0));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

export default function AutomationWorkspace({ client }: { client: CoworkerClient }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [goals, setGoals] = useState<PersonalGoal[]>([]);
  const [automations, setAutomations] = useState<PersonalAutomation[]>([]);
  const [connectorGrants, setConnectorGrants] = useState<ConnectorReadGrant[]>([]);
  const [notifications, setNotifications] = useState<AgentNotification[]>([]);
  const [digests, setDigests] = useState<NotificationDigest[]>([]);
  const [groupNotices, setGroupNotices] = useState(false);
  const [notificationPreferences, setNotificationPreferences] = useState<NotificationPreferences | null>(null);
  const [browserPushConfig, setBrowserPushConfig] = useState<BrowserPushConfig | null>(null);
  const [browserPushDeviceActive, setBrowserPushDeviceActive] = useState(false);
  const [goalId, setGoalId] = useState("");
  const [kind, setKind] = useState<"daily" | "weekly" | "event">("daily");
  const [eventGrantId, setEventGrantId] = useState("");
  const [weekdays, setWeekdays] = useState<string[]>(["mon", "tue", "wed", "thu", "fri"]);
  const [at, setAt] = useState("08:00");
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [quiet, setQuiet] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const createKey = useRef("");

  const selectedGoal = useMemo(() => goals.find(item => item.id === goalId) ?? null, [goals, goalId]);
  const activeConnectorGrants = useMemo(
    () => connectorGrants.filter(item => item.state === "active"),
    [connectorGrants],
  );

  async function currentBrowserPushDevice(signal?: AbortSignal) {
    if (!("serviceWorker" in navigator)) return false;
    const registration = await navigator.serviceWorker.getRegistration("/");
    const subscription = registration ? await registration.pushManager.getSubscription() : null;
    if (!subscription) return false;
    return (await client.browserPushSubscriptionStatus(subscription.endpoint, signal)).active;
  }

  async function reload(signal?: AbortSignal) {
    const [goalResult, automationResult, grantResult, notificationResult, notificationPreferenceResult, digestResult, pushConfigResult] = await Promise.all([
      client.goals(signal), client.automations(signal), client.connectorReadGrants(signal),
      client.notifications(signal), client.notificationPreferences(signal), client.notificationDigests(signal), client.browserPushConfig(signal),
    ]);
    const activeGoals = goalResult.goals.filter(item => item.state === "active");
    setGoals(activeGoals);
    setGoalId(value => activeGoals.some(item => item.id === value) ? value : activeGoals[0]?.id ?? "");
    setEnabled(automationResult.enabled);
    setAutomations(automationResult.automations);
    const activeGrants = grantResult.enabled ? grantResult.grants.filter(item => item.state === "active") : [];
    setConnectorGrants(activeGrants);
    setEventGrantId(value => activeGrants.some(item => item.id === value) ? value : activeGrants[0]?.id ?? "");
    setNotifications(notificationResult.notifications);
    setDigests(digestResult.digests);
    setNotificationPreferences(notificationPreferenceResult);
    setBrowserPushConfig(pushConfigResult);
    setBrowserPushDeviceActive(await currentBrowserPushDevice(signal));
  }

  useEffect(() => {
    const controller = new AbortController();
    reload(controller.signal).catch(error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [client]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!selectedGoal || busy) return;
    if (!createKey.current) createKey.current = crypto.randomUUID();
    const [hour, minute] = at.split(":").map(Number);
    setBusy("create"); setError(""); setNotice("");
    try {
      if (kind === "event" && !eventGrantId) throw new Error("Choose an active connected read authorization.");
      await client.createAutomation({
        goal_id: selectedGoal.id, goal_revision: selectedGoal.revision, timezone,
        schedule: kind === "event"
          ? { kind: "event", grant_id: eventGrantId }
          : { kind, hour, minute, weekdays: kind === "weekly" ? weekdays : [] },
        output_language: "en", overlap_policy: "skip", catchup_window_seconds: 3600,
        quiet_hours: quiet ? { start: "22:00", end: "07:00" } : null, expires_at: null,
      }, createKey.current);
      createKey.current = "";
      await reload();
      setNotice(kind === "event"
        ? "Automation saved. An authorized connected update can wake one bounded Agent run."
        : "Automation saved. Temporal will reconcile the durable schedule before it can fire.");
    } catch (error) { setError(message(error)); }
    finally { setBusy(""); }
  }

  async function transition(item: PersonalAutomation, action: "pause" | "resume" | "cancel") {
    if (busy) return;
    setBusy(item.id); setError(""); setNotice("");
    try {
      await client.transitionAutomation(item.id, item.revision, action);
      await reload();
      setNotice(`Automation ${action === "cancel" ? "cancelled" : action + "d"}.`);
    } catch (error) { setError(message(error)); }
    finally { setBusy(""); }
  }

  async function markRead(item: AgentNotification, digestId?: string) {
    if (item.state === "read" || busy) return;
    setBusy(item.id); setError("");
    try {
      if (digestId) await client.readNotificationDigest(digestId, [item.id]);
      else await client.readNotification(item.id);
      await reload();
    } catch (error) {
      setError(message(error));
      if (digestId) { try { await reload(); } catch { /* Keep the action error. */ } }
    }
    finally { setBusy(""); }
  }

  async function markDigestRead(item: NotificationDigest) {
    if (!item.unread_count || busy) return;
    setBusy(item.id); setError(""); setNotice("");
    try {
      await client.readNotificationDigest(item.id, item.notifications.map(value => value.id));
      await reload();
      setNotice("The notices in this digest are marked as read.");
    } catch (error) {
      setError(message(error));
      try { await reload(); } catch { /* Keep the original action error visible. */ }
    } finally { setBusy(""); }
  }

  async function setBrowserPush(nextEnabled: boolean) {
    if (busy || !notificationPreferences) return;
    setBusy("browser-push"); setError(""); setNotice("");
    try {
      if (!nextEnabled) {
        const registration = "serviceWorker" in navigator
          ? await navigator.serviceWorker.getRegistration("/") : undefined;
        const subscription = registration ? await registration.pushManager.getSubscription() : null;
        if (subscription) {
          await client.deactivateBrowserPushSubscription(subscription.endpoint);
          await subscription.unsubscribe();
        }
        const saved = await client.saveNotificationPreferences({
          ...notificationPreferences,
          browser_push_enabled: false,
        });
        setNotificationPreferences(saved);
        setBrowserPushDeviceActive(false);
        setNotice("Browser notifications are off for this account.");
        return;
      }
      if (!browserPushConfig?.enabled || !browserPushConfig.application_server_key) {
        throw new Error("Browser notifications are not enabled in this deployment yet.");
      }
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
        throw new Error("This browser does not support Web Push.");
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted") throw new Error("Browser notification permission was not granted.");
      const registration = await navigator.serviceWorker.register("/push-sw.js", { scope: "/" });
      await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: applicationServerKey(browserPushConfig.application_server_key),
        });
      }
      const json = subscription.toJSON();
      if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
        throw new Error("The browser returned an incomplete push subscription.");
      }
      await client.saveBrowserPushSubscription({
        endpoint: json.endpoint,
        p256dh: json.keys.p256dh,
        auth: json.keys.auth,
        expiration_time: subscription.expirationTime,
      });
      const saved = await client.saveNotificationPreferences({
        ...notificationPreferences,
        browser_push_enabled: true,
      });
      setNotificationPreferences(saved);
      setBrowserPushDeviceActive(true);
      setNotice("Browser notifications are enabled for this account and device.");
    } catch (error) { setError(message(error)); }
    finally { setBusy(""); }
  }

  async function saveNotificationPreference(next: NotificationPreferences) {
    if (busy) return;
    setBusy("notification-preferences"); setError(""); setNotice("");
    try {
      const saved = await client.saveNotificationPreferences(next);
      setNotificationPreferences(saved);
      if (!saved.in_app_enabled) { setNotifications([]); setDigests([]); }
      else await reload();
      setNotice(saved.in_app_enabled
        ? "In-app notification preferences saved."
        : "In-app notifications are off. Scheduled work can still run.");
    } catch (error) { setError(message(error)); }
    finally { setBusy(""); }
  }

  if (enabled === null && !error) return <p className="cw-loading" role="status">Loading automations…</p>;

  return <section className="cw-agent cw-automations" aria-label="Automations and notifications">
    <div className="cw-action-intro">
      <span className="cw-eyebrow">Personal agent · PA-02</span>
      <h2>Durable scheduled and event-driven work without a permanent chat session.</h2>
      <p>PostgreSQL stores automation authority. Temporal owns due-time schedules; authenticated connector events may wake only explicitly bound automations. Every occurrence is deduplicated before one bounded run can start.</p>
    </div>
    {error && <p className="cw-error" role="alert">{error}</p>}
    {notice && <p className="cw-notice" role="status">{notice}</p>}
    {enabled === false ? <div className="cw-agent-run"><strong>Automations are disabled.</strong><p className="cw-fineprint">The production-safe default remains off until migration, CI and controlled staging evidence are complete.</p></div> :
    <div className="cw-layout">
      <section className="cw-compose">
        <div className="cw-card-title"><span className="cw-step-number">02</span><div><h2>Automate bounded work</h2><p>Attach a reviewed schedule or connected-event trigger to an active persistent goal.</p></div></div>
        <form onSubmit={create}>
          <label>Goal<select required value={goalId} onChange={event => { setGoalId(event.target.value); createKey.current = ""; }}>
            <option value="">Choose an active goal</option>{goals.map(goal => <option key={goal.id} value={goal.id}>{goal.objective}</option>)}
          </select></label>
          <label>Trigger<select value={kind} onChange={event => { setKind(event.target.value as "daily" | "weekly" | "event"); createKey.current = ""; }}>
            <option value="daily">Daily schedule</option><option value="weekly">Selected weekdays</option><option value="event">Authorized connected update</option>
          </select></label>
          {kind === "event" && <label>Connected read authorization<select required value={eventGrantId} onChange={event => { setEventGrantId(event.target.value); createKey.current = ""; }}>
            <option value="">Choose an active connection grant</option>
            {activeConnectorGrants.map(grant => <option key={grant.id} value={grant.id}>{grant.provider} · {grant.capability}</option>)}
          </select></label>}
          {kind === "event" && activeConnectorGrants.length === 0 && <p className="cw-fineprint">Create an active Gmail/Calendar read authorization before enabling an event-triggered automation.</p>}
          {kind === "weekly" && <fieldset><legend>Weekdays</legend><div className="cw-agent-meta">{DAYS.map(day =>
            <label key={day}><input type="checkbox" checked={weekdays.includes(day)} onChange={event => {
              setWeekdays(previous => event.target.checked ? [...previous, day] : previous.filter(value => value !== day)); createKey.current = "";
            }} /> {day.toUpperCase()}</label>)}</div></fieldset>}
          {kind !== "event" && <label>Local time<input type="time" required value={at} onChange={event => { setAt(event.target.value); createKey.current = ""; }} /></label>}
          <label>Timezone<input required maxLength={64} value={timezone} onChange={event => { setTimezone(event.target.value); createKey.current = ""; }} /></label>
          <label><input type="checkbox" checked={quiet} onChange={event => { setQuiet(event.target.checked); createKey.current = ""; }} /> Delay in-app notifications during 22:00–07:00 quiet hours</label>
          <button className="cw-primary" type="submit" disabled={Boolean(busy) || !selectedGoal || (kind === "weekly" && weekdays.length === 0) || (kind === "event" && !eventGrantId)}>{busy === "create" ? "Saving…" : "Create automation"}<span aria-hidden="true">↗</span></button>
          <p className="cw-fineprint">A schedule or connected event never grants email, calendar-write, purchase, or provider authority. Event content remains untrusted context; consequential actions still use the separate approval boundary.</p>
        </form>
      </section>
      <div className="cw-output-column">
        <div className="cw-history-title"><h2>Automations</h2></div>
        {automations.length === 0 ? <section className="cw-empty"><h2>No automation yet.</h2><p>Create one from an active goal.</p></section> :
        <div className="cw-history"><ul>{automations.map(item => <li key={item.id}><div className="cw-agent-run">
          <strong>{goals.find(goal => goal.id === item.goal_id)?.objective ?? "Persistent goal"}</strong>
          <p>{item.schedule.kind === "event"
            ? `connected update · ${connectorGrants.find(grant => grant.id === item.schedule.grant_id)?.capability ?? "authorized read"} · ${item.timezone}`
            : `${item.schedule.kind} · ${String(item.schedule.hour).padStart(2, "0")}:${String(item.schedule.minute).padStart(2, "0")} · ${item.timezone}`}</p>
          <div className="cw-agent-meta"><span>{item.state}</span><span>revision {item.revision}</span><span>{item.schedule_applied_revision === item.revision ? (item.schedule.kind === "event" ? "event trigger reconciled" : "Temporal reconciled") : "reconciliation pending"}</span>{item.schedule_error_code && <span>{item.schedule_error_code}</span>}</div>
          <div>{item.state === "active" && <button className="cw-secondary" disabled={Boolean(busy)} onClick={() => transition(item, "pause")}>Pause</button>}
            {item.state === "paused" && <button className="cw-secondary" disabled={Boolean(busy)} onClick={() => transition(item, "resume")}>Resume</button>}
            {item.state !== "cancelled" && <button className="cw-text-button" disabled={Boolean(busy)} onClick={() => transition(item, "cancel")}>Cancel</button>}</div>
        </div></li>)}</ul></div>}
        <div className="cw-history-title"><h2>Notifications</h2></div>
        {notificationPreferences && <div className="cw-agent-run">
          <strong>In-app notification controls</strong>
          <label><input type="checkbox"
            checked={notificationPreferences.in_app_enabled}
            disabled={Boolean(busy)}
            onChange={event => saveNotificationPreference({
              ...notificationPreferences,
              in_app_enabled: event.target.checked,
              browser_push_enabled: event.target.checked ? notificationPreferences.browser_push_enabled : false,
            })} /> Show personal-agent notifications in Shuddho</label>
          <label><input type="checkbox"
            checked={notificationPreferences.automation_updates_enabled}
            disabled={Boolean(busy) || !notificationPreferences.in_app_enabled}
            onChange={event => saveNotificationPreference({
              ...notificationPreferences,
              automation_updates_enabled: event.target.checked,
            })} /> Scheduled-work updates</label>
          <label><input type="checkbox"
            checked={notificationPreferences.browser_push_enabled && browserPushDeviceActive}
            disabled={Boolean(busy) || !notificationPreferences.in_app_enabled || (!browserPushConfig?.enabled && !browserPushDeviceActive)}
            onChange={event => setBrowserPush(event.target.checked)} /> Browser notifications on this account and device</label>
          {!browserPushConfig?.enabled && <p className="cw-fineprint">Browser Push delivery is currently disabled by deployment policy. Existing consent can still be revoked.</p>}
          {notificationPreferences.browser_push_enabled && !browserPushConfig?.enabled && !browserPushDeviceActive &&
            <button className="cw-text-button" type="button" disabled={Boolean(busy)} onClick={() => saveNotificationPreference({
              ...notificationPreferences,
              browser_push_enabled: false,
            })}>Turn off Browser Push for this account</button>}
          {notificationPreferences.browser_push_enabled && browserPushConfig?.enabled && !browserPushDeviceActive &&
            <p className="cw-fineprint">Browser Push is allowed for this account, but this browser is not registered yet. Enable the checkbox to add this device.</p>}
          <p className="cw-fineprint">Browser Push requires separate account consent plus browser permission. Push messages use generic text; open Shuddho to review the actual notice. Turning notifications off never pauses goals or automations.</p>
        </div>}
        <label className="cw-digest-toggle"><input type="checkbox" checked={groupNotices} onChange={event => setGroupNotices(event.target.checked)} /> Group suggestion notices into digests</label>
        <p className="cw-fineprint">Groups contain up to ten delivered notices from the same six-hour period. Expand a group to review each notice.</p>
        {groupNotices ? (digests.length === 0 ? <p className="cw-fineprint">No available digests. Notices may have expired or their source access may have changed.</p> :
          <div className="cw-history"><ul>{digests.map(item => <li key={item.id}><div className="cw-agent-run cw-notification-digest">
            <details><summary><strong>{item.title}</strong><small>{item.unread_count} unread · {new Date(item.latest_at).toLocaleString()}</small></summary>
              <ul className="cw-digest-members">{item.notifications.map(member => <li key={member.id}>
                <strong>{member.title}</strong><p>{member.message}</p>
                <small>{new Date(member.visible_at).toLocaleString()} · {member.state}</small>
                {member.state !== "read" && <button className="cw-text-button" disabled={Boolean(busy)} onClick={() => markRead(member, member.read_digest_id)}>Mark as read</button>}
              </li>)}</ul>
            </details>
            <button className="cw-secondary" disabled={Boolean(busy) || item.unread_count === 0} onClick={() => markDigestRead(item)}>{item.unread_count === 0 ? "All read" : "Mark digest as read"}</button>
          </div></li>)}</ul></div>) : (notifications.length === 0 ? <p className="cw-fineprint">No delivered in-app notifications yet.</p> :
        <div className="cw-history"><ul>{notifications.map(item => <li key={item.id}><button type="button" disabled={Boolean(busy)} onClick={() => markRead(item)}><div><strong>{item.title}</strong><small>{item.message} · {new Date(item.created_at).toLocaleString()} · {item.state}</small></div></button></li>)}</ul></div>)}
      </div>
    </div>}
  </section>;
}
