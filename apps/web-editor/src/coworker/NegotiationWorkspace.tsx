import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  CoworkerClient,
  type ConnectedAccount,
  type NegotiationCase,
  type NegotiationLimit,
  type NegotiationOfferTerm,
} from "./client";

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "This negotiation update could not be completed.";

const parseLimits = (value: string): NegotiationLimit[] => {
  if (!value.trim()) return [];
  return value.split("\n").map((line, index) => {
    const parts = line.split("|").map(item => item.trim());
    if (parts.length !== 3 || !["at_most", "at_least", "exact", "avoid"].includes(parts[0]) || !parts[1] || !parts[2]) {
      throw new Error(`Limit line ${index + 1} must use: at_most | Price | USD 5,000`);
    }
    return {
      comparison: parts[0] as NegotiationLimit["comparison"],
      name: parts[1],
      value: parts[2],
    };
  });
};

const limitsText = (limits: NegotiationLimit[]) =>
  limits.map(item => `${item.comparison} | ${item.name} | ${item.value}`).join("\n");

const parseTerms = (value: string): NegotiationOfferTerm[] => {
  if (!value.trim()) return [];
  return value.split("\n").map((line, index) => {
    const separator = line.indexOf("=");
    const name = line.slice(0, separator).trim();
    const termValue = separator >= 0 ? line.slice(separator + 1).trim() : "";
    if (separator < 1 || !name || !termValue) {
      throw new Error(`Offer term line ${index + 1} must use: Price=USD 5,000`);
    }
    return { name, value: termValue };
  });
};

export default function NegotiationWorkspace({ client }: { client: CoworkerClient }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [cases, setCases] = useState<NegotiationCase[]>([]);
  const [connections, setConnections] = useState<ConnectedAccount[]>([]);
  const [operations, setOperations] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [connectionId, setConnectionId] = useState("");
  const [counterpartyName, setCounterpartyName] = useState("");
  const [counterpartyAddress, setCounterpartyAddress] = useState("");
  const [subject, setSubject] = useState("");
  const [objective, setObjective] = useState("");
  const [limits, setLimits] = useState("");

  const [editSubject, setEditSubject] = useState("");
  const [editObjective, setEditObjective] = useState("");
  const [editLimits, setEditLimits] = useState("");

  const [offerDirection, setOfferDirection] = useState<"ours" | "theirs">("theirs");
  const [offerKind, setOfferKind] = useState<"proposal" | "counteroffer" | "commitment" | "response">("counteroffer");
  const [offerSummary, setOfferSummary] = useState("");
  const [offerTerms, setOfferTerms] = useState("");

  const selected = cases.find(item => item.id === selectedId) ?? cases[0] ?? null;
  const eligibleConnections = useMemo(
    () => connections.filter(item =>
      item.active
      && item.capability === "email"
      && (item.provider === "google" || item.provider === "microsoft")
      && operations.includes(`${item.provider}:negotiation_commitment_email`)
    ),
    [connections, operations],
  );

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      client.negotiations(controller.signal),
      client.connections(controller.signal),
    ]).then(([saved, connectionState]) => {
      if (controller.signal.aborted) return;
      setEnabled(saved.enabled);
      setCases(saved.cases);
      setConnections(connectionState.connections);
      setOperations(connectionState.transaction_operations ?? []);
      setSelectedId(current => current || saved.cases[0]?.id || "");
    }).catch(failure => {
      if (!controller.signal.aborted) {
        setEnabled(false);
        setError(errorMessage(failure));
      }
    });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!selected) return;
    setSelectedId(selected.id);
    setEditSubject(selected.subject);
    setEditObjective(selected.objective);
    setEditLimits(limitsText(selected.limits));
  }, [selected?.id, selected?.revision]);

  function replaceCase(value: NegotiationCase) {
    setCases(previous => [value, ...previous.filter(item => item.id !== value.id)]
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
    setSelectedId(value.id);
  }

  async function run(name: string, operation: () => Promise<void>) {
    if (busy) return;
    setBusy(name);
    setError("");
    setNotice("");
    try {
      await operation();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy("");
    }
  }

  async function createCase(event: FormEvent) {
    event.preventDefault();
    await run("create", async () => {
      const value = await client.createNegotiation({
        connection_id: connectionId,
        counterparty_name: counterpartyName,
        counterparty_address: counterpartyAddress,
        subject,
        objective,
        limits: parseLimits(limits),
      }, crypto.randomUUID());
      replaceCase(value);
      setCounterpartyName("");
      setCounterpartyAddress("");
      setSubject("");
      setObjective("");
      setLimits("");
      setNotice("Negotiation case created. Provider execution still requires a separate approved action.");
    });
  }

  async function saveCase() {
    if (!selected) return;
    await run("save", async () => {
      replaceCase(await client.updateNegotiation(selected.id, selected.revision, {
        subject: editSubject,
        objective: editObjective,
        limits: parseLimits(editLimits),
      }));
      setNotice("Negotiation strategy and limits updated. Counterparty scope did not change.");
    });
  }

  async function transition(state: "active" | "paused" | "closed" | "cancelled") {
    if (!selected) return;
    await run(state, async () => {
      replaceCase(await client.transitionNegotiation(selected.id, selected.revision, state));
      setNotice(`Negotiation case is now ${state}.`);
    });
  }

  async function addOffer(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    await run("offer", async () => {
      await client.appendNegotiationOffer(selected.id, {
        direction: offerDirection,
        kind: offerKind,
        summary: offerSummary,
        terms: parseTerms(offerTerms),
        occurred_at: new Date().toISOString(),
      }, crypto.randomUUID());
      replaceCase(await client.negotiation(selected.id));
      setOfferSummary("");
      setOfferTerms("");
      setNotice("Offer history recorded. This did not send anything externally.");
    });
  }

  if (enabled === null) return <section className="cw-card"><p>Loading negotiation cases…</p></section>;
  if (!enabled) return <section className="cw-card"><h2>Negotiations</h2><p>Negotiation case tracking is not enabled in this deployment.</p>{error && <p className="cw-error">{error}</p>}</section>;

  return <section className="cw-card" aria-label="Negotiation cases">
    <div className="cw-card-title"><div><span className="cw-eyebrow">PA-09</span><h2>Negotiations</h2><p>Keep counterparty scope, user limits, and offer history separate from execution authority.</p></div></div>
    {error && <p className="cw-error" role="alert">{error}</p>}
    {notice && <p className="cw-notice" role="status">{notice}</p>}

    <form onSubmit={createCase}>
      <h3>New case</h3>
      <label>Email connection<select value={connectionId} required onChange={event => setConnectionId(event.target.value)}>
        <option value="">Choose a qualified connection</option>
        {eligibleConnections.map(item => <option key={item.id} value={item.id}>{item.provider} · {item.email}</option>)}
      </select></label>
      <label>Counterparty name<input value={counterpartyName} required maxLength={300} onChange={event => setCounterpartyName(event.target.value)} /></label>
      <label>Counterparty email<input dir="ltr" value={counterpartyAddress} required maxLength={254} onChange={event => setCounterpartyAddress(event.target.value)} /></label>
      <label>Subject<input value={subject} required maxLength={300} onChange={event => setSubject(event.target.value)} /></label>
      <label>Objective<textarea rows={3} value={objective} required maxLength={4000} onChange={event => setObjective(event.target.value)} /></label>
      <label>User limits<textarea rows={4} value={limits} onChange={event => setLimits(event.target.value)} placeholder={"at_most | Price | USD 5,000\nat_most | Delivery | 30 days"} /><small>One limit per line. Comparisons: at_most, at_least, exact, avoid.</small></label>
      <button className="cw-primary" type="submit" disabled={Boolean(busy) || !connectionId}>Create case</button>
    </form>

    {cases.length > 0 && <label>Saved cases<select value={selected?.id ?? ""} onChange={event => setSelectedId(event.target.value)}>
      {cases.map(item => <option key={item.id} value={item.id}>{item.counterparty_name} · {item.subject} · {item.state}</option>)}
    </select></label>}

    {selected && <div>
      <h3>Case scope</h3>
      <dl className="cw-action-details">
        <dt>Provider</dt><dd>{selected.provider}</dd>
        <dt>Counterparty</dt><dd>{selected.counterparty_name}</dd>
        <dt>Address</dt><dd>{selected.counterparty_address}</dd>
        <dt>State</dt><dd>{selected.state}</dd>
        <dt>Revision</dt><dd>{selected.revision}</dd>
      </dl>
      <p className="cw-fineprint">Provider, connection, and counterparty address are immutable. Changing them requires a new case.</p>

      {selected.state !== "closed" && selected.state !== "cancelled" && <>
        <label>Subject<input value={editSubject} maxLength={300} onChange={event => setEditSubject(event.target.value)} /></label>
        <label>Objective<textarea rows={3} value={editObjective} maxLength={4000} onChange={event => setEditObjective(event.target.value)} /></label>
        <label>User limits<textarea rows={4} value={editLimits} onChange={event => setEditLimits(event.target.value)} /></label>
        <button className="cw-secondary" type="button" disabled={Boolean(busy)} onClick={saveCase}>Save strategy</button>
        {selected.state === "active"
          ? <button className="cw-secondary" type="button" disabled={Boolean(busy)} onClick={() => transition("paused")}>Pause</button>
          : <button className="cw-secondary" type="button" disabled={Boolean(busy)} onClick={() => transition("active")}>Resume</button>}
        <button className="cw-secondary" type="button" disabled={Boolean(busy)} onClick={() => transition("closed")}>Close</button>
        <button className="cw-text-button" type="button" disabled={Boolean(busy)} onClick={() => transition("cancelled")}>Cancel case</button>
      </>}

      <h3>Offer history</h3>
      {selected.offers.length === 0 ? <p>No offers recorded yet.</p> : <ol>
        {selected.offers.map(item => <li key={item.id}>
          <strong>#{item.sequence} · {item.direction} · {item.kind}</strong>
          <p>{item.summary}</p>
          {item.terms.length > 0 && <ul>{item.terms.map(term => <li key={term.name}><strong>{term.name}:</strong> {term.value}</li>)}</ul>}
          <small>{new Date(item.occurred_at).toLocaleString()}{item.external_action_id ? " · confirmed PA-09 action linked" : ""}</small>
        </li>)}
      </ol>}

      {selected.state === "active" && <form onSubmit={addOffer}>
        <label>Direction<select value={offerDirection} onChange={event => setOfferDirection(event.target.value as "ours" | "theirs")}>
          <option value="theirs">Counterparty</option><option value="ours">Ours</option>
        </select></label>
        <label>Type<select value={offerKind} onChange={event => setOfferKind(event.target.value as typeof offerKind)}>
          <option value="proposal">Proposal</option><option value="counteroffer">Counteroffer</option><option value="response">Response</option>
        </select></label>
        <label>Summary<textarea rows={3} required maxLength={4000} value={offerSummary} onChange={event => setOfferSummary(event.target.value)} /></label>
        <label>Terms<textarea rows={4} value={offerTerms} onChange={event => setOfferTerms(event.target.value)} placeholder={"Price=USD 5,100\nDelivery=28 days"} /><small>One term per line as Name=Value.</small></label>
        <button className="cw-secondary" type="submit" disabled={Boolean(busy)}>Record offer</button>
        <p className="cw-fineprint">Recording history never sends a message. Binding commitments still require the existing immutable action preview and explicit approval.</p>
      </form>}
    </div>}
  </section>;
}
