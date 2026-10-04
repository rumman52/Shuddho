import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  CoworkerClient,
  type TransactionRecord,
  type TransactionSurface,
  type TransactionTerm,
} from "./client";

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "This transaction update could not be completed.";

const parseTerms = (value: string): TransactionTerm[] => {
  const lines = value.split("\n").map(line => line.trim()).filter(Boolean);
  if (!lines.length) throw new Error("Add at least one exact term as Name=Value.");
  return lines.map((line, index) => {
    const separator = line.indexOf("=");
    const name = line.slice(0, separator).trim();
    const termValue = separator >= 0 ? line.slice(separator + 1).trim() : "";
    if (separator < 1 || !name || !termValue) {
      throw new Error(`Term line ${index + 1} must use Name=Value.`);
    }
    return { name, value: termValue };
  });
};

const integer = (value: string, label: string) => {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error(`${label} must be a non-negative whole number of minor currency units.`);
  }
  return parsed;
};

const localIso = (value: string) => {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) throw new Error("Choose a valid date and time.");
  return date.toISOString();
};

const localInput = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
};

export default function TransactionWorkspace({ client }: { client: CoworkerClient }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [transactions, setTransactions] = useState<TransactionRecord[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [surface, setSurface] = useState<TransactionSurface | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [kind, setKind] = useState("reservation");
  const [counterparty, setCounterparty] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [transactionExpiry, setTransactionExpiry] = useState("");

  const [termsText, setTermsText] = useState("");
  const [subtotal, setSubtotal] = useState("0");
  const [tax, setTax] = useState("0");
  const [fees, setFees] = useState("0");
  const [shipping, setShipping] = useState("0");
  const [discount, setDiscount] = useState("0");
  const [providerQuoteId, setProviderQuoteId] = useState("");
  const [quoteExpiry, setQuoteExpiry] = useState("");

  const selected = useMemo(
    () => transactions.find(item => item.id === selectedId) ?? transactions[0] ?? null,
    [transactions, selectedId],
  );

  async function refreshList(signal?: AbortSignal) {
    const value = await client.transactions(signal);
    setEnabled(value.enabled);
    setTransactions(value.transactions);
    setSelectedId(current => current || value.transactions[0]?.id || "");
  }

  async function refreshSurface(id: string) {
    const value = await client.transaction(id);
    setSurface(value);
    setTransactions(previous => [
      value.transaction,
      ...previous.filter(item => item.id !== value.transaction.id),
    ].sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
    setSelectedId(id);
  }

  useEffect(() => {
    const controller = new AbortController();
    refreshList(controller.signal).catch(failure => {
      if (!controller.signal.aborted) {
        setEnabled(false);
        setError(errorMessage(failure));
      }
    });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    const id = selected?.id;
    if (!id || enabled !== true) {
      setSurface(null);
      return;
    }
    const controller = new AbortController();
    client.transaction(id, controller.signal).then(value => {
      if (!controller.signal.aborted) setSurface(value);
    }).catch(failure => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    });
    return () => controller.abort();
  }, [client, enabled, selected?.id, selected?.revision]);

  useEffect(() => {
    if (!surface) return;
    setCurrency(surface.transaction.currency ?? "USD");
    if (!surface.terms) {
      setTermsText("");
      setSubtotal("0");
      setTax("0");
      setFees("0");
      setShipping("0");
      setDiscount("0");
      setProviderQuoteId("");
      setQuoteExpiry("");
      return;
    }
    setTermsText(surface.terms.terms.map(term => `${term.name}=${term.value}`).join("\n"));
    setSubtotal(String(surface.terms.price.subtotal_minor));
    setTax(String(surface.terms.price.tax_minor));
    setFees(String(surface.terms.price.fees_minor));
    setShipping(String(surface.terms.price.shipping_minor));
    setDiscount(String(surface.terms.price.discount_minor));
    setProviderQuoteId(surface.terms.provider_quote_id ?? "");
    setQuoteExpiry(localInput(surface.terms.quote_expires_at));
  }, [surface?.transaction.id, surface?.transaction.revision, surface?.terms?.terms_sha256]);

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

  async function createTransaction(event: FormEvent) {
    event.preventDefault();
    await run("create", async () => {
      const value = await client.createTransaction({
        transaction_kind: kind,
        counterparty,
        currency: currency || null,
        expires_at: transactionExpiry ? localIso(transactionExpiry) : null,
      }, crypto.randomUUID());
      setTransactions(previous => [value, ...previous.filter(item => item.id !== value.id)]);
      setSelectedId(value.id);
      setCounterparty("");
      setTransactionExpiry("");
      setNotice("Transaction draft created for review only. No provider action was created.");
    });
  }

  async function replaceTerms(event: FormEvent) {
    event.preventDefault();
    if (!surface) return;
    await run("terms", async () => {
      const subtotalMinor = integer(subtotal, "Subtotal");
      const taxMinor = integer(tax, "Tax");
      const feesMinor = integer(fees, "Fees");
      const shippingMinor = integer(shipping, "Shipping");
      const discountMinor = integer(discount, "Discount");
      const totalMinor = subtotalMinor + taxMinor + feesMinor + shippingMinor - discountMinor;
      if (totalMinor < 0) throw new Error("Discount cannot make the total negative.");
      const quotedAt = new Date().toISOString();
      const saved = await client.replaceTransactionTerms(
        surface.transaction.id,
        surface.transaction.revision,
        {
          terms: parseTerms(termsText),
          price: {
            currency: currency.toUpperCase(),
            subtotal_minor: subtotalMinor,
            tax_minor: taxMinor,
            fees_minor: feesMinor,
            shipping_minor: shippingMinor,
            discount_minor: discountMinor,
            total_minor: totalMinor,
          },
          provider_quote_id: providerQuoteId || null,
          quoted_at: quotedAt,
          quote_expires_at: localIso(quoteExpiry),
        },
      );
      setTransactions(previous => [
        saved.transaction,
        ...previous.filter(item => item.id !== saved.transaction.id),
      ]);
      await refreshSurface(saved.transaction.id);
      setNotice("Exact terms saved. Any earlier review was invalidated and a fresh review is required.");
    });
  }

  async function startReview() {
    if (!surface) return;
    await run("review", async () => {
      const value = await client.startTransactionReview(
        surface.transaction.id,
        surface.transaction.revision,
      );
      setTransactions(previous => [value, ...previous.filter(item => item.id !== value.id)]);
      await refreshSurface(value.id);
      setNotice("Review started. Verify the exact terms and hash before confirming.");
    });
  }

  async function confirmReview() {
    const current = surface;
    const terms = current?.terms;
    if (!current || !terms) return;
    await run("confirm", async () => {
      const value = await client.confirmTransactionReview(
        current.transaction.id,
        current.transaction.revision,
        terms.terms_sha256,
      );
      setTransactions(previous => [
        value.transaction,
        ...previous.filter(item => item.id !== value.transaction.id),
      ]);
      await refreshSurface(value.transaction.id);
      setNotice("Exact terms reviewed and confirmed. No external action was approved or executed.");
    });
  }

  async function cancelTransaction() {
    if (!surface) return;
    await run("cancel", async () => {
      const value = await client.cancelTransaction(
        surface.transaction.id,
        surface.transaction.revision,
      );
      setTransactions(previous => [value, ...previous.filter(item => item.id !== value.id)]);
      await refreshSurface(value.id);
      setNotice("Transaction review cancelled. No provider action occurred.");
    });
  }

  if (enabled === null) return <section className="cw-card"><p>Loading transactions…</p></section>;
  if (!enabled) return <section className="cw-card"><h2>Transactions</h2><p>Transaction review is not enabled in this deployment.</p>{error && <p className="cw-error">{error}</p>}</section>;

  const editable = surface && ["draft", "terms_ready", "awaiting_review", "awaiting_approval"].includes(surface.transaction.state);
  const cancellable = surface && !["cancelled", "expired", "confirmed", "failed", "outcome_unknown"].includes(surface.transaction.state);

  return <section className="cw-card" aria-label="Transaction review">
    <div className="cw-card-title"><div><span className="cw-eyebrow">Transactions</span><h2>Review exact transaction terms</h2><p>Business intent and human review only. Provider execution remains a separate approved ExternalAction.</p></div></div>
    {error && <p className="cw-error" role="alert">{error}</p>}
    {notice && <p className="cw-notice" role="status">{notice}</p>}

    <form onSubmit={createTransaction}>
      <h3>New review record</h3>
      <label>Transaction type<input value={kind} required pattern="[a-z][a-z0-9_]*" maxLength={40} onChange={event => setKind(event.target.value.toLowerCase())} /></label>
      <label>Counterparty<input value={counterparty} required maxLength={300} onChange={event => setCounterparty(event.target.value)} /></label>
      <label>Currency<input value={currency} required minLength={3} maxLength={3} onChange={event => setCurrency(event.target.value.toUpperCase())} /></label>
      <label>Optional transaction expiry<input type="datetime-local" value={transactionExpiry} onChange={event => setTransactionExpiry(event.target.value)} /></label>
      <button className="cw-primary" type="submit" disabled={Boolean(busy)}>Create review record</button>
      <p className="cw-fineprint">This creates an internal review record only. It cannot select a connected provider or create an external action.</p>
    </form>

    {transactions.length > 0 && <label>Saved transactions<select value={selected?.id ?? ""} onChange={event => setSelectedId(event.target.value)}>
      {transactions.map(item => <option key={item.id} value={item.id}>{item.counterparty ?? item.transaction_kind} · {item.state} · r{item.revision}</option>)}
    </select></label>}

    {surface && <div>
      <h3>Current scope</h3>
      <dl className="cw-action-details">
        <dt>Type</dt><dd>{surface.transaction.transaction_kind}</dd>
        <dt>Counterparty</dt><dd>{surface.transaction.counterparty}</dd>
        <dt>State</dt><dd>{surface.transaction.state}</dd>
        <dt>Revision</dt><dd>{surface.transaction.revision}</dd>
        <dt>Currency</dt><dd>{surface.transaction.currency ?? "Not set"}</dd>
        <dt>Execution</dt><dd>Not available in this review surface</dd>
      </dl>

      {editable && <form onSubmit={replaceTerms}>
        <h3>Exact final terms</h3>
        <label>Terms<textarea rows={5} required value={termsText} onChange={event => setTermsText(event.target.value)} placeholder={"Room=Deluxe room\nCancellation=Free until 24 hours before arrival"} /><small>One exact term per line as Name=Value.</small></label>
        <p className="cw-fineprint">Money is entered as integer minor units to avoid floating-point ambiguity. For USD, 12500 means USD 125.00.</p>
        <label>Subtotal (minor units)<input inputMode="numeric" value={subtotal} onChange={event => setSubtotal(event.target.value)} /></label>
        <label>Tax (minor units)<input inputMode="numeric" value={tax} onChange={event => setTax(event.target.value)} /></label>
        <label>Fees (minor units)<input inputMode="numeric" value={fees} onChange={event => setFees(event.target.value)} /></label>
        <label>Shipping (minor units)<input inputMode="numeric" value={shipping} onChange={event => setShipping(event.target.value)} /></label>
        <label>Discount (minor units)<input inputMode="numeric" value={discount} onChange={event => setDiscount(event.target.value)} /></label>
        <label>Provider quote ID (optional)<input value={providerQuoteId} maxLength={255} onChange={event => setProviderQuoteId(event.target.value)} /></label>
        <label>Quote expires<input type="datetime-local" required value={quoteExpiry} onChange={event => setQuoteExpiry(event.target.value)} /></label>
        <button className="cw-secondary" type="submit" disabled={Boolean(busy)}>Save exact terms</button>
      </form>}

      {surface.terms && <div>
        <h3>Review binding</h3>
        <dl className="cw-action-details">
          <dt>Total</dt><dd>{surface.terms.total_minor} {surface.terms.currency} minor units</dd>
          <dt>Quote expires</dt><dd>{new Date(surface.terms.quote_expires_at).toLocaleString()}</dd>
          <dt>Terms revision</dt><dd>{surface.terms.revision}</dd>
          <dt>Terms SHA-256</dt><dd><code>{surface.terms.terms_sha256}</code></dd>
        </dl>
        <ul>{surface.terms.terms.map(term => <li key={term.name}><strong>{term.name}:</strong> {term.value}</li>)}</ul>
      </div>}

      {surface.transaction.state === "terms_ready" && <button className="cw-secondary" type="button" disabled={Boolean(busy)} onClick={startReview}>Start review</button>}
      {surface.transaction.state === "awaiting_review" && surface.terms && <button className="cw-primary" type="button" disabled={Boolean(busy)} onClick={confirmReview}>Confirm this exact hash</button>}
      {surface.transaction.state === "awaiting_approval" && <p className="cw-notice">Human review is confirmed. TX-04 does not provide provider approval or execution; a later qualified adapter must create a separately reviewed ExternalAction.</p>}
      {cancellable && <button className="cw-text-button" type="button" disabled={Boolean(busy)} onClick={cancelTransaction}>Cancel transaction review</button>}

      <h3>History</h3>
      {surface.events.length === 0 ? <p>No events recorded.</p> : <ol>
        {surface.events.map(event => <li key={event.sequence}>#{event.sequence} · {event.event_type} · {event.state} · revision {event.revision}</li>)}
      </ol>}
    </div>}
  </section>;
}
