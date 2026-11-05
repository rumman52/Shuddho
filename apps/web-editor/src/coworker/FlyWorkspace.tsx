import { useEffect, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import type { CoworkerClient, SandboxExecution, SandboxSession } from "./client";
import "./fly-workspace.css";

type FlyLanguage = "python" | "javascript" | "typescript" | "html" | "css" | "json" | "markdown" | "text" | "sql" | "shell";
type SavedSource = { documentId: string; versionId: string; sha256: string; filename: string };
type FlyFile = { id: string; name: string; language: FlyLanguage; content: string; saved?: SavedSource };
type FlyDraft = { files: FlyFile[]; activeId: string };
type ReviewAttempt = { fingerprint: string; createKey: string; messageKey: string; conversationId?: string; messageId?: string; sequence?: number };

const MAX_FILES = 12;
const MAX_FILE_BYTES = 512 * 1024;
const MAX_PYTHON_BYTES = 20 * 1024;
const DEFAULT_FILE: FlyFile = { id: "fly-main", name: "main.py", language: "python", content: "def main():\n    print(\"Hello from Fly\")\n\nif __name__ == \"__main__\":\n    main()\n" };
const languageOptions: Array<{ value: FlyLanguage; label: string }> = [
  { value: "python", label: "Python 3.11" }, { value: "javascript", label: "JavaScript" },
  { value: "typescript", label: "TypeScript" }, { value: "html", label: "HTML" },
  { value: "css", label: "CSS" }, { value: "json", label: "JSON" },
  { value: "markdown", label: "Markdown" }, { value: "sql", label: "SQL" },
  { value: "shell", label: "Shell script (editing only)" }, { value: "text", label: "Plain text" },
];
const sourceExtensions = /\.(py|js|jsx|mjs|cjs|ts|tsx|html|htm|css|scss|json|md|markdown|txt|yaml|yml|toml|xml|sql|sh|bash|go|rs|java|kt|dart|swift|c|h|cpp|hpp|cs|php|rb|vue|svelte|astro|graphql)$/i;
const storageKey = (accountId: string) => "rukh-fly-workspace:v1:" + accountId;
const errorMessage = (value: unknown) => value instanceof Error ? value.message : "Fly could not complete this action.";
const encodedBytes = (value: string) => new TextEncoder().encode(value).byteLength;
const activeExecution = (value: SandboxExecution) => value.state === "prepared" || value.state === "running";
const sortExecutions = (items: SandboxExecution[]) => [...items].sort((a, b) => b.sequence - a.sequence);

function safeFilename(value: string) {
  const leaf = value.split(/[\\/]/).pop() ?? "untitled.txt";
  return leaf.replace(/[^\w.-]/g, "-").replace(/^\.+/, "").slice(0, 96) || "untitled.txt";
}
function languageForFilename(name: string): FlyLanguage {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "py") return "python";
  if (["js", "jsx", "mjs", "cjs"].includes(ext)) return "javascript";
  if (["ts", "tsx"].includes(ext)) return "typescript";
  if (["html", "htm"].includes(ext)) return "html";
  if (["css", "scss"].includes(ext)) return "css";
  if (ext === "json") return "json";
  if (["md", "markdown"].includes(ext)) return "markdown";
  if (ext === "sql") return "sql";
  if (["sh", "bash"].includes(ext)) return "shell";
  return "text";
}
function readDraft(accountId: string): FlyDraft {
  const fallback: FlyDraft = { files: [DEFAULT_FILE], activeId: DEFAULT_FILE.id };
  if (typeof window === "undefined") return fallback;
  try {
    const parsed = JSON.parse(window.sessionStorage.getItem(storageKey(accountId)) ?? "null");
    if (!parsed || !Array.isArray(parsed.files)) return fallback;
    const files = parsed.files.filter((item: unknown): item is FlyFile => {
      if (!item || typeof item !== "object") return false;
      const file = item as FlyFile;
      return typeof file.id === "string" && typeof file.name === "string" && typeof file.content === "string" &&
        encodedBytes(file.content) <= MAX_FILE_BYTES && languageOptions.some(option => option.value === file.language);
    }).slice(0, MAX_FILES).map(file => {
      const saved = file.saved && typeof file.saved.documentId === "string" && typeof file.saved.versionId === "string" &&
        typeof file.saved.sha256 === "string" && typeof file.saved.filename === "string" ? file.saved : undefined;
      return { ...file, name: safeFilename(file.name), saved };
    });
    if (!files.length) return fallback;
    const activeId = files.some(file => file.id === parsed.activeId) ? parsed.activeId : files[0].id;
    return { files, activeId };
  } catch { return fallback; }
}
async function sha256(value: string) {
  if (!globalThis.crypto?.subtle) throw new Error("Secure source verification is unavailable in this browser.");
  const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}
function htmlPreviewDocument(source: string) {
  const policy = "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; connect-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src 'none'; font-src data:; form-action 'none'; base-uri 'none'; object-src 'none';\">";
  if (/<head[^>]*>/i.test(source)) return source.replace(/<head([^>]*)>/i, "$&" + policy);
  if (/<html[^>]*>/i.test(source)) return source.replace(/<html([^>]*)>/i, "$&<head>" + policy + "</head>");
  return "<!doctype html><html><head>" + policy + "</head><body>" + source + "</body></html>";
}
function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function highlightSource(source: string, language: FlyLanguage) {
  const keywords = language === "python"
    ? "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda nonlocal not or pass raise return True try while with yield None"
    : "async await break case catch class const continue default delete do else export extends false finally for from function if import in instanceof let new null of return static super switch this throw true try typeof undefined var void while";
  const pattern = /(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_$][\w$]*\b)/g;
  let result = "";
  let offset = 0;
  for (const match of source.matchAll(pattern)) {
    const index = match.index ?? 0;
    const token = match[0];
    result += escapeHtml(source.slice(offset, index));
    let tokenClass = "";
    if (token.startsWith("//") || token.startsWith("#") || token.startsWith("/*")) tokenClass = "fly-token-comment";
    else if (/^["']/.test(token)) tokenClass = "fly-token-string";
    else if (/^\d/.test(token)) tokenClass = "fly-token-number";
    else if (keywords.split(" ").includes(token)) tokenClass = "fly-token-keyword";
    else if (source[index + token.length] === "(") tokenClass = "fly-token-function";
    result += tokenClass ? "<span class=\"" + tokenClass + "\">" + escapeHtml(token) + "</span>" : escapeHtml(token);
    offset = index + token.length;
  }
  result += escapeHtml(source.slice(offset));
  return result + "\n";
}

export default function FlyWorkspace({ client, accountId }: { client: CoworkerClient; accountId: string }) {
  const [draft, setDraft] = useState<FlyDraft>(() => readDraft(accountId));
  const [runtimeEnabled, setRuntimeEnabled] = useState<boolean | null>(null);
  const [runtimeLoading, setRuntimeLoading] = useState(true);
  const [runtimeError, setRuntimeError] = useState("");
  const [projects, setProjects] = useState<Array<{ id: string; name: string }>>([]);
  const [projectsError, setProjectsError] = useState("");
  const [selectedProject, setSelectedProject] = useState("");
  const [session, setSession] = useState<SandboxSession | null>(null);
  const [executions, setExecutions] = useState<SandboxExecution[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [storageWarning, setStorageWarning] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const lineGutter = useRef<HTMLPreElement>(null);
  const highlightLayer = useRef<HTMLPreElement>(null);
  const reviewAttempt = useRef<ReviewAttempt | null>(null);
  const files = draft.files;
  const active = files.find(file => file.id === draft.activeId) ?? files[0];
  const latestExecution = executions[0] ?? null;
  const runningExecutionId = executions.find(activeExecution)?.id ?? "";
  const lineNumbers = useMemo(() => Array.from({ length: Math.max(1, (active?.content ?? "").split("\n").length) }, (_, index) => String(index + 1)).join("\n"), [active?.content]);
  const highlightedSource = useMemo(() => highlightSource(active?.content ?? "", active?.language ?? "text"), [active?.content, active?.language]);
  const previewDocument = useMemo(() => active?.language === "html" ? htmlPreviewDocument(active.content) : "", [active?.content, active?.language]);
  const runtimeLabel = runtimeLoading ? "Checking Python runtime" : runtimeEnabled ? "Python 3.11 available" : "Python runtime disabled";
  const terminalOutput = latestExecution
    ? [latestExecution.result.stdout, latestExecution.result.stderr,
      latestExecution.result.exit_code === undefined ? "" : "Exit code: " + latestExecution.result.exit_code,
      latestExecution.result.elapsed_ms === undefined ? "" : "Elapsed: " + latestExecution.result.elapsed_ms + " ms",
      latestExecution.error_code ? "Execution error: " + latestExecution.error_code : ""].filter(Boolean).join("\n\n")
    : "No Python execution yet. Run a Python file when the isolated runtime is enabled.";

  useEffect(() => {
    try { window.sessionStorage.setItem(storageKey(accountId), JSON.stringify(draft)); setStorageWarning(false); }
    catch { setStorageWarning(true); }
  }, [accountId, draft]);

  useEffect(() => {
    const controller = new AbortController();
    client.sandboxSessions(controller.signal).then(async value => {
      if (controller.signal.aborted) return;
      setRuntimeEnabled(value.enabled);
      const current = value.sessions.find(item => item.purpose === "code_task" && ["prepared", "queued", "running"].includes(item.state));
      if (current) {
        setSession(current);
        try {
          const history = await client.sandboxExecutions(current.id, controller.signal);
          if (!controller.signal.aborted) setExecutions(sortExecutions(history.executions));
        } catch (failure) { if (!controller.signal.aborted) setRuntimeError(errorMessage(failure)); }
      }
    }).catch(failure => {
      if (!controller.signal.aborted) { setRuntimeEnabled(false); setRuntimeError(errorMessage(failure)); }
    }).finally(() => { if (!controller.signal.aborted) setRuntimeLoading(false); });
    client.projects(controller.signal).then(value => {
      if (!controller.signal.aborted) setProjects(value.items.map(item => ({ id: item.id, name: item.name })));
    }).catch(failure => { if (!controller.signal.aborted) setProjectsError(errorMessage(failure)); });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    if (!session || !runningExecutionId) return;
    let alive = true;
    const timer = window.setInterval(() => {
      void client.sandboxExecutions(session.id).then(history => {
        if (alive) setExecutions(sortExecutions(history.executions));
      }).catch(failure => { if (alive) setRuntimeError(errorMessage(failure)); });
    }, 1400);
    return () => { alive = false; window.clearInterval(timer); };
  }, [client, session?.id, runningExecutionId]);

  useEffect(() => setPreviewOpen(false), [draft.activeId]);

  function updateContent(content: string) {
    if (!active) return;
    if (encodedBytes(content) > MAX_FILE_BYTES) { setError("Fly supports source files up to 512 KB each."); return; }
    setDraft(current => ({ ...current, files: current.files.map(file => file.id === active.id ? { ...file, content, saved: undefined } : file) }));
    setError("");
    setNotice("");
  }

  function createFile() {
    if (busy) return;
    if (files.length >= MAX_FILES) { setError("Fly supports up to 12 local source files in one workspace."); return; }
    let index = 1;
    let name = "module-" + index + ".py";
    while (files.some(file => file.name === name)) { index += 1; name = "module-" + index + ".py"; }
    const file: FlyFile = { id: globalThis.crypto.randomUUID(), name, language: "python", content: "" };
    setDraft(current => ({ files: [...current.files, file], activeId: file.id }));
    setError("");
    setNotice(name + " created as a local draft.");
  }

  async function uploadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    if (!sourceExtensions.test(file.name)) { setError("Choose a text source file such as Python, JavaScript, TypeScript, HTML, CSS, JSON, SQL or Markdown."); return; }
    if (file.size > MAX_FILE_BYTES) { setError("Fly supports source files up to 512 KB each."); return; }
    if (files.length >= MAX_FILES) { setError("Fly supports up to 12 local source files in one workspace."); return; }
    setBusy("upload"); setError(""); setNotice("");
    try {
      const content = await file.text();
      if (content.includes("\u0000")) throw new Error("This file is binary, not a plain-text source file.");
      const name = safeFilename(file.name);
      const next: FlyFile = { id: globalThis.crypto.randomUUID(), name, language: languageForFilename(name), content };
      setDraft(current => ({ files: [...current.files, next], activeId: next.id }));
      setNotice(name + " opened as a local draft.");
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(""); }
  }

  async function saveActive() {
    if (!active || !active.content.trim()) throw new Error("Add source code before saving.");
    if (encodedBytes(active.content) > MAX_FILE_BYTES) throw new Error("This source file exceeds Fly's 512 KB limit.");
    const digest = await sha256(active.content);
    const uploadName = safeFilename(active.name) + ".txt";
    const manifest = await client.workspaceManifest();
    let source = manifest.documents.find(item => item.name === uploadName && item.sha256 === digest && item.available);
    if (!source) {
      const uploaded = await client.upload(new File([active.content], uploadName, { type: "text/plain" }));
      const refreshed = await client.workspaceManifest();
      source = refreshed.documents.find(item => item.document_id === uploaded.id && item.sha256 === digest && item.available);
    }
    if (!source) throw new Error("The upload completed, but a verified source version is not available in Rukh Files yet. Refresh Files and retry.");
    if (selectedProject) {
      const project = await client.project(selectedProject);
      const alreadyLinked = project.resources.some(item => item.resource_type === "document" && item.resource_id === source!.document_id);
      if (!alreadyLinked) await client.linkProjectResource(project.id, "document", source.document_id, project.revision);
    }
    const saved: SavedSource = { documentId: source.document_id, versionId: source.version_id, sha256: digest, filename: source.name };
    setDraft(current => ({ ...current, files: current.files.map(file => file.id === active.id ? { ...file, saved } : file) }));
    return source;
  }

  async function saveFile() {
    if (busy || !active) return;
    setBusy("save"); setError(""); setNotice("");
    try {
      await saveActive();
      setNotice("Saved " + active.name + " as a verified private source snapshot in Rukh Files." + (selectedProject ? " Linked to the selected project." : ""));
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(""); }
  }

  async function reviewWithRukh() {
    if (busy || !active) return;
    setBusy("review"); setError(""); setNotice("");
    try {
      const source = await saveActive();
      const fingerprint = accountId + "|" + active.id + "|" + source.sha256;
      if (reviewAttempt.current?.fingerprint !== fingerprint) {
        reviewAttempt.current = { fingerprint, createKey: globalThis.crypto.randomUUID(), messageKey: globalThis.crypto.randomUUID() };
      }
      const attempt = reviewAttempt.current;
      if (!attempt) throw new Error("The review request could not be initialized.");
      if (!attempt.conversationId) {
        const conversation = await client.createConversation("Code review: " + active.name, attempt.createKey);
        attempt.conversationId = conversation.id;
      }
      if (!attempt.conversationId) throw new Error("The review conversation could not be created.");
      if (!attempt.messageId || attempt.sequence === undefined) {
        const message = await client.appendConversationMessage(
          attempt.conversationId,
          "Review the attached source file " + active.name + " as untrusted code. Perform a static review only. Check correctness, edge cases, security, performance, maintainability and test coverage. Return prioritized findings with file/line references and a suggested unified diff. Do not claim that you executed, changed or saved the local file. Ask before any external or destructive action.",
          attempt.messageKey,
          [source.version_id],
        );
        attempt.messageId = message.id;
        attempt.sequence = message.sequence;
      }
      await client.dispatchConversationMessage(attempt.conversationId, attempt.messageId, attempt.sequence);
      const destination = "/coworker?conversation=" + encodeURIComponent(attempt.conversationId);
      reviewAttempt.current = null;
      window.location.assign(destination);
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(""); }
  }

  async function runPython() {
    if (busy || !active) return;
    if (runningExecutionId) { setError("Wait for the current Python execution to finish or stop it before starting another run."); return; }
    if (active.language !== "python") { setError("The connected runtime currently executes Python 3.11 only."); return; }
    if (runtimeEnabled !== true) { setError("The isolated Python runtime is disabled or unavailable. Editing, HTML preview and private file saving remain available."); return; }
    if (!active.content.trim()) { setError("Add Python source before running it."); return; }
    if (encodedBytes(active.content) > MAX_PYTHON_BYTES) { setError("Python execution is limited to 20 KB of source per run."); return; }
    setBusy("run"); setError(""); setNotice("");
    try {
      let current = session;
      if (!current || !["prepared", "queued", "running"].includes(current.state)) {
        current = await client.createSandboxSession("code_task", "fly-" + globalThis.crypto.randomUUID());
        setSession(current);
        setExecutions([]);
      }
      const result = await client.runSandbox(current.id, active.content);
      setExecutions(previous => sortExecutions([result, ...previous.filter(item => item.id !== result.id)]));
      setNotice("Python execution submitted to the isolated worker. Network access, credentials, host mounts and arbitrary packages are not available.");
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(""); }
  }

  async function stopRun() {
    if (!session || busy) return;
    setBusy("cancel"); setError(""); setNotice("");
    try {
      const updated = await client.cancelSandbox(session.id);
      setSession(updated);
      const history = await client.sandboxExecutions(session.id);
      setExecutions(sortExecutions(history.executions));
      setNotice("The sandbox cancellation request was accepted.");
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(""); }
  }

  async function openArtifactPreview(artifactId: string) {
    if (busy) return;
    setBusy("preview"); setError(""); setNotice("");
    try {
      const value = await client.sandboxPreview(artifactId);
      const url = new URL(value.url);
      const local = url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
      if ((url.protocol !== "https:" && !local) || url.username || url.password || url.origin === window.location.origin || !url.pathname.startsWith("/sandbox-preview/")) {
        throw new Error("The preview origin is not safely isolated.");
      }
      const opened = window.open(url.href, "_blank", "noopener,noreferrer");
      if (opened) opened.opener = null;
      setNotice("Opened a short-lived preview on the isolated sandbox origin without the workspace access token.");
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(""); }
  }

  function downloadFile() {
    if (!active) return;
    const url = URL.createObjectURL(new Blob([active.content], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = safeFilename(active.name);
    anchor.rel = "noreferrer";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  function editorKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (!active) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); void saveFile(); return; }
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); void runPython(); return; }
    if (event.key === "Tab") {
      event.preventDefault();
      const target = event.currentTarget;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      updateContent(active.content.slice(0, start) + "    " + active.content.slice(end));
      window.requestAnimationFrame(() => target.setSelectionRange(start + 4, start + 4));
    }
  }

  function removeFile(id: string) {
    if (busy) return;
    if (files.length <= 1) { setError("Fly keeps at least one source file in the workspace."); return; }
    const remaining = files.filter(file => file.id !== id);
    setDraft(current => ({ files: remaining, activeId: current.activeId === id ? remaining[0].id : current.activeId }));
    setError("");
  }

  const runtimeStatus = runtimeLoading ? "Checking runtime" : runtimeEnabled ? "Python 3.11 ready" : "Python runtime disabled";
  const latestArtifact = latestExecution?.result.artifact ?? null;

  return <section className="rukh-fly-workspace" aria-label="Fly code workspace">
    <header className="rukh-fly-toolbar">
      <div className="rukh-fly-toolbar-copy"><span className="rukh-fly-kicker">RUKH AI / FLY</span><h2>Build, test and iterate.</h2><p>Manage source files, run supported code, preview HTML and hand work to Rukh.</p></div>
      <div className="rukh-fly-toolbar-actions">
        <span className={"rukh-fly-runtime-badge" + (runtimeEnabled ? " is-enabled" : "")} role="status">{runtimeStatus}</span>
        <button type="button" className="rukh-fly-button" onClick={createFile} disabled={Boolean(busy) || files.length >= MAX_FILES}>New file</button>
        <button type="button" className="rukh-fly-button" onClick={() => fileInput.current?.click()} disabled={Boolean(busy) || files.length >= MAX_FILES}>Upload file</button>
        <input ref={fileInput} className="rukh-fly-file-input" type="file" aria-label="Upload source file" accept=".py,.js,.jsx,.mjs,.cjs,.ts,.tsx,.html,.htm,.css,.scss,.json,.md,.markdown,.txt,.yaml,.yml,.toml,.xml,.sql,.sh,.bash,.go,.rs,.java,.kt,.dart,.swift,.c,.h,.cpp,.hpp,.cs,.php,.rb,.vue,.svelte,.astro,.graphql" onChange={event => void uploadFile(event)} />
        <button type="button" className="rukh-fly-button" onClick={() => void saveFile()} disabled={Boolean(busy) || !active?.content.trim()}>{busy === "save" ? "Saving…" : "Save to Rukh Files"}</button>
        <button type="button" className="rukh-fly-button rukh-fly-button-primary" onClick={() => void reviewWithRukh()} disabled={Boolean(busy) || !active?.content.trim()}>{busy === "review" ? "Starting review…" : "Ask Rukh to review"}</button>
      </div>
    </header>
    {error && <p className="rukh-fly-alert" role="alert">{error}</p>}
    {runtimeError && <p className="rukh-fly-alert" role="alert">Runtime status could not be verified: {runtimeError}</p>}
    {projectsError && <p className="rukh-fly-alert" role="alert">Projects could not be loaded: {projectsError}</p>}
    {storageWarning && <p className="rukh-fly-alert" role="alert">This tab cannot preserve local drafts. Save source files to Rukh Files before leaving.</p>}
    {notice && <p className="rukh-fly-notice" role="status">{notice}</p>}
    <div className="rukh-fly-layout">
      <aside className="rukh-fly-panel rukh-fly-files" aria-label="Fly file explorer">
        <div className="rukh-fly-panel-heading"><div><span>WORKSPACE</span><h3>Files</h3></div><span className="rukh-fly-file-count">{files.length}/{MAX_FILES}</span></div>
        <label className="rukh-fly-project-label">Project
          <select aria-label="Attach saved files to project" value={selectedProject} onChange={event => setSelectedProject(event.target.value)} disabled={Boolean(busy)}>
            <option value="">No project selected</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </label>
        <ul className="rukh-fly-file-list">{files.map(file => <li key={file.id}>
          <button type="button" className={file.id === active?.id ? "is-active" : ""} aria-current={file.id === active?.id ? "page" : undefined} onClick={() => setDraft(current => ({ ...current, activeId: file.id }))} disabled={Boolean(busy)}>
            <span aria-hidden="true">‹/›</span><span>{file.name}</span><small>{file.saved?.sha256 ? "Saved" : "Local"}</small>
          </button>
          {files.length > 1 && <button type="button" className="rukh-fly-remove-file" aria-label={"Remove " + file.name} onClick={() => removeFile(file.id)} disabled={Boolean(busy)}>×</button>}
        </li>)}</ul>
        <p className="rukh-fly-fineprint">Local drafts stay in this browser tab. Saving creates a verified text snapshot in Rukh Files; it does not overwrite the original source file.</p>
        <a className="rukh-fly-project-link" href="/coworker?view=projects">Manage projects</a>
      </aside>
      <section className="rukh-fly-panel rukh-fly-editor-panel" aria-label="Source editor">
        <div className="rukh-fly-editor-header">
          <div className="rukh-fly-file-tab"><span className="rukh-fly-file-dot" />{active?.name ?? "No file"}</div>
          <label className="rukh-fly-language-label">Language
            <select aria-label="Language" value={active?.language ?? "text"} onChange={event => {
              if (active) setDraft(current => ({ ...current, files: current.files.map(file => file.id === active.id ? { ...file, language: event.target.value as FlyLanguage } : file) }));
            }} disabled={Boolean(busy)}>{languageOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
          </label>
          <button type="button" className="rukh-fly-editor-action" onClick={downloadFile} disabled={!active}>Download</button>
          {active?.language === "html" && <button type="button" className="rukh-fly-editor-action" onClick={() => setPreviewOpen(value => !value)}>{previewOpen ? "Hide preview" : "Preview HTML"}</button>}
        </div>
        <div className="rukh-fly-code-shell">
          <pre ref={lineGutter} className="rukh-fly-line-numbers" aria-hidden="true">{lineNumbers}</pre>
          <div className="rukh-fly-code-layer">
            <pre ref={highlightLayer} className="rukh-fly-code-highlight" aria-hidden="true" dangerouslySetInnerHTML={{ __html: highlightedSource }} />
            <textarea aria-label="Code editor" dir="ltr" autoCapitalize="off" autoComplete="off" autoCorrect="off" spellCheck={false} maxLength={MAX_FILE_BYTES} value={active?.content ?? ""} disabled={Boolean(busy)} onChange={event => updateContent(event.target.value)} onKeyDown={editorKeyDown} onScroll={event => {
              if (lineGutter.current) lineGutter.current.scrollTop = event.currentTarget.scrollTop;
              if (highlightLayer.current) {
                highlightLayer.current.scrollTop = event.currentTarget.scrollTop;
                highlightLayer.current.scrollLeft = event.currentTarget.scrollLeft;
              }
            }} />
          </div>
        </div>
        {previewOpen && active?.language === "html" && <section className="rukh-fly-preview" aria-label="HTML preview"><header><strong>Isolated HTML preview</strong><span>Scripts are disabled; network and form submission are blocked.</span></header><iframe title="Fly HTML preview" sandbox="" referrerPolicy="no-referrer" srcDoc={previewDocument} /></section>}
        <section className="rukh-fly-terminal" aria-label="Python terminal output">
          <header><div><span className="rukh-fly-terminal-indicator" /><strong>Terminal output</strong></div><span>{latestExecution?.state ?? "Idle"}</span>
            {session && runningExecutionId && <button type="button" onClick={() => void stopRun()} disabled={Boolean(busy)}>{busy === "cancel" ? "Stopping…" : "Stop run"}</button>}
          </header>
          <pre>{terminalOutput}</pre>
          {latestArtifact && <div className="rukh-fly-terminal-artifact"><span>{latestArtifact.filename} · {latestArtifact.byte_size} bytes</span><button type="button" onClick={() => void openArtifactPreview(latestArtifact.id)} disabled={Boolean(busy)}>{busy === "preview" ? "Opening…" : "Open isolated artifact preview"}</button></div>}
        </section>
      </section>
      <aside className="rukh-fly-panel rukh-fly-inspector">
        <section><span className="rukh-fly-panel-eyebrow">AI CODE REVIEW</span><h3>Work with Rukh</h3><p>Start a real Coworker review with the verified active source attached. Rukh can explain issues and propose a unified diff; it does not silently modify your local files.</p><button type="button" className="rukh-fly-review-button" onClick={() => void reviewWithRukh()} disabled={Boolean(busy) || !active?.content.trim()}>{busy === "review" ? "Starting review…" : "Review this file"}</button></section>
        <section><span className="rukh-fly-panel-eyebrow">EXECUTION</span><h3>{runtimeLabel}</h3><p>The connected backend runtime is an isolated Python 3.11 sandbox with no network, host mounts, credentials or arbitrary package installation.</p>
          {active?.language !== "python" && <p className="rukh-fly-runtime-note">The active file is editable and downloadable, but only Python 3.11 is connected for execution.</p>}
          {runtimeEnabled === false && <p className="rukh-fly-runtime-note">The safe default remains disabled until the environment enables isolated execution.</p>}
          <button type="button" className="rukh-fly-run-button" onClick={() => void runPython()} disabled={Boolean(busy) || Boolean(runningExecutionId) || runtimeLoading || runtimeEnabled !== true || active?.language !== "python" || !active?.content.trim()}>{busy === "run" ? "Running…" : "Run Python 3.11"}</button><small>Shortcut: Ctrl/Cmd + Enter to run · Ctrl/Cmd + S to save</small>
        </section>
        <section><span className="rukh-fly-panel-eyebrow">REPOSITORY TOOLS</span><h3>Not connected yet</h3><p>Git clone/push, remote repository write access, arbitrary shell commands and Node, Java or other language runtimes are not connected to this backend. Fly will not simulate them.</p></section>
      </aside>
    </div>
  </section>;
}
