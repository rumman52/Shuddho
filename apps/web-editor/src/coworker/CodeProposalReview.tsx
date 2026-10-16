import { useEffect, useState } from "react";
import {
  CoworkerClient,
  type CodeProposalDetail,
  type CodeProposalSummary,
} from "./client";

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "The code review request was rejected.";

export default function CodeProposalReview({
  client, runId,
}: {
  client: CoworkerClient; runId: string;
}) {
  const [proposals, setProposals] = useState<CodeProposalSummary[]>([]);
  const [detail, setDetail] = useState<CodeProposalDetail | null>(null);
  const [inspected, setInspected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setProposals([]);
    setDetail(null);
    setLoading(true);
    setError("");
    setMessage("");
    client.reviewableCodeProposals(runId, controller.signal).then(result => {
      if (!controller.signal.aborted) setProposals(result.proposals);
    }).catch(failure => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [client, runId]);

  async function inspect(item: CodeProposalSummary) {
    if (busy) return;
    setBusy(true);
    setDetail(null);
    setInspected(false);
    setError("");
    setMessage("");
    try {
      const data = await client.codeProposal(runId, item.id);
      if (data.review_sha256 !== item.review_sha256 || data.id !== item.id) {
        throw new Error("This proposal changed. Refresh before reviewing.");
      }
      setDetail(data);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  async function review(decision: "approve" | "reject") {
    if (!detail || !inspected || busy) return;
    const now = Date.now();
    const deadline = Math.min(Date.parse(detail.expires_at), now + 2 * 60_000);
    if (!(deadline > now)) {
      setError("The review window ended. Revoke this proposal or request a new one.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await client.reviewCodeProposal(
        runId, detail.id, detail.review_sha256, decision, new Date(deadline).toISOString(),
      );
      setMessage(result.decision === "approve"
        ? "Human review recorded. This does not authorize or start code execution."
        : "Proposal rejected and private source erased.");
      setInspected(false);
      setDetail(decision === "reject" ? null : { ...detail, human_review: result });
      const next = await client.reviewableCodeProposals(runId);
      setProposals(next.proposals);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!detail || busy) return;
    if (!window.confirm("Revoke this exact proposal and permanently erase its stored source?")) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await client.revokeCodeProposal(runId, detail.id, detail.review_sha256);
      setDetail(null);
      setInspected(false);
      const next = await client.reviewableCodeProposals(runId);
      setProposals(next.proposals);
      setMessage("Proposal revoked; its stored source is no longer available.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  const remaining = detail && Date.parse(detail.expires_at) > Date.now();
  const approved = detail?.human_review?.decision === "approve";
  return <section className="cw-proposals" aria-label="Review generated code">
    <div>
      <span className="cw-eyebrow">Exact code review</span>
      <h3>Inspect before deciding</h3>
      <p>Stored proposals are untrusted Python. Read the complete source and limits before approving. A review decision is not permission to execute: generated-code dispatch remains unavailable.</p>
    </div>
    {loading && <p role="status">Loading owned proposals…</p>}
    {error && <p role="alert" className="cw-error">{error}</p>}
    {message && <p role="status" className="cw-notice">{message}</p>}
    {!loading && proposals.length === 0 && <p className="cw-fineprint">No currently authorized, unexpired code proposals for this run.</p>}
    {proposals.length > 0 && <div className="cw-proposal-controls" role="group" aria-label="Reviewable code proposals">
      {proposals.map(item => <button type="button" className="cw-secondary"
        key={item.id} disabled={busy} aria-pressed={detail?.id === item.id}
        onClick={() => void inspect(item)}>
        Inspect proposal {item.id.slice(0, 8)} · {item.human_review?.decision ?? "unreviewed"}
      </button>)}
    </div>}
    {detail && <article className="cw-proposal-card" aria-label="Exact code and review authority">
      <div className="cw-proposal-heading"><div><strong>Python source (untrusted)</strong><small>Proposal {detail.id} · expires {new Date(detail.expires_at).toLocaleString()}</small></div></div>
      <dl className="cw-action-details">
        <dt>Immutable review SHA-256</dt><dd><code>{detail.review_sha256}</code></dd>
        <dt>Source SHA-256</dt><dd><code>{detail.proposal.source_sha256}</code></dd>
        <dt>Network access</dt><dd>{detail.proposal.egress_profile === "none" && detail.proposal.destinations.length === 0 ? "No network destinations" : "Unreviewable policy"}</dd>
        <dt>Source inputs</dt><dd>{detail.proposal.input_versions.length === 0 ? "No attached document versions" : detail.proposal.input_versions.map(item =>
          <div key={item.version_id}><code>{item.document_id} · {item.version_id} · {item.source_sha256}</code></div>)}</dd>
        <dt>Execution ceilings</dt><dd>
          CPU {detail.proposal.limits.cpu_seconds}s · wall {detail.proposal.limits.wall_seconds}s ·
          memory {detail.proposal.limits.memory_mb} MB · disk {detail.proposal.limits.disk_mb} MB ·
          output {detail.proposal.limits.stdout_bytes} bytes
        </dd>
      </dl>
      <pre className="cw-code-source"><code>{detail.proposal.source}</code></pre>
      {detail.human_review && <p className="cw-fineprint">Decision: {detail.human_review.decision} · {detail.human_review.revoked ? "revoked" : detail.human_review.expired ? "expired" : "recorded"} · execution authorized: no.</p>}
      {!approved && remaining && <label className="cw-inspection-ack">
        <input type="checkbox" checked={inspected} onChange={event => setInspected(event.target.checked)} disabled={busy} />
        I inspected the exact Python source, inputs, hash, expiry, compute ceilings and network policy shown above.
      </label>}
      <div className="cw-proposal-controls">
        {!detail.human_review && remaining && <div>
          <button type="button" className="cw-primary" disabled={!inspected || busy} onClick={() => void review("approve")}>Record human approval only</button>
          <button type="button" className="cw-secondary" disabled={!inspected || busy} onClick={() => void review("reject")}>Reject and erase</button>
        </div>}
        <button className="cw-text-button" type="button" disabled={busy} onClick={() => void revoke()}>Revoke and erase source</button>
      </div>
      <p className="cw-fineprint">Reviewing does not enqueue Python, start a sandbox, grant a tool, or approve an external action. The server revalidates ownership, scope, and exact identity.</p>
    </article>}
  </section>;
}
