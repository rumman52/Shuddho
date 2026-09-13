import { fetchWithTimeout } from "../lib/fetchWithTimeout";

export type TaskState = "queued" | "running" | "cancelling" | "completed" | "needs_input" | "failed" | "cancelled";
export type Artifact = { id: string; filename: string; content_type: string; byte_size: number; sha256: string };
export type CoworkerTask = {
  id: string; state: TaskState; phase: string; message: string; error_code: string | null;
  instruction: string; output_language: string; created_at: string; event_sequence: number;
  input: { notes: string; document_ids: string[] } | null;
  artifacts: Artifact[]; usage: { model_attempts: number; accounted_tokens: number };
  draft: null | {
    report: { title: string; summary: string; sections: { heading: string; paragraphs: string[]; source_ids: string[] }[] };
    email: { subject: string; body: string }; output_language: string; missing_information: string[];
  };
  sources: { id: string; label: string; sha256: string }[];
};
export type Workspace = {
  account_id: string; workspace_name: string; preferences: { language?: string };
  usage: { tasks_today: number }; limits: { daily_tasks: number; upload_bytes: number };
};
export type SourceDocument = { id: string; filename: string; state: string; byte_size: number };
export type TaskInput = { instruction: string; notes: string; document_ids: string[]; output_language: string };
export type ProgressEvent = { sequence: number; state: TaskState; phase: string; message: string };
export const terminal = (state: TaskState) => ["completed", "needs_input", "failed", "cancelled"].includes(state);

export class WorkspaceError extends Error {
  constructor(message: string, readonly status = 0) { super(message); }
}

export function trustedBase(base: string): string {
  if (base === "" || base === "/backend") return base;
  const value = new URL(base);
  if ((value.protocol !== "https:" && !(value.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(value.hostname))) ||
      value.username || value.password || value.search || value.hash) {
    throw new Error("Workspace API must use a configured HTTPS origin.");
  }
  return value.href.replace(/\/$/, "");
}

const identifier = (value: string) => {
  if (!/^[a-f0-9-]{36}$/i.test(value)) throw new WorkspaceError("This workspace item is invalid.");
  return value;
};

export function parseProgress(frame: string): ProgressEvent | null {
  const data = frame.split("\n").filter(line => line.startsWith("data:")).map(line => line.slice(5).trim()).join("\n");
  if (!data) return null;
  const value = JSON.parse(data) as ProgressEvent;
  if (!Number.isSafeInteger(value.sequence) || value.sequence < 1 || typeof value.message !== "string" ||
      typeof value.phase !== "string" || !["queued", "running", "cancelling", "completed", "needs_input", "failed", "cancelled"].includes(value.state)) {
    throw new WorkspaceError("The progress connection was interrupted.");
  }
  return value;
}

export function pause(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
    const done = () => { signal.removeEventListener("abort", cancel); resolve(); };
    const timer = setTimeout(done, ms);
    const cancel = () => { clearTimeout(timer); signal.removeEventListener("abort", cancel); reject(new DOMException("Aborted", "AbortError")); };
    signal.addEventListener("abort", cancel, { once: true });
  });
}

export class CoworkerClient {
  private readonly base: string;
  constructor(base: string, private readonly getToken: () => Promise<string | null>) {
    // Build configuration only. Never use the writing editor's localStorage
    // API override for authenticated workspace traffic.
    this.base = trustedBase(base);
  }

  private async headers(extra?: HeadersInit) {
    const token = await this.getToken();
    if (!token) throw new WorkspaceError("Please sign in again to continue.", 401);
    const headers = new Headers(extra);
    headers.set("Authorization", "Bearer " + token);
    return headers;
  }

  private async response(path: string, options: RequestInit = {}, timeout = 20000) {
    if (!path.startsWith("/api/v1/") || path.includes("..") || path.includes("\\")) throw new WorkspaceError("Invalid workspace route.");
    const response = await fetchWithTimeout(this.base + path, {
      ...options, headers: await this.headers(options.headers), credentials: "omit", redirect: "error", cache: "no-store",
    }, timeout);
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new WorkspaceError(typeof body?.error?.message === "string" ? body.error.message : "Your workspace could not be reached. Please try again.", response.status);
    }
    return response;
  }

  private async json<T>(path: string, options: RequestInit = {}): Promise<T> {
    return (await this.response(path, options)).json() as Promise<T>;
  }
  me(signal?: AbortSignal) { return this.json<Workspace>("/api/v1/me", { signal }); }
  list(signal?: AbortSignal) { return this.json<{ tasks: CoworkerTask[] }>("/api/v1/tasks", { signal }); }
  documents(signal?: AbortSignal) { return this.json<{ documents: SourceDocument[] }>("/api/v1/documents", { signal }); }
  deleteDocument(id: string) { return this.json<{ message: string }>(`/api/v1/documents/${identifier(id)}`, { method: "DELETE" }); }
  task(id: string, signal?: AbortSignal) { return this.json<CoworkerTask>(`/api/v1/tasks/${identifier(id)}`, { signal }); }
  cancel(id: string) { return this.json<CoworkerTask>(`/api/v1/tasks/${identifier(id)}/cancel`, { method: "POST" }); }
  create(input: TaskInput, key: string) {
    return this.json<CoworkerTask>("/api/v1/tasks", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(input) });
  }

  async upload(file: File): Promise<SourceDocument> {
    if (!/\.(txt|docx|pdf)$/i.test(file.name) || file.size < 1 || file.size > 8 * 1024 * 1024) {
      throw new WorkspaceError("Choose a TXT, DOCX, or text-based PDF file up to 8 MB.");
    }
    const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
    const document = await this.json<SourceDocument>("/api/v1/documents", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, byte_size: file.size, sha256 }) });
    return (await this.response(`/api/v1/documents/${identifier(document.id)}/content`, { method: "PUT", body: file }, 40000)).json();
  }

  async download(artifact: Artifact) {
    const id = identifier(artifact.id);
    const value = await this.json<{ url: string | null; content_path: string | null }>(`/api/v1/artifacts/${id}/download`);
    let href: string;
    let revoke = false;
    if (value.url) {
      const url = new URL(value.url);
      if (url.protocol !== "https:" || url.username || url.password) throw new WorkspaceError("The download link is invalid.");
      href = url.href;
    } else {
      const expected = `/api/v1/artifacts/${id}/content`;
      if (value.content_path !== expected) throw new WorkspaceError("The download link is invalid.");
      href = URL.createObjectURL(await (await this.response(expected)).blob());
      revoke = true;
    }
    // Never attach the account token to an object-storage URL.
    const anchor = document.createElement("a");
    anchor.href = href; anchor.download = artifact.filename; anchor.rel = "noreferrer";
    document.body.append(anchor); anchor.click(); anchor.remove();
    if (revoke) setTimeout(() => URL.revokeObjectURL(href), 10000);
  }

  private async stream(id: string, after: number, signal: AbortSignal, receive: (event: ProgressEvent) => void) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) controller.abort();
    const timer = setTimeout(abort, 30000);
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      const response = await fetch(`${this.base}/api/v1/tasks/${identifier(id)}/events?stream=true&after=${after}`, {
        headers: await this.headers({ Accept: "text/event-stream" }), signal: controller.signal,
        credentials: "omit", redirect: "error", cache: "no-store",
      });
      if (!response.ok || !response.headers.get("Content-Type")?.includes("text/event-stream") || !response.body) {
        throw new WorkspaceError("Reconnecting to your task…", response.status);
      }
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        if (buffer.length > 65536) throw new WorkspaceError("Progress response was too large.");
        let boundary: number;
        while ((boundary = buffer.indexOf("\n\n")) >= 0) {
          const event = parseProgress(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
          if (event) receive(event);
        }
      }
    } finally {
      clearTimeout(timer); signal.removeEventListener("abort", abort);
      await reader?.cancel().catch(() => undefined);
    }
  }

  async watch(id: string, signal: AbortSignal, snapshot: (task: CoworkerTask) => void,
              progress: (event: ProgressEvent) => void, connection: (message: string) => void) {
    let cursor = 0;
    while (!signal.aborted) {
      try {
        const task = await this.task(id, signal);
        if (signal.aborted) return;
        cursor = Math.max(cursor, task.event_sequence);
        snapshot(task); connection("");
        if (terminal(task.state)) return;
        await this.stream(id, cursor, signal, event => {
          if (signal.aborted || event.sequence <= cursor) return;
          cursor = event.sequence; progress(event);
        });
        await pause(700, signal);
      } catch (error) {
        if (signal.aborted) return;
        if (error instanceof WorkspaceError && [401, 404].includes(error.status)) { connection(error.message); return; }
        connection("Reconnecting. Your task continues in the background.");
        // Fetching the snapshot at the top of the loop is the polling fallback.
        await pause(4000, signal).catch(() => undefined);
      }
    }
  }
}
