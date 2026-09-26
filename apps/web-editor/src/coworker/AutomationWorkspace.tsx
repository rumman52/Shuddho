import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { CoworkerClient, type AgentNotification, type PersonalAutomation, type PersonalGoal } from "./client";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const message = (error: unknown) => error instanceof Error ? error.message : "This automation action could not finish.";

export default function AutomationWorkspace({ client }: { client: CoworkerClient }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [goals, setGoals] = useState<PersonalGoal[]>([]);
  const [automations, setAutomations] = useState<PersonalAutomation[]>([]);
  const [notifications, setNotifications] = useState<AgentNotification[]>([]);
  const [goalId, setGoalId] = useState("");
  const [kind, setKind] = useState<"daily" | "weekly">("daily");
  const [weekdays, setWeekdays] = useState<string[]>(["mon", "tue", "wed", "thu", "fri"]);
  const [at, setAt] = useState("08:00");
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [quiet, setQuiet] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const createKey = useRef("");

  const selectedGoal = useMemo(() => goals.find(item => item.id === goalId) ?? null, [goals, goalId]);

  async function reload(signal?: AbortSignal) {
    const [goalResult, automationResult, notificationResult] = await Promise.all([
      client.goals(signal), client.automations(signal), client.notifications(signal),
    ]);
    const activeGoals = goalResult.goals.filter(item => item.state === "active");
    setGoals(activeGoals);
    setGoalId(value => activeGoals.some(item => item.id === value) ? value : activeGoals[0]?.id ?? "");
    setEnabled(automationResult.enabled);
    setAutomations(automationResult.automations);
    setNotifications(notificationResult.notifications);
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
      await client.createAutomation({
        goal_id: selectedGoal.id, goal_revision: selectedGoal.revision, timezone,
        schedule: { kind, hour, minute, weekdays: kind === "weekly" ? weekdays : [] },
        output_language: "en", overlap_policy: "skip", catchup_window_seconds: 3600,
        quiet_hours: quiet ? { start: "22:00", end: "07:00" } : null, expires_at: null,
      }, createKey.current);
      createKey.current = "";
      await reload();
      setNotice("Automation saved. Temporal will reconcile the durable schedule before it can fire.");
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

  async function markRead(item: AgentNotification) {
    if (item.state === "read") return;
    try {
      await client.readNotification(item.id);
      setNotifications(previous => previous.map(value => value.id === item.id ? { ...value, state: "read", read_at: new Date().toISOString() } : value));
    } catch (error) { setError(message(error)); }
  }

  if (enabled === null && !error) return <p className="cw-loading" role="status">Loading automations…</p>;

  return <section className="cw-agent cw-automations" aria-label="Automations and notifications">
    <div className="cw-action-intro">
      <span className="cw-eyebrow">Personal agent · PA-02</span>
      <h2>Recurring work without a permanent chat session.</h2>
      <p>PostgreSQL stores the desired schedule. Temporal owns due-time execution. Every firing is deduplicated before one bounded run can start.</p>
    </div>
    {error && <p className="cw-error" role="alert">{error}</p>}
    {notice && <p className="cw-notice" role="status">{notice}</p>}
    {enabled === false ? <div className="cw-agent-run"><strong>Automations are disabled.</strong><p className="cw-fineprint">The production-safe default remains off until migration, CI and controlled staging evidence are complete.</p></div> :
    <div className="cw-layout">
      <section className="cw-compose">
        <div className="cw-card-title"><span className="cw-step-number">02</span><div><h2>Schedule bounded work</h2><p>Attach recurring execution to an active persistent goal.</p></div></div>
        <form onSubmit={create}>
          <label>Goal<select required value={goalId} onChange={event => { setGoalId(event.target.value); createKey.current = ""; }}>
            <option value="">Choose an active goal</option>{goals.map(goal => <option key={goal.id} value={goal.id}>{goal.objective}</option>)}
          </select></label>
          <label>Cadence<select value={kind} onChange={event => { setKind(event.target.value as "daily" | "weekly"); createKey.current = ""; }}>
            <option value="daily">Daily</option><option value="weekly">Selected weekdays</option>
          </select></label>
          {kind === "weekly" && <fieldset><legend>Weekdays</legend><div className="cw-agent-meta">{DAYS.map(day =>
            <label key={day}><input type="checkbox" checked={weekdays.includes(day)} onChange={event => {
              setWeekdays(previous => event.target.checked ? [...previous, day] : previous.filter(value => value !== day)); createKey.current = "";
            }} /> {day.toUpperCase()}</label>)}</div></fieldset>}
          <label>Local time<input type="time" required value={at} onChange={event => { setAt(event.target.value); createKey.current = ""; }} /></label>
          <label>Timezone<input required maxLength={64} value={timezone} onChange={event => { setTimezone(event.target.value); createKey.current = ""; }} /></label>
          <label><input type="checkbox" checked={quiet} onChange={event => { setQuiet(event.target.checked); createKey.current = ""; }} /> Delay in-app notifications during 22:00–07:00 quiet hours</label>
          <button className="cw-primary" type="submit" disabled={Boolean(busy) || !selectedGoal || (kind === "weekly" && weekdays.length === 0)}>{busy === "create" ? "Saving…" : "Create automation"}<span aria-hidden="true">↗</span></button>
          <p className="cw-fineprint">A schedule never grants email, calendar, purchase, or provider authority. Consequential actions still use the separate approval boundary.</p>
        </form>
      </section>
      <div className="cw-output-column">
        <div className="cw-history-title"><h2>Automations</h2></div>
        {automations.length === 0 ? <section className="cw-empty"><h2>No automation yet.</h2><p>Create one from an active goal.</p></section> :
        <div className="cw-history"><ul>{automations.map(item => <li key={item.id}><div className="cw-agent-run">
          <strong>{goals.find(goal => goal.id === item.goal_id)?.objective ?? "Persistent goal"}</strong>
          <p>{item.schedule.kind} · {String(item.schedule.hour).padStart(2, "0")}:{String(item.schedule.minute).padStart(2, "0")} · {item.timezone}</p>
          <div className="cw-agent-meta"><span>{item.state}</span><span>revision {item.revision}</span><span>{item.schedule_applied_revision === item.revision ? "Temporal reconciled" : "reconciliation pending"}</span>{item.schedule_error_code && <span>{item.schedule_error_code}</span>}</div>
          <div>{item.state === "active" && <button className="cw-secondary" disabled={Boolean(busy)} onClick={() => transition(item, "pause")}>Pause</button>}
            {item.state === "paused" && <button className="cw-secondary" disabled={Boolean(busy)} onClick={() => transition(item, "resume")}>Resume</button>}
            {item.state !== "cancelled" && <button className="cw-text-button" disabled={Boolean(busy)} onClick={() => transition(item, "cancel")}>Cancel</button>}</div>
        </div></li>)}</ul></div>}
        <div className="cw-history-title"><h2>Notifications</h2></div>
        {notifications.length === 0 ? <p className="cw-fineprint">No delivered automation notifications yet.</p> :
        <div className="cw-history"><ul>{notifications.map(item => <li key={item.id}><button type="button" onClick={() => markRead(item)}><div><strong>{item.title}</strong><small>{item.message} · {new Date(item.created_at).toLocaleString()} · {item.state}</small></div></button></li>)}</ul></div>}
      </div>
    </div>}
  </section>;
}
