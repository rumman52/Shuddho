import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  CoworkerClient,
  type AgentActionProposal,
  type AgentRun,
  type ConnectedAccount,
  type ExternalAction,
  type SourceDocument,
} from "./client";

const stateLabel: Record<AgentRun["state"], string> = {
  queued: "Queued",
  planning: "Planning",
  running: "Running",
  awaiting_approval: "Waiting for approval",
  completed: "Completed",
  failed: "Could not finish",
  cancelled: "Cancelled",
};

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "This Agent request could not finish.";

const proposalTitle = (proposal: AgentActionProposal) =>
  proposal.payload.kind === "email_send"
    ? proposal.payload.subject
    : proposal.payload.title;

const proposalCapability = (proposal: AgentActionProposal): "email" | "calendar" =>
  proposal.payload.kind === "email_send" ? "email" : "calendar";

export default function AgentWorkspace({
  client,
  documents,
  reviewAction,
  openActions,
}: {
  client: CoworkerClient;
  documents: SourceDocument[];
  reviewAction: (action: ExternalAction) => void;
  openActions: () => void;
}) {
  const [enabled, setEnabled] = useState(false);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [connections, setConnections] = useState<ConnectedAccount[]>([]);
  const [goal, setGoal] = useState("");
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [language, setLanguage] = useState("en");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const submission = useRef<{ fingerprint: string; key: string }>();

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    Promise.all([
      client.agentTools(controller.signal),
      client.agentRuns(controller.signal),
      client.connections(controller.signal),
    ]).then(([tools, history, accounts]) => {
      if (controller.signal.aborted) return;
      setEnabled(tools.enabled);
      setRuns(history.runs);
      setConnections(accounts.connections.filter(item => item.active));
      setRun(current => current ?? history.runs[0] ?? null);
    }).catch(failure => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    });
    return () => controller.abort();
  }, [client, reload]);

  useEffect(() => {
    if (!run || ["completed", "failed", "cancelled"].includes(run.state)) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await client.agentRun(run.id, controller.signal);
        if (controller.signal.aborted) return;
        setRun(next);
        setRuns(previous => [next, ...previous.filter(item => item.id !== next.id)]);
      } catch (failure) {
        if (!controller.signal.aborted) setError(errorMessage(failure));
      }
      if (!controller.signal.aborted && !["completed", "failed", "cancelled"].includes(run.state)) {
        timer = setTimeout(poll, 2200);
      }
    };
    timer = setTimeout(poll, 700);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [client, run?.id, run?.state]);

  async function perform(name: string, operation: () => Promise<void>) {
    if (busy) return;
    setBusy(name);
    setError("");
    try { await operation(); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(""); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const input = {
      goal,
      document_ids: selectedDocs,
      action_ids: [],
      memory_namespaces: [],
      output_language: language,
    };
    const fingerprint = JSON.stringify(input);
    if (submission.current?.fingerprint !== fingerprint) {
      submission.current = { fingerprint, key: crypto.randomUUID() };
    }
    await perform("create", async () => {
      const next = await client.createAgentRun(input, submission.current!.key);
      setRun(next);
      setRuns(previous => [next, ...previous.filter(item => item.id !== next.id)]);
    });
  }

  async function refreshRun() {
    if (!run) return;
    await perform("refresh", async () => {
      const next = await client.agentRun(run.id);
      setRun(next);
      setRuns(previous => [next, ...previous.filter(item => item.id !== next.id)]);
    });
  }

  function matchingConnections(proposal: AgentActionProposal) {
    const capability = proposalCapability(proposal);
    return connections.filter(item => item.capability === capability && item.active);
  }

  async function promote(proposal: AgentActionProposal, connectionId: string) {
    await perform("promote:" + proposal.id, async () => {
      const action = await client.promoteActionProposal(
        run!.id,
        proposal.id,
        proposal.proposal_hash,
        connectionId,
      );
      const next = await client.agentRun(run!.id);
      setRun(next);
      setRuns(previous => [next, ...previous.filter(item => item.id !== next.id)]);
      reviewAction(action);
    });
  }

  async function dismiss(proposal: AgentActionProposal) {
    await perform("dismiss:" + proposal.id, async () => {
      await client.dismissActionProposal(run!.id, proposal.id, proposal.proposal_hash);
      await refreshRun();
    });
  }

  return <section className="cw-agent" aria-label="Agent workspace">
    <div className="cw-action-intro">
      <span className="cw-eyebrow">Bounded Agent</span>
      <h2>Plan the work. Keep the authority.</h2>
      <p>The Agent can plan tasks and suggest inert email or calendar actions. You choose the account, promote the exact proposal, and approve the final preview separately.</p>
    </div>
    {error && <p className="cw-error" role="alert">{error}</p>}
    {!enabled && <p className="cw-notice">Agent runs are not enabled in this workspace yet.</p>}
    <div className="cw-layout">
      <section className="cw-compose" aria-label="Create an Agent run">
        <div className="cw-card-title"><span className="cw-step-number">01</span><div><h2>Give the Agent a goal</h2><p>Describe the outcome. It stays inside the registered tool set.</p></div></div>
        <form onSubmit={submit}>
          <label>Goal<textarea dir="auto" rows={7} minLength={3} maxLength={4000} required value={goal} onChange={event => setGoal(event.target.value)} placeholder="For example, draft a project update and suggest an email to recipient@example.org with the exact subject and message…" /></label>
          {documents.length > 0 && <fieldset className="cw-agent-files"><legend>Owned source files (optional)</legend>{documents.slice(0, 20).map(document => <label key={document.id}><input type="checkbox" checked={selectedDocs.includes(document.id)} disabled={!selectedDocs.includes(document.id) && selectedDocs.length >= 5} onChange={event => setSelectedDocs(previous => event.target.checked ? [...previous, document.id] : previous.filter(id => id !== document.id))} /><span>{document.filename}</span></label>)}</fieldset>}
          <label>Output language<input value={language} onChange={event => setLanguage(event.target.value)} pattern="(auto|[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*)" maxLength={35} required /></label>
          <button className="cw-primary" disabled={!enabled || Boolean(busy) || goal.trim().length < 3}>{busy === "create" ? "Starting Agent…" : "Start bounded Agent run"}<span aria-hidden="true">↗</span></button>
          <p className="cw-fineprint">Starting a run does not approve or execute an external action.</p>
        </form>
      </section>
      <div className="cw-output-column">
        {run ? <section className="cw-agent-run" aria-label="Agent run details">
          <div className="cw-history-title"><div><span className="cw-eyebrow">02 · Run</span><h2 dir="auto">{run.goal}</h2></div><button className="cw-text-button" disabled={Boolean(busy)} onClick={() => void refreshRun()}>Refresh</button></div>
          <p role="status"><span className={`cw-status cw-status-${run.state}`}>{stateLabel[run.state]}</span> {run.message}</p>
          <div className="cw-agent-meta"><span>Planner: {run.planner_mode ?? "pending"}</span><span>Calls: {run.planner_calls}</span><span>Tokens: {run.planner_tokens}</span></div>
          {run.steps.length > 0 && <ol className="cw-agent-steps">{run.steps.map(step => <li key={step.id}><span>{step.ordinal}</span><div><strong>{step.tool ?? "Planning"}</strong><small>{step.state}{step.depends_on.length ? ` · after ${step.depends_on.join(", ")}` : ""}</small></div></li>)}</ol>}
          {run.action_proposals.length > 0 && <section className="cw-proposals" aria-label="Agent action proposals">
            <div><span className="cw-eyebrow">Suggested actions</span><h3>Nothing here is executable yet.</h3><p>Review the exact model suggestion, choose one of your connected accounts, then promote it into the normal immutable action preview.</p></div>
            {run.action_proposals.map(proposal => {
              const accounts = matchingConnections(proposal);
              const selected = accounts[0]?.id ?? "";
              const payload = proposal.payload;
              return <article className="cw-proposal-card" key={proposal.id}>
                <div className="cw-proposal-heading"><div><strong dir="auto">{proposalTitle(proposal)}</strong><small>{proposal.kind === "email_send" ? "Email suggestion" : "Calendar suggestion"} · {proposal.state}</small></div><code>{proposal.proposal_hash.slice(0, 12)}…</code></div>
                <p className="cw-proposal-rationale" dir="auto">{proposal.rationale}</p>
                <dl className="cw-action-details">
                  {payload.kind === "email_send" ? <>
                    <dt>To</dt><dd>{payload.to.join(", ")}</dd><dt>Subject</dt><dd dir="auto">{payload.subject}</dd><dt>Message</dt><dd dir="auto">{payload.body}</dd>
                  </> : <>
                    <dt>When</dt><dd>{payload.start_at} → {payload.end_at}</dd><dt>Zone</dt><dd>{payload.time_zone}</dd><dt>Guests</dt><dd>{payload.attendees.join(", ") || "None"}</dd><dt>Details</dt><dd dir="auto">{payload.description}</dd>
                  </>}
                </dl>
                {proposal.state === "suggested" ? accounts.length ? <ProposalControls proposal={proposal} accounts={accounts} busy={busy} promote={promote} dismiss={dismiss} /> : <div className="cw-proposal-controls"><p className="cw-fineprint">Connect a matching {proposalCapability(proposal)} account before promotion.</p><button className="cw-secondary" type="button" onClick={openActions}>Open Email & calendar</button><button className="cw-text-button" type="button" disabled={Boolean(busy)} onClick={() => void dismiss(proposal)}>Dismiss suggestion</button></div> : proposal.state === "promoted" && proposal.promoted_action_id ? <button className="cw-secondary" type="button" onClick={() => void perform("open:" + proposal.id, async () => reviewAction(await client.action(proposal.promoted_action_id!)))}>Review final action</button> : null}
              </article>;
            })}
          </section>}
          {!["completed", "failed", "cancelled"].includes(run.state) && <button className="cw-text-button cw-cancel" disabled={Boolean(busy)} onClick={() => void perform("cancel", async () => { const next = await client.cancelAgentRun(run.id); setRun(next); })}>Cancel Agent run</button>}
        </section> : <section className="cw-empty"><span className="cw-empty-mark" aria-hidden="true">✦</span><span className="cw-eyebrow">Bounded by design</span><h2>Give the Agent a goal.</h2><p>It can plan registered tools and suggest inert actions, while provider identity, promotion, approval, and execution stay under your control.</p></section>}
        {runs.length > 0 && <section className="cw-history"><div className="cw-history-title"><h2>Recent Agent runs</h2><button className="cw-text-button" onClick={() => setReload(value => value + 1)}>Refresh</button></div><ul>{runs.map(item => <li key={item.id}><button aria-pressed={run?.id === item.id} onClick={() => setRun(item)}><div><strong dir="auto">{item.goal}</strong><small>{item.planner_mode ?? "pending"} · {new Date(item.created_at).toLocaleString()}</small></div><span className={`cw-status cw-status-${item.state}`}>{stateLabel[item.state]}</span></button></li>)}</ul></section>}
      </div>
    </div>
  </section>;
}

function ProposalControls({
  proposal,
  accounts,
  busy,
  promote,
  dismiss,
}: {
  proposal: AgentActionProposal;
  accounts: ConnectedAccount[];
  busy: string;
  promote: (proposal: AgentActionProposal, connectionId: string) => Promise<void>;
  dismiss: (proposal: AgentActionProposal) => Promise<void>;
}) {
  const [connectionId, setConnectionId] = useState(accounts[0]?.id ?? "");
  return <div className="cw-proposal-controls">
    <label>Connected account<select aria-label={`Account for ${proposalTitle(proposal)}`} value={connectionId} onChange={event => setConnectionId(event.target.value)} disabled={Boolean(busy)}>{accounts.map(account => <option value={account.id} key={account.id}>{account.email} · {account.provider}</option>)}</select></label>
    <p className="cw-fineprint">The model did not choose this account. Promotion creates a separate immutable preview and still does not approve it.</p>
    <div><button className="cw-primary" type="button" disabled={!connectionId || Boolean(busy)} onClick={() => void promote(proposal, connectionId)}>{busy === "promote:" + proposal.id ? "Promoting…" : "Promote exact proposal"}</button><button className="cw-text-button" type="button" disabled={Boolean(busy)} onClick={() => void dismiss(proposal)}>Dismiss suggestion</button></div>
  </div>;
}
