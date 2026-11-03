import { useEffect, useState } from "react";
import { type AgentRun, type CoworkerClient } from "./client";

const states: Record<string, string> = {
  queued: "Queued", planning: "Planning", running: "Working", awaiting_approval: "Approval needed",
  needs_input: "Your input is needed", blocked: "Blocked", completed: "Completed", failed: "Could not finish", cancelled: "Cancelled",
  partially_completed: "Partially completed", waiting_for_user: "Your input is needed", waiting_for_approval: "Approval needed",
};
const stopped = new Set(["completed", "failed", "cancelled", "needs_input", "blocked"]);

/** Read-only projection of an owned run. Loading or retrying never starts work. */
export default function ConversationRunStatus({ client, runId, eager = true }: { client: CoworkerClient; runId: string; eager?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const shouldLoad = eager || expanded;
  const [snapshot, setSnapshot] = useState<{ id: string; run: AgentRun | null; error: string }>({ id: runId, run: null, error: "" });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!shouldLoad) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setSnapshot({ id: runId, run: null, error: "" });
    async function load() {
      try {
        const run = await client.agentRun(runId, controller.signal);
        if (controller.signal.aborted) return;
        if (run.id !== runId) throw new Error("Agent response does not match this conversation's run.");
        setSnapshot({ id: runId, run, error: "" });
        if (!stopped.has(run.state)) timer = setTimeout(() => { void load(); }, 5000);
      } catch (cause) {
        if (!controller.signal.aborted) setSnapshot({ id: runId, run: null,
          error: cause instanceof Error ? cause.message : "Agent progress could not be loaded." });
      }
    }
    void load();
    return () => { controller.abort(); if (timer !== undefined) clearTimeout(timer); };
  }, [client, runId, revision, shouldLoad]);
  if (!shouldLoad) return <button type="button" className="cw-text-button" aria-label="Show coworker progress"
    onClick={() => setExpanded(true)}>Show coworker progress</button>;
  const run = snapshot.id === runId ? snapshot.run : null;
  const error = snapshot.id === runId ? snapshot.error : "";
  const state = run?.final_state ?? run?.state;
  return <section className="rukh-inline-run" aria-label="Coworker progress">
    <div className="rukh-inline-run-heading"><span className="rukh-chat-mark" aria-hidden="true">R</span><strong>Rukh AI</strong>
      {state && <span className={`cw-status cw-status-${run?.state}`} role="status">{states[state] ?? state.replace(/_/g, " ")}</span>}
    </div>
    {error ? <><p className="cw-error" role="alert">{error}</p><button type="button" className="cw-text-button" aria-label="Retry Agent progress" onClick={() => setRevision(value => value + 1)}>Retry</button></> :
      run ? <>
        <p className="rukh-run-message" dir="auto">{run.message}</p>
        {run.plan?.length > 0 && <details><summary>Plan · {run.plan.length} steps</summary><ol>{run.plan.map(step =>
          <li key={step.step_id}><span>{step.tool ?? "Plan step"}</span><small>{step.state.replace(/_/g, " ")}</small></li>)}</ol></details>}
        {run.tool_results?.length > 0 && <details><summary>Tool results · {run.tool_results.length}</summary>
          {run.tool_results.map(result => <article key={result.invocation_id}><strong>{result.tool}</strong><small>{result.status}</small>
            <pre dir="auto">{JSON.stringify(result.summary, null, 2)}</pre></article>)}
        </details>}
      </> : <p className="rukh-muted" role="status">Loading Agent progress…</p>}
  </section>;
}
