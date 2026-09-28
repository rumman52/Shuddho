import { useEffect, useRef, useState, type FormEvent } from "react";
import { WorkspaceError, type CoworkerClient, type SandboxExecution, type SandboxPurpose, type SandboxSession } from "./client";

const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Sandbox action failed.";

const INTERACTIVE_SAMPLE = `from pathlib import Path

html = """<!doctype html>
<html>
<head>
  <title>Shuddho private preview</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 1rem; }
  </style>
</head>
<body>
  <main class="card">
    <h1>Private interactive artifact</h1>
    <details>
      <summary>Open details</summary>
      <p>This preview is static, scriptless, and networkless.</p>
    </details>
  </main>
</body>
</html>"""
Path("/tmp/shuddho-preview.html").write_text(html, encoding="utf-8")
print("preview ready")
`;

export default function SandboxWorkspace({ client }: { client: CoworkerClient }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [sessions, setSessions] = useState<SandboxSession[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<SandboxSession | null>(null);
  const [executions, setExecutions] = useState<SandboxExecution[]>([]);
  const [purpose, setPurpose] = useState<SandboxPurpose>("interactive_artifact");
  const [source, setSource] = useState(INTERACTIVE_SAMPLE);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const createKey = useRef("");

  async function load(signal?: AbortSignal) {
    const value = await client.sandboxSessions(signal);
    setEnabled(value.enabled);
    setSessions(value.sessions);
    setSelectedId(current => current && value.sessions.some(item => item.id === current)
      ? current
      : value.sessions[0]?.id ?? "");
  }

  async function loadSelected(id: string, signal?: AbortSignal) {
    const [session, history] = await Promise.all([
      client.sandboxSession(id, signal),
      client.sandboxExecutions(id, signal),
    ]);
    setSelected(session);
    setExecutions(history.executions);
  }

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch(value => {
      if (!controller.signal.aborted) setError(errorMessage(value));
    });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      setExecutions([]);
      return;
    }
    const controller = new AbortController();
    loadSelected(selectedId, controller.signal).catch(value => {
      if (!controller.signal.aborted) setError(errorMessage(value));
    });
    return () => controller.abort();
  }, [client, selectedId]);

  useEffect(() => {
    if (!selectedId || !executions.some(item => ["prepared", "running"].includes(item.state))) return;
    const timer = window.setInterval(() => {
      void loadSelected(selectedId).catch(value => setError(errorMessage(value)));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [client, selectedId, executions]);

  async function createSession(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy("create"); setError(""); setNotice("");
    if (!createKey.current) createKey.current = crypto.randomUUID();
    try {
      const session = await client.createSandboxSession(purpose, createKey.current);
      createKey.current = "";
      setSessions(previous => [session, ...previous.filter(item => item.id !== session.id)]);
      setSelectedId(session.id);
      setSelected(session);
      setExecutions([]);
      setNotice("Disposable Python sandbox prepared. No planner tool or provider authority was granted.");
    } catch (value) {
      setError(errorMessage(value));
    } finally {
      setBusy("");
    }
  }

  async function run(event: FormEvent) {
    event.preventDefault();
    if (!selected || busy || !source.trim()) return;
    setBusy("run"); setError(""); setNotice("");
    try {
      await client.runSandbox(selected.id, source);
      await loadSelected(selected.id);
      setNotice("Execution queued for the isolated worker. Source is treated as untrusted and scrubbed after a terminal result.");
    } catch (value) {
      setError(errorMessage(value));
    } finally {
      setBusy("");
    }
  }

  async function cancel() {
    if (!selected || busy) return;
    setBusy("cancel"); setError(""); setNotice("");
    try {
      await client.cancelSandbox(selected.id);
      await load();
      await loadSelected(selected.id);
      setNotice("Sandbox session cancelled. New worker claims are blocked.");
    } catch (value) {
      setError(errorMessage(value));
    } finally {
      setBusy("");
    }
  }

  async function openPreview(artifactId: string) {
    if (busy) return;
    setBusy("preview"); setError(""); setNotice("");
    try {
      const value = await client.sandboxPreview(artifactId);
      const url = new URL(value.url);
      const local = url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
      if (
        (url.protocol !== "https:" && !local)
        || url.username
        || url.password
        || url.origin === window.location.origin
        || !url.pathname.startsWith("/sandbox-preview/")
      ) {
        throw new WorkspaceError("The interactive preview origin is not safely isolated.");
      }
      const opened = window.open(url.href, "_blank", "noopener,noreferrer");
      if (opened) opened.opener = null;
      setNotice("Opened a short-lived preview on the isolated sandbox origin without the workspace access token.");
    } catch (value) {
      setError(errorMessage(value));
    } finally {
      setBusy("");
    }
  }

  return <section className="cw-service-workspace" aria-label="Sandboxed computation">
    <div className="cw-card-title">
      <span className="cw-step-number">08</span>
      <div>
        <h2>Sandboxed computation</h2>
        <p>Run bounded Python in disposable compute and create private, scriptless interactive previews.</p>
      </div>
    </div>

    {error && <p className="cw-error" role="alert">{error}</p>}
    {notice && <p className="cw-notice" role="status">{notice}</p>}

    {enabled === false ? <div className="cw-agent-run">
      <strong>Sandbox capability is disabled.</strong>
      <p className="cw-fineprint">The safe default remains off until isolated execution, preview-origin and cleanup evidence pass controlled staging.</p>
    </div> : <div className="cw-layout">
      <section className="cw-compose">
        <form onSubmit={createSession}>
          <label>Purpose
            <select value={purpose} onChange={event => {
              const next = event.target.value as SandboxPurpose;
              setPurpose(next);
              createKey.current = "";
              if (next === "interactive_artifact") setSource(INTERACTIVE_SAMPLE);
            }}>
              <option value="interactive_artifact">Private interactive artifact</option>
              <option value="data_analysis">Data analysis</option>
              <option value="code_task">Code task</option>
            </select>
          </label>
          <button className="cw-primary" type="submit" disabled={Boolean(busy)}>
            {busy === "create" ? "Preparing…" : "Prepare disposable sandbox"}<span aria-hidden="true">↗</span>
          </button>
          <p className="cw-fineprint">No network, host filesystem, connector credentials, production secrets, arbitrary packages, Docker socket, or privileged Shuddho API bridge are available to generated code.</p>
        </form>

        {selected && <form onSubmit={run}>
          <label>Python source
            <textarea
              rows={16}
              spellCheck={false}
              value={source}
              maxLength={20000}
              onChange={event => setSource(event.target.value)}
              required
            />
          </label>
          {selected.purpose === "interactive_artifact" && <p className="cw-fineprint">
            Write one UTF-8 file to <code>/tmp/shuddho-preview.html</code>. Only validated static HTML/CSS, fragment links, local controls, and data images are accepted. Scripts, forms, iframes and external resources are rejected.
          </p>}
          <button className="cw-primary" type="submit" disabled={Boolean(busy) || selected.cancel_requested}>
            {busy === "run" ? "Queuing…" : "Run in isolated worker"}<span aria-hidden="true">→</span>
          </button>
        </form>}
      </section>

      <section className="cw-history">
        <h3>Sandbox sessions</h3>
        {sessions.length === 0 && <p className="cw-fineprint">No sandbox sessions yet.</p>}
        {sessions.map(item => <button
          key={item.id}
          type="button"
          className="cw-history-item"
          aria-pressed={selectedId === item.id}
          onClick={() => setSelectedId(item.id)}
        >
          <strong>{item.purpose.replaceAll("_", " ")}</strong>
          <span>{item.state} · expires {new Date(item.expires_at).toLocaleTimeString()}</span>
        </button>)}

        {selected && <div className="cw-agent-run">
          <strong>Selected sandbox</strong>
          <div className="cw-agent-meta">
            <span>{selected.state}</span>
            <span>network {selected.policy.network}</span>
            <span>{selected.policy.resource_limits.memory_mb} MB memory</span>
            <span>{selected.policy.resource_limits.wall_seconds}s wall time</span>
            <span>planner tool {selected.execution.planner_tool_registered ? "registered" : "not registered"}</span>
          </div>
          {!selected.cancel_requested && <button type="button" className="cw-text-button" disabled={Boolean(busy)} onClick={() => void cancel()}>Cancel sandbox</button>}
        </div>}

        <h3>Executions</h3>
        {executions.length === 0 && <p className="cw-fineprint">No executions in this session.</p>}
        {executions.map(item => <article key={item.id} className="cw-agent-run">
          <strong>Run {item.sequence} · {item.state}</strong>
          <div className="cw-agent-meta"><span>attempts {item.attempts}</span>{item.result.elapsed_ms !== undefined && <span>{item.result.elapsed_ms} ms</span>}{item.error_code && <span>{item.error_code}</span>}</div>
          {item.result.stdout && <><p className="cw-fineprint">stdout</p><pre>{item.result.stdout}</pre></>}
          {item.result.stderr && <><p className="cw-fineprint">stderr</p><pre>{item.result.stderr}</pre></>}
          {item.result.artifact && <div>
            <p className="cw-fineprint">{item.result.artifact.filename} · {item.result.artifact.byte_size} bytes · expires {new Date(item.result.artifact.expires_at).toLocaleTimeString()}</p>
            <button type="button" className="cw-secondary" disabled={Boolean(busy)} onClick={() => void openPreview(item.result.artifact!.id)}>
              {busy === "preview" ? "Opening…" : "Open isolated preview"}
            </button>
          </div>}
        </article>)}
      </section>
    </div>}
  </section>;
}
