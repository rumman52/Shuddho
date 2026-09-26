import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoworkerClient, type PersonalGoal } from "./client";

const errorMessage = (error: unknown) => error instanceof Error ? error.message : "This goal action could not finish.";

function lines(value: string) {
  return value.split("\n").map(item => item.trim()).filter(Boolean).slice(0, 10);
}

export default function GoalWorkspace({ client, openAgent }: { client: CoworkerClient; openAgent: () => void }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [goals, setGoals] = useState<PersonalGoal[]>([]);
  const [selected, setSelected] = useState("");
  const [objective, setObjective] = useState("");
  const [criteria, setCriteria] = useState("");
  const [constraints, setConstraints] = useState("");
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [deadline, setDeadline] = useState("");
  const [maxRuns, setMaxRuns] = useState(20);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const createKey = useRef("");

  const current = goals.find(goal => goal.id === selected) ?? null;

  useEffect(() => {
    const controller = new AbortController();
    client.goals(controller.signal).then(result => {
      setEnabled(result.enabled);
      setGoals(result.goals);
      setSelected(value => result.goals.some(goal => goal.id === value) ? value : result.goals[0]?.id ?? "");
    }).catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, [client]);

  function replaceGoal(next: PersonalGoal) {
    setGoals(previous => [next, ...previous.filter(goal => goal.id !== next.id)].sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
    setSelected(next.id);
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!createKey.current) createKey.current = crypto.randomUUID();
    setBusy("create"); setError(""); setNotice("");
    try {
      const next = await client.createGoal({
        objective, success_criteria: lines(criteria), constraints: lines(constraints),
        deadline_at: deadline ? new Date(deadline).toISOString() : null, timezone, state: "active",
        milestones: [], budget: { max_runs: maxRuns, max_planner_tokens: null },
        authorized_resources: [], next_review_at: null,
      }, createKey.current);
      replaceGoal(next);
      setObjective(""); setCriteria(""); setConstraints(""); setDeadline(""); setMaxRuns(20);
      createKey.current = "";
      setNotice("Goal created. It will only do work when a bounded run or future automation wakes it.");
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(""); }
  }

  async function transition(action: "pause" | "resume" | "cancel") {
    if (!current || busy) return;
    setBusy(action); setError(""); setNotice("");
    try { replaceGoal(await client.transitionGoal(current.id, current.revision, action)); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(""); }
  }

  async function runNow() {
    if (!current || busy) return;
    setBusy("run"); setError(""); setNotice("");
    try {
      const run = await client.runGoal(current.id, current.revision, "en", crypto.randomUUID());
      replaceGoal(await client.goal(current.id));
      setNotice(`Bounded run ${run.id.slice(0, 8)} started from goal revision ${run.persistent_goal_revision}. You can inspect it in Agent.`);
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(""); }
  }

  async function reviseObjective() {
    if (!current || busy) return;
    const revised = window.prompt("Revise the goal objective. Existing runs keep their accepted revision.", current.objective)?.trim();
    if (!revised || revised === current.objective) return;
    setBusy("revise"); setError(""); setNotice("");
    try {
      replaceGoal(await client.updateGoal(current.id, current.revision, { objective: revised }));
      setNotice("Goal revision saved. Historical Agent runs were not changed.");
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(""); }
  }

  if (enabled === null && !error) return <p className="cw-loading" role="status">Loading persistent goals…</p>;

  return <section className="cw-agent cw-goals" aria-label="Persistent goals">
    <div className="cw-action-intro">
      <span className="cw-eyebrow">Personal agent · PA-01</span>
      <h2>Goals persist. Runs stay bounded.</h2>
      <p>A goal can live for days or weeks. Each execution remains a finite Agent run tied to the exact goal revision it accepted.</p>
    </div>
    {error && <p className="cw-error" role="alert">{error}</p>}
    {notice && <p className="cw-notice" role="status">{notice} {notice.includes("Bounded run") && <button type="button" className="cw-text-button" onClick={openAgent}>Open Agent</button>}</p>}
    {enabled === false ? <div className="cw-agent-run"><strong>Persistent goals are disabled.</strong><p className="cw-fineprint">The production-safe default is off until migrations, CI and controlled staging are verified.</p></div> :
    <div className="cw-layout">
      <section className="cw-compose">
        <div className="cw-card-title"><span className="cw-step-number">01</span><div><h2>Create a persistent goal</h2><p>Describe the outcome, not an endless chat session.</p></div></div>
        <form onSubmit={create}>
          <label>Objective<textarea rows={4} minLength={3} maxLength={4000} required value={objective} onChange={event => { setObjective(event.target.value); createKey.current = ""; }} placeholder="Prepare for my final exams over the next three weeks." /></label>
          <label>Success criteria <small>One per line</small><textarea rows={3} maxLength={5000} value={criteria} onChange={event => { setCriteria(event.target.value); createKey.current = ""; }} /></label>
          <label>Constraints <small>One per line</small><textarea rows={3} maxLength={5000} value={constraints} onChange={event => { setConstraints(event.target.value); createKey.current = ""; }} /></label>
          <label>Timezone<input value={timezone} maxLength={64} required onChange={event => { setTimezone(event.target.value); createKey.current = ""; }} /></label>
          <label>Deadline (optional)<input type="datetime-local" value={deadline} onChange={event => { setDeadline(event.target.value); createKey.current = ""; }} /></label>
          <label>Maximum bounded runs<input type="number" min={1} max={1000} value={maxRuns} onChange={event => { setMaxRuns(Number(event.target.value)); createKey.current = ""; }} /></label>
          <button className="cw-primary" type="submit" disabled={Boolean(busy) || !objective.trim()}>{busy === "create" ? "Creating…" : "Create goal"}<span aria-hidden="true">↗</span></button>
          <p className="cw-fineprint">Creating a goal does not send email, mutate calendars, connect accounts or grant provider permissions.</p>
        </form>
      </section>
      <div className="cw-output-column">
        {goals.length === 0 ? <section className="cw-empty"><span className="cw-empty-mark" aria-hidden="true">◎</span><span className="cw-eyebrow">Persistent goals</span><h2>No active goal yet.</h2><p>Create one to preserve an objective across bounded Agent runs.</p></section> :
        <>
          <div className="cw-history-title"><h2>Saved goals</h2></div>
          <div className="cw-history"><ul>{goals.map(goal => <li key={goal.id}><button type="button" aria-pressed={goal.id === selected} onClick={() => setSelected(goal.id)}><div><strong>{goal.objective}</strong><small>Revision {goal.revision} · {goal.state} · {goal.run_links.length} linked run{goal.run_links.length === 1 ? "" : "s"}</small></div></button></li>)}</ul></div>
          {current && <article className="cw-agent-run">
            <span className="cw-eyebrow">Revision {current.revision}</span>
            <h2>{current.objective}</h2>
            <div className="cw-agent-meta"><span>{current.state}</span><span>{current.timezone}</span><span>{current.budget.max_runs} max runs</span>{current.deadline_at && <span>Due {new Date(current.deadline_at).toLocaleString()}</span>}</div>
            {current.success_criteria.length > 0 && <><strong>Success criteria</strong><ul>{current.success_criteria.map(item => <li key={item}>{item}</li>)}</ul></>}
            <div className="cw-proposal-controls"><div>
              <button type="button" className="cw-primary" disabled={Boolean(busy) || current.state !== "active"} onClick={runNow}>{busy === "run" ? "Starting…" : "Run bounded work now"}</button>
              <button type="button" className="cw-secondary" disabled={Boolean(busy) || ["cancelled", "archived"].includes(current.state)} onClick={reviseObjective}>Revise</button>
              {current.state === "active" && <button type="button" className="cw-secondary" disabled={Boolean(busy)} onClick={() => transition("pause")}>Pause</button>}
              {current.state === "paused" && <button type="button" className="cw-secondary" disabled={Boolean(busy)} onClick={() => transition("resume")}>Resume</button>}
              {!["cancelled", "completed", "archived"].includes(current.state) && <button type="button" className="cw-text-button" disabled={Boolean(busy)} onClick={() => transition("cancel")}>Cancel goal</button>}
            </div></div>
            {current.run_links.length > 0 && <div className="cw-proposals"><h3>Bounded run history</h3>{current.run_links.map(run => <p key={run.run_id}><code>{run.run_id.slice(0, 8)}</code> · goal revision {run.goal_revision} · {run.state}</p>)}</div>}
          </article>}
        </>}
      </div>
    </div>}
  </section>;
}
