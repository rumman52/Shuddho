import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import type { ConversationActivityRecord, ConversationMessageRecord, ConversationRecord, CoworkerClient, GitHubRepositoryBinding, GitHubRepositoryFile, SandboxExecution, SandboxSession } from "./client";
import ConversationRunStatus from "./ConversationRunStatus";
import FlyRepositoryPanel from "./FlyRepositoryPanel";
import "./fly-workspace.css";

type FlyLanguage = "python" | "javascript" | "typescript" | "html" | "css" | "json" | "markdown" | "text" | "sql" | "shell";
type SavedSource = { documentId: string; versionId: string; sha256: string; filename: string };
type RepositoryOrigin = { repository: string; path: string; branch: string; commitSha: string; repositorySha: string };
type FlyFile = { id: string; name: string; language: FlyLanguage; content: string; saved?: SavedSource; origin?: RepositoryOrigin };
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
export function normalizeStoredDraft(value: unknown): FlyDraft {
  const fallback: FlyDraft = { files: [DEFAULT_FILE], activeId: DEFAULT_FILE.id };
  if (!value || typeof value !== "object") return fallback;
  const parsed = value as { files?: unknown; activeId?: unknown };
  if (!Array.isArray(parsed.files)) return fallback;

  const files = parsed.files.filter((item: unknown): item is FlyFile => {
    if (!item || typeof item !== "object") return false;
    const file = item as Record<string, unknown>;
    return typeof file.id === "string" && typeof file.name === "string" && typeof file.content === "string" &&
      encodedBytes(file.content) <= MAX_FILE_BYTES && typeof file.language === "string" &&
      languageOptions.some(option => option.value === file.language);
  }).slice(0, MAX_FILES).map((file: FlyFile) => {
    const savedValue: unknown = file.saved;
    const saved = savedValue && typeof savedValue === "object" &&
      "documentId" in savedValue && typeof savedValue.documentId === "string" &&
      "versionId" in savedValue && typeof savedValue.versionId === "string" &&
      "sha256" in savedValue && typeof savedValue.sha256 === "string" &&
      "filename" in savedValue && typeof savedValue.filename === "string"
      ? savedValue as SavedSource
      : undefined;
    const originValue: unknown = file.origin;
    const origin = originValue && typeof originValue === "object" &&
      "repository" in originValue && typeof originValue.repository === "string" &&
      "path" in originValue && typeof originValue.path === "string" &&
      "branch" in originValue && typeof originValue.branch === "string" &&
      "commitSha" in originValue && typeof originValue.commitSha === "string" && /^[a-f0-9]{40}$/i.test(originValue.commitSha) &&
      "repositorySha" in originValue && typeof originValue.repositorySha === "string" && /^[a-f0-9]{40}$/i.test(originValue.repositorySha)
      ? originValue as RepositoryOrigin
      : undefined;
    return { ...file, name: safeFilename(file.name), saved, origin };
  });

  if (!files.length) return fallback;
  const activeId = typeof parsed.activeId === "string" && files.some(file => file.id === parsed.activeId)
    ? parsed.activeId
    : files[0].id;
  return { files, activeId };
}

function readDraft(accountId: string): FlyDraft {
  const fallback: FlyDraft = { files: [DEFAULT_FILE], activeId: DEFAULT_FILE.id };
  if (typeof window === "undefined") return fallback;
  try {
    return normalizeStoredDraft(JSON.parse(window.sessionStorage.getItem(storageKey(accountId)) ?? "null"));
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

export type FlyDiffLine = { kind: "add" | "remove"; text: string };

/** Small, local-only line diff. Large files deliberately fall back to a safe summary. */
export function buildLineDiff(before: string, after: string): FlyDiffLine[] | null {
  const lines = (value: string) => {
    const normalized = value.replace(/\r\n?/g, "\n");
    if (!normalized) return [];
    const result = normalized.split("\n");
    if (result[result.length - 1] === "") result.pop();
    return result;
  };
  const left = lines(before);
  const right = lines(after);
  if (left.length > 300 || right.length > 300) return null;

  const matrix = Array.from({ length: left.length + 1 }, () => new Uint16Array(right.length + 1));
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      matrix[i][j] = left[i] === right[j]
        ? matrix[i + 1][j + 1] + 1
        : Math.max(matrix[i + 1][j], matrix[i][j + 1]);
    }
  }

  const changes: FlyDiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < left.length || j < right.length) {
    if (i < left.length && j < right.length && left[i] === right[j]) {
      i += 1;
      j += 1;
    } else if (i < left.length && (j >= right.length || matrix[i + 1][j] >= matrix[i][j + 1])) {
      changes.push({ kind: "remove", text: left[i] });
      i += 1;
    } else if (j < right.length) {
      changes.push({ kind: "add", text: right[j] });
      j += 1;
    }
  }
  return changes;
}

export default function FlyWorkspace({ client, accountId }: { client: CoworkerClient; accountId: string }) {
  const [draft, setDraft] = useState<FlyDraft>(() => readDraft(accountId));
  const [runtimeEnabled, setRuntimeEnabled] = useState<boolean | null>(null);
  const [runtimeLoading, setRuntimeLoading] = useState(true);
  const [runtimeError, setRuntimeError] = useState("");
  const [projects, setProjects] = useState<Array<{ id: string; name: string }>>([]);
  const [projectsError, setProjectsError] = useState("");
  const [selectedProject, setSelectedProject] = useState("");
  const [repositoryName, setRepositoryName] = useState("");
  const [session, setSession] = useState<SandboxSession | null>(null);
  const [executions, setExecutions] = useState<SandboxExecution[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [storageWarning, setStorageWarning] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [assistantPrompt, setAssistantPrompt] = useState("");
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [messages, setMessages] = useState<ConversationMessageRecord[]>([]);
  const [activity, setActivity] = useState<ConversationActivityRecord[]>([]);
  const [conversationError, setConversationError] = useState("");
  const [workspacePanel, setWorkspacePanel] = useState<"editor" | "changes">("editor");
  const [bottomPanel, setBottomPanel] = useState<"terminal" | "tests" | "logs">("terminal");
  const [savedSnapshots, setSavedSnapshots] = useState<Record<string, string>>({});
  const fileInput = useRef<HTMLInputElement>(null);
  const agentComposerRef = useRef<HTMLTextAreaElement>(null);
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

  const onRepositoryBindingChange = useCallback((binding: GitHubRepositoryBinding | null) => {
    setRepositoryName(binding?.full_name ?? "");
  }, []);

  const importRepositoryFiles = useCallback(async (items: GitHubRepositoryFile[]) => {
    if (!items.length) return;
    const existing = new Set(files.filter(file => file.origin).map(file =>
      [file.origin!.repository, file.origin!.path, file.origin!.commitSha].join("|"),
    ));
    const fresh = items.filter(item => !existing.has([item.repository, item.path, item.commit_sha].join("|")));
    if (!fresh.length) throw new Error("Those repository files are already present at this commit.");
    if (files.length + fresh.length > MAX_FILES) throw new Error("Fly can hold up to " + MAX_FILES + " files. Remove a local file before importing more repository context.");
    const imported: FlyFile[] = [];
    for (const item of fresh) {
      if (item.repository !== repositoryName) throw new Error("The repository changed while these files were being imported. Refresh the repository panel.");
      if (encodedBytes(item.content) !== item.byte_size || item.byte_size > MAX_FILE_BYTES) {
        throw new Error(item.path + " failed the repository file size check.");
      }
      if (!/^[a-f0-9]{40}$/i.test(item.commit_sha) || !/^[a-f0-9]{40}$/i.test(item.blob_sha) || !/^[a-f0-9]{64}$/i.test(item.sha256)) {
        throw new Error(item.path + " is missing valid GitHub source provenance.");
      }
      if (await sha256(item.content) !== item.sha256) throw new Error(item.path + " failed its SHA-256 integrity check.");
      imported.push({
        id: "github-" + globalThis.crypto.randomUUID(),
        name: safeFilename(item.path.replace(/\//g, "__")),
        language: languageForFilename(item.path),
        content: item.content,
        origin: {
          repository: item.repository,
          path: item.path,
          branch: item.branch,
          commitSha: item.commit_sha,
          repositorySha: item.blob_sha,
        },
      });
    }
    setDraft(current => ({ files: [...current.files, ...imported], activeId: imported[0].id }));
    setSavedSnapshots(current => ({
      ...current,
      ...Object.fromEntries(imported.map(file => [file.id, file.content])),
    }));
    setWorkspacePanel("editor");
    setNotice("Imported " + imported.length + " repository file(s) from commit " + fresh[0].commit_sha.slice(0, 12) + ". Fly will save verified private snapshots before attaching them to the Agent.");
  }, [files, repositoryName]);

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

  useEffect(() => {
    const controller = new AbortController();
    client.conversations(controller.signal).then(value => {
      if (!controller.signal.aborted) {
        setConversations(value.items);
        setConversationError("");
      }
    }).catch(failure => {
      if (!controller.signal.aborted) setConversationError(errorMessage(failure));
    });
    return () => controller.abort();
  }, [client]);

  useEffect(() => {
    setMessages([]);
    setActivity([]);
    setConversationError("");
    if (!activeConversationId) return;
    const controller = new AbortController();
    let inFlight = false;
    const reload = async () => {
      if (inFlight || controller.signal.aborted) return;
      inFlight = true;
      try {
        const [history, progress] = await Promise.all([
          client.conversationHistory(activeConversationId, controller.signal),
          client.conversationActivityHistory(activeConversationId, controller.signal),
        ]);
        if (!controller.signal.aborted) {
          setMessages(history.items);
          setActivity(progress.items);
          setConversationError("");
        }
      } catch (failure) {
        if (!controller.signal.aborted) setConversationError(errorMessage(failure));
      } finally {
        inFlight = false;
      }
    };
    void reload();
    const timer = window.setInterval(() => { void reload(); }, 4000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [client, activeConversationId]);

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
    setSavedSnapshots(current => ({ ...current, [active.id]: active.content }));
    return source;
  }

  async function saveRepositoryContextFile(file: FlyFile): Promise<{ versionId: string; digest: string }> {
    if (!file.origin || !file.content.trim()) throw new Error("A repository context file is missing its source metadata or content.");
    if (encodedBytes(file.content) > MAX_FILE_BYTES) throw new Error(file.origin.path + " exceeds Fly's 512 KB source limit.");
    const digest = await sha256(file.content);
    const manifest = await client.workspaceManifest();
    const existingSnapshot = file.saved?.sha256 === digest
      ? manifest.documents.find(item =>
          item.document_id === file.saved?.documentId &&
          item.version_id === file.saved?.versionId &&
          item.sha256 === digest &&
          item.available,
        )
      : undefined;
    const uploadName = safeFilename(
      "repo-" + file.origin.repository.replace("/", "-") + "-" +
      file.origin.path.replace(/\//g, "__") + "-" + digest.slice(0, 8),
    ) + ".txt";
    let source = existingSnapshot ?? manifest.documents.find(item => item.name === uploadName && item.sha256 === digest && item.available);
    if (!source) {
      const uploaded = await client.upload(new File([file.content], uploadName, { type: "text/plain" }));
      const refreshed = await client.workspaceManifest();
      source = refreshed.documents.find(item => item.document_id === uploaded.id && item.sha256 === digest && item.available);
    }
    if (!source) throw new Error("The repository file snapshot could not be verified in Rukh Files. Refresh Files and retry.");
    if (selectedProject) {
      const project = await client.project(selectedProject);
      const alreadyLinked = project.resources.some(item => item.resource_type === "document" && item.resource_id === source!.document_id);
      if (!alreadyLinked) await client.linkProjectResource(project.id, "document", source.document_id, project.revision);
    }
    const saved: SavedSource = { documentId: source.document_id, versionId: source.version_id, sha256: digest, filename: source.name };
    setDraft(current => ({ ...current, files: current.files.map(item => item.id === file.id ? { ...item, saved } : item) }));
    setSavedSnapshots(current => ({ ...current, [file.id]: file.content }));
    return { versionId: source.version_id, digest };
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

  async function reviewWithRukh(request = assistantPrompt) {
    if (busy || !active) return;
    const userRequest = request.trim() || "Review this file for correctness, security, performance, maintainability and missing tests.";
    setBusy("review"); setError(""); setNotice(""); setConversationError("");
    try {
      const source = await saveActive();
      const repositoryFiles = files.filter(file => file.origin && file.origin.repository === repositoryName);
      const repositoryContext: Array<{ path: string; branch: string; commitSha: string; repositorySha: string; localSha: string; versionId: string }> = [];
      for (const file of repositoryFiles) {
        const saved = file.id === active.id
          ? { versionId: source.version_id, digest: source.sha256 }
          : await saveRepositoryContextFile(file);
        if (file.origin) repositoryContext.push({
          path: file.origin.path,
          branch: file.origin.branch,
          commitSha: file.origin.commitSha,
          repositorySha: file.origin.repositorySha,
          localSha: saved.digest,
          versionId: saved.versionId,
        });
      }
      const repositoryFingerprint = repositoryContext.map(item =>
        [item.path, item.commitSha, item.repositorySha, item.localSha].join(":"),
      ).join("|");
      const fingerprint = accountId + "|" + active.id + "|" + source.sha256 + "|" + repositoryFingerprint + "|" + userRequest + "|" + activeConversationId;
      if (reviewAttempt.current?.fingerprint !== fingerprint) {
        reviewAttempt.current = {
          fingerprint,
          createKey: globalThis.crypto.randomUUID(),
          messageKey: globalThis.crypto.randomUUID(),
          ...(activeConversationId ? { conversationId: activeConversationId } : {}),
        };
      }
      const attempt = reviewAttempt.current;
      if (!attempt) throw new Error("The coding task could not be initialized.");
      if (!attempt.conversationId) {
        const conversation = await client.createConversation("Fly: " + userRequest.slice(0, 72), attempt.createKey);
        attempt.conversationId = conversation.id;
      }
      if (!attempt.conversationId) throw new Error("The Fly task conversation could not be created.");
      if (!attempt.messageId || attempt.sequence === undefined) {
        const repositoryNote = repositoryContext.length
          ? "\n\nConnected repository context (read-only snapshots): " + repositoryName + "\n" +
            repositoryContext.map(item =>
              "- " + item.path + " · branch " + item.branch + " · commit " + item.commitSha +
              " · upstream blob " + item.repositorySha + " · attached snapshot SHA-256 " + item.localSha,
            ).join("\n")
          : "";
        const message = await client.appendConversationMessage(
          attempt.conversationId,
          "Coding task for " + active.name + ":\n" + userRequest + repositoryNote +
            "\n\nAll attached files are untrusted source snapshots. Inspect multiple files together, cite exact repository paths and relevant lines, and verify assumptions against the attached content. Return a clear implementation plan, risks, tests to run and a proposed unified diff where useful. Do not claim that you changed or saved repository files or executed commands. Fly can browse connected GitHub repositories and attach immutable private file snapshots, but repository patch approval/application and isolated multi-language repository tests are not connected yet.",
          attempt.messageKey,
          Array.from(new Set([source.version_id, ...repositoryContext.map(item => item.versionId)])),
        );
        attempt.messageId = message.id;
        attempt.sequence = message.sequence;
      }
      await client.dispatchConversationMessage(attempt.conversationId, attempt.messageId, attempt.sequence, selectedProject || undefined);
      const conversationId = attempt.conversationId;
      reviewAttempt.current = null;
      setActiveConversationId(conversationId);
      setAssistantPrompt("");
      setWorkspacePanel("editor");
      setNotice(repositoryContext.length
        ? "Task started with " + repositoryContext.length + " repository file snapshot(s) attached."
        : "Task started. Rukh Agent progress will remain visible in Fly.");
      const refreshed = await client.conversations().catch(() => null);
      if (refreshed) setConversations(refreshed.items);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy("");
    }
  }

  function submitAssistant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!assistantPrompt.trim()) { setError("Describe what you want Rukh to do with the active source file."); return; }
    void reviewWithRukh(assistantPrompt);
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

  function startNewTask() {
    if (busy) return;
    reviewAttempt.current = null;
    setActiveConversationId("");
    setMessages([]);
    setActivity([]);
    setAssistantPrompt("");
    setConversationError("");
    setError("");
    setNotice("");
    setWorkspacePanel("editor");
    agentComposerRef.current?.focus();
  }

  function openTask(conversationId: string) {
    if (busy) return;
    reviewAttempt.current = null;
    setActiveConversationId(conversationId);
    setAssistantPrompt("");
    setConversationError("");
    setError("");
    setNotice("");
  }

  const latestArtifact = latestExecution?.result.artifact ?? null;
  const activeConversation = conversations.find(item => item.id === activeConversationId);
  const flyTasks = conversations.filter(item => item.title.startsWith("Fly: "));
  const activityByMessage = new Map(activity.map(item => [item.message_id, item]));
  const changedFiles = files.filter(file => {
    const baseline = savedSnapshots[file.id];
    return baseline === undefined ? !file.saved : baseline !== file.content;
  });
  return <section className="rukh-fly-workspace" aria-label="Fly code workspace">
    <header className="rukh-fly-v2-topbar">
      <div className="rukh-fly-v2-brand">
        <a href="/coworker" aria-label="Back to Rukh AI Coworker">rukh<sup>AI</sup></a>
        <span>/</span><strong>Fly</strong>
        <small>{projects.find(project => project.id === selectedProject)?.name ?? "Personal workspace"}</small>
      </div>
      <div className="rukh-fly-v2-top-actions">
        <span className="rukh-fly-v2-repo-badge" title={repositoryName ? "Connected GitHub repository · read-only source access" : "No GitHub repository connected"}>{repositoryName ? "GitHub · " + repositoryName : "Local workspace"}</span>
        <span className={"rukh-fly-v2-runtime" + (runtimeEnabled ? " is-enabled" : "")} role="status">
          <i />{runtimeLoading ? "Checking runtime" : runtimeEnabled ? "Python 3.11 ready" : "Runtime unavailable"}
        </span>
        <button type="button" onClick={createFile} disabled={Boolean(busy) || files.length >= MAX_FILES}>New file</button>
        <button type="button" onClick={() => fileInput.current?.click()} disabled={Boolean(busy) || files.length >= MAX_FILES}>Upload</button>
        <button type="button" onClick={() => void saveFile()} disabled={Boolean(busy) || !active?.content.trim()}>{busy === "save" ? "Saving…" : "Save"}</button>
        <button type="button" className="is-primary" onClick={() => void runPython()} disabled={Boolean(busy) || Boolean(runningExecutionId) || runtimeLoading || runtimeEnabled !== true || active?.language !== "python" || !active?.content.trim()}>{busy === "run" ? "Running…" : "Run Python 3.11"}</button>
        <input ref={fileInput} className="rukh-fly-file-input" type="file" aria-label="Upload source file" accept=".py,.js,.jsx,.mjs,.cjs,.ts,.tsx,.html,.htm,.css,.scss,.json,.md,.markdown,.txt,.yaml,.yml,.toml,.xml,.sql,.sh,.bash,.go,.rs,.java,.kt,.dart,.swift,.c,.h,.cpp,.hpp,.cs,.php,.rb,.vue,.svelte,.astro,.graphql" onChange={event => void uploadFile(event)} />
      </div>
    </header>

    {(error || runtimeError || projectsError || storageWarning || notice || conversationError) && <div className="rukh-fly-v2-feedback">
      {error && <p role="alert">{error}</p>}
      {runtimeError && <p role="alert">Runtime status could not be verified: {runtimeError}</p>}
      {projectsError && <p role="alert">Projects could not be loaded: {projectsError}</p>}
      {storageWarning && <p role="alert">Save source files to Rukh Files before leaving; this tab cannot preserve local drafts.</p>}
      {notice && <p role="status">{notice}</p>}
      {conversationError && <p role="alert">{conversationError}</p>}
    </div>}

    <div className="rukh-fly-v2-layout">
      <aside className="rukh-fly-v2-sidebar" aria-label="Fly file explorer and task history">
        <div className="rukh-fly-v2-sidebar-heading">
          <div><span>CODING WORKSPACE</span><h2>Fly</h2></div>
          <button type="button" onClick={startNewTask} disabled={Boolean(busy)}>+ New task</button>
        </div>

        <label className="rukh-fly-v2-project-label">Project
          <select aria-label="Attach saved files to project" value={selectedProject} onChange={event => setSelectedProject(event.target.value)} disabled={Boolean(busy)}>
            <option value="">Personal workspace</option>
            {projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </label>

        <FlyRepositoryPanel
          client={client}
          projectId={selectedProject}
          onProjectChange={setSelectedProject}
          onBindingChange={onRepositoryBindingChange}
          onImportFiles={importRepositoryFiles}
        />

        <section className="rukh-fly-v2-sidebar-section" aria-label="Recent coding tasks">
          <div className="rukh-fly-v2-section-title"><span>RECENT TASKS</span><small>{flyTasks.length}</small></div>
          {flyTasks.length ? <ul className="rukh-fly-v2-task-list">
            {flyTasks.map(item => <li key={item.id}>
              <button type="button" className={activeConversationId === item.id ? "is-active" : ""} aria-pressed={activeConversationId === item.id} onClick={() => openTask(item.id)} disabled={Boolean(busy)}>
                <strong>{item.title}</strong>
                <small>{new Date(item.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</small>
              </button>
            </li>)}
          </ul> : <p className="rukh-fly-v2-sidebar-empty">Your coding tasks will appear here.</p>}
        </section>

        <section className="rukh-fly-v2-sidebar-section rukh-fly-v2-files-section" aria-label="Project files">
          <div className="rukh-fly-v2-section-title"><span>FILES</span><div><small>{files.length}/{MAX_FILES}</small><button type="button" aria-label="Create new file" onClick={createFile} disabled={Boolean(busy) || files.length >= MAX_FILES}>+</button></div></div>
          <ul className="rukh-fly-v2-file-list">{files.map(file => <li key={file.id}>
            <button type="button" className={file.id === active?.id ? "is-active" : ""} aria-current={file.id === active?.id ? "page" : undefined} onClick={() => { setDraft(current => ({ ...current, activeId: file.id })); setWorkspacePanel("editor"); }} disabled={Boolean(busy)}>
              <span className="rukh-fly-v2-file-icon">{file.name.split(".").pop()?.slice(0, 3).toUpperCase() ?? "TXT"}</span>
              <span>{file.name}</span>
              <small>{file.saved?.sha256 ? "Saved" : "Draft"}</small>
            </button>
            {files.length > 1 && <button type="button" className="rukh-fly-v2-remove" aria-label={"Remove " + file.name} onClick={() => removeFile(file.id)} disabled={Boolean(busy)}>×</button>}
          </li>)}</ul>
        </section>

        <footer className="rukh-fly-v2-sidebar-footer">
          <div className="rukh-fly-v2-runtime-card">
            <span>CONNECTED RUNTIME</span>
            <strong>{runtimeLabel}</strong>
            <small>Isolated Python 3.11 execution</small>
          </div>
          <p>GitHub repository browsing and multi-file source context are available when connected. Repository patch approval/application and isolated multi-language tests are not connected yet.</p>
          <a href="/coworker?view=projects">Manage projects ↗</a>
        </footer>
      </aside>

      <section className="rukh-fly-v2-agent" aria-label="AI coding agent">
        <header className="rukh-fly-v2-agent-header">
          <span className="rukh-fly-v2-agent-mark" aria-hidden="true">✦</span>
          <div><strong>Rukh Agent</strong><small>{activeConversation?.title ?? "Coding task workspace"}</small></div>
          <span className={"rukh-fly-v2-agent-state" + (busy === "review" ? " is-working" : "")}>{busy === "review" ? "Working" : activeConversation ? "Task" : "Ready"}</span>
        </header>

        <div className="rukh-fly-v2-thread" aria-live="polite">
          {messages.length === 0 ? <div className="rukh-fly-v2-empty">
            <span>RUKH AI / FLY</span>
            <h2>What are we building?</h2>
            <p>Describe a feature, investigate a bug, or ask Rukh to review your code. Your task and Agent progress stay together in this workspace.</p>
            <div className="rukh-fly-v2-quick-prompts" aria-label="Suggested coding tasks">
              <button type="button" onClick={() => { setAssistantPrompt("Review this file for bugs, security issues and missing tests."); agentComposerRef.current?.focus(); }}>Ask Rukh to review this file</button>
              <button type="button" onClick={() => { setAssistantPrompt("Explain this code step by step, including its inputs, outputs and edge cases."); agentComposerRef.current?.focus(); }}>Explain this code</button>
              <button type="button" onClick={() => { setAssistantPrompt("Suggest a maintainable refactor and provide a proposed unified diff."); agentComposerRef.current?.focus(); }}>Plan a refactor</button>
            </div>
            <div className="rukh-fly-v2-context-card">
              <span>ACTIVE SOURCE</span><strong>{active?.name ?? "No active file"}</strong>
              <small>The active source file is saved as a private snapshot and attached when you start a task.</small>
            </div>
          </div> : <ol className="rukh-fly-v2-message-list" aria-label="Fly task conversation">
            {messages.map(item => {
              const progress = activityByMessage.get(item.id);
              const linkedRun = item.resource_links.find(link => link.resource_type === "agent_run");
              const runId = linkedRun?.resource_id ?? progress?.run_id;
              return <li key={item.id}>
                <article className="rukh-fly-v2-user-message">
                  <header><strong>You</strong><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time></header>
                  <p dir="auto">{item.text}</p>
                  {item.selected_sources.length > 0 && <small className="rukh-fly-v2-attachment-note">{item.selected_sources.length} private source snapshot(s) attached</small>}
                </article>
                {runId ? <ConversationRunStatus client={client} runId={runId} eager /> :
                  progress ? <div className="rukh-fly-v2-run-pending" role="status"><strong>Agent {progress.state.replace(/_/g, " ")}</strong><span>{progress.detail}</span></div> : null}
              </li>;
            })}
          </ol>}
          {conversationError && <p className="rukh-fly-v2-inline-error" role="alert">{conversationError}</p>}
        </div>

        <form className="rukh-fly-v2-composer" onSubmit={submitAssistant}>
          <label htmlFor="rukh-fly-agent-prompt">Ask Rukh about this code</label>
          <textarea ref={agentComposerRef} id="rukh-fly-agent-prompt" aria-label="Ask Rukh about this code" rows={3} maxLength={12000} value={assistantPrompt} onChange={event => setAssistantPrompt(event.target.value)} onKeyDown={event => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
              event.preventDefault();
              if (!busy && assistantPrompt.trim()) event.currentTarget.form?.requestSubmit();
            }
          }} placeholder="Describe the feature, bug or code review you need…" disabled={Boolean(busy)} />
          <div className="rukh-fly-v2-composer-footer">
            <small><span aria-hidden="true">↳</span> {active?.name ?? "No active source"} will be attached</small>
            <button type="submit" disabled={Boolean(busy) || !active?.content.trim() || !assistantPrompt.trim()}>{busy === "review" ? "Starting task…" : "Start task"}</button>
          </div>
        </form>
      </section>

      <section className="rukh-fly-v2-code" aria-label="Code editor and changes">
        <header className="rukh-fly-v2-code-heading">
          <div><span>WORKSPACE</span><h2>Code &amp; changes</h2></div>
          <div className="rukh-fly-v2-tabs" role="tablist" aria-label="Code workspace views">
            <button type="button" role="tab" aria-selected={workspacePanel === "editor"} className={workspacePanel === "editor" ? "is-active" : ""} onClick={() => setWorkspacePanel("editor")}>Editor</button>
            <button type="button" role="tab" aria-selected={workspacePanel === "changes"} className={workspacePanel === "changes" ? "is-active" : ""} onClick={() => setWorkspacePanel("changes")}>Changes <span>{changedFiles.length}</span></button>
          </div>
        </header>

        {workspacePanel === "editor" ? <>
          <div className="rukh-fly-v2-editor-header">
            <div className="rukh-fly-v2-file-tab"><span />{active?.name ?? "No file"}<small>{active?.saved?.sha256 ? "Saved snapshot" : "Local draft"}</small></div>
            <label>Language<select aria-label="Language" value={active?.language ?? "text"} onChange={event => { if (active) setDraft(current => ({ ...current, files: current.files.map(file => file.id === active.id ? { ...file, language: event.target.value as FlyLanguage } : file) })); }} disabled={Boolean(busy)}>
              {languageOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select></label>
            <button type="button" onClick={downloadFile} disabled={!active}>Download</button>
            {active?.language === "html" && <button type="button" onClick={() => setPreviewOpen(value => !value)}>{previewOpen ? "Hide preview" : "Preview"}</button>}
          </div>
          <div className="rukh-fly-code-shell rukh-fly-v2-code-shell">
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
          {previewOpen && active?.language === "html" && <section className="rukh-fly-preview" aria-label="HTML preview">
            <header><strong>Isolated HTML preview</strong><span>Scripts, network and form submission are disabled.</span></header>
            <iframe title="Fly HTML preview" sandbox="" referrerPolicy="no-referrer" srcDoc={previewDocument} />
          </section>}
        </> : <section className="rukh-fly-v2-changes" aria-label="Changed files">
          <div className="rukh-fly-v2-change-summary">
            <strong>{changedFiles.length} local file(s) with changes</strong>
            <p>These comparisons use snapshots saved in this browser tab. They are not Git or repository diffs.</p>
          </div>
          {changedFiles.length === 0 ? <div className="rukh-fly-v2-no-changes"><strong>No local changes</strong><p>Save a source snapshot, then edit a file to review its local diff here.</p></div> :
            changedFiles.map(file => {
              const baseline = savedSnapshots[file.id];
              const diff = baseline === undefined ? null : buildLineDiff(baseline, file.content);
              const additions = diff?.filter(line => line.kind === "add").length ?? 0;
              const removals = diff?.filter(line => line.kind === "remove").length ?? 0;
              return <article className="rukh-fly-v2-change-file" key={file.id}>
                <header><div><strong>{file.name}</strong><small>{baseline === undefined ? "Unsaved local draft · baseline unavailable" : additions + " additions · " + removals + " deletions"}</small></div>
                  <button type="button" onClick={() => { setDraft(current => ({ ...current, activeId: file.id })); setWorkspacePanel("editor"); }}>Open</button>
                </header>
                {baseline === undefined ? <p>Save this file once to establish a local comparison baseline. No repository history is being read.</p> :
                  diff === null ? <p>This file exceeds the 300-line local diff limit. The source remains editable and downloadable.</p> :
                    diff.length === 0 ? <p>No differences from the last saved snapshot.</p> :
                      <pre className="rukh-fly-v2-diff">{diff.map((line, index) => <span key={index} className={"is-" + line.kind}><b>{line.kind === "add" ? "+" : "−"}</b>{line.text || " "}</span>)}</pre>}
              </article>;
            })}
        </section>}
      </section>

      <section className="rukh-fly-v2-console" aria-label="Terminal output">
        <header>
          <div><span>DEVELOPMENT OUTPUT</span><strong>Terminal output</strong></div>
          <nav aria-label="Execution output views">
            <button type="button" className={bottomPanel === "terminal" ? "is-active" : ""} aria-pressed={bottomPanel === "terminal"} onClick={() => setBottomPanel("terminal")}>Terminal</button>
            <button type="button" className={bottomPanel === "tests" ? "is-active" : ""} aria-pressed={bottomPanel === "tests"} onClick={() => setBottomPanel("tests")}>Tests</button>
            <button type="button" className={bottomPanel === "logs" ? "is-active" : ""} aria-pressed={bottomPanel === "logs"} onClick={() => setBottomPanel("logs")}>Logs</button>
          </nav>
          <span className="rukh-fly-v2-console-state">{latestExecution?.state ?? "Idle"}</span>
          {session && runningExecutionId && <button type="button" className="rukh-fly-v2-stop" onClick={() => void stopRun()} disabled={Boolean(busy)}>{busy === "cancel" ? "Stopping…" : "Stop run"}</button>}
        </header>
        {bottomPanel === "terminal" ? <>
          <pre>{terminalOutput}</pre>
          {latestArtifact && <div className="rukh-fly-terminal-artifact"><span>{latestArtifact.filename} · {latestArtifact.byte_size} bytes</span><button type="button" onClick={() => void openArtifactPreview(latestArtifact.id)} disabled={Boolean(busy)}>{busy === "preview" ? "Opening…" : "Open isolated artifact preview"}</button></div>}
        </> : bottomPanel === "tests" ? <div className="rukh-fly-v2-console-empty"><strong>Test runner not connected</strong><p>The current backend provides isolated Python 3.11 execution only. Project test commands, package installation and multi-language test runners are not available yet.</p></div> :
          <div className="rukh-fly-v2-log-list">{executions.length ? executions.map(item => <article key={item.id}>
            <strong>Run {item.sequence} · {item.state}</strong><small>{new Date(item.created_at).toLocaleString()} · {item.result.elapsed_ms ?? "—"} ms</small>
            <pre>{[item.result.stdout, item.result.stderr].filter(Boolean).join("\\n") || "No output."}</pre>
          </article>) : <p>No execution logs yet.</p>}</div>}
      </section>
    </div>
  </section>;
}
