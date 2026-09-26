import { fetchWithTimeout } from "../lib/fetchWithTimeout";

export type TaskState = "queued" | "running" | "cancelling" | "completed" | "needs_input" | "failed" | "cancelled";
export type Artifact = { id: string; filename: string; content_type: string; byte_size: number; sha256: string; created_at?: string };
export type SkillId = "report_email" | "email" | "document" | "career" | "social" | "meeting" | "daily_plan" | "personal_plan" | "presentation" | "spreadsheet" | "research";
export type ResearchOptions = { query: string; time_range: "any" | "day" | "week" | "month" | "year" };
export type ResearchSource = { id: string; label: string; sha256: string; kind?: "web"; url?: string; retrieved_at?: string; source_date?: string | null; truncated?: boolean };
export type WorkSkill = { id: SkillId; name: string; description: string; instruction: string; output: string };
export type DraftMetadata = { output_language: string; missing_information: string[] };
export type WorkSection = { heading: string; paragraphs: string[]; bullets: string[]; source_ids: string[] };
export type EmailDraft = { subject: string; body: string };
export type ConnectedAccount = { id: string; provider: "google" | "microsoft" | "linkedin"; capability: "email" | "calendar" | "drive" | "social"; email: string; active: boolean };
export type ActionRecipient = { id: string; name: string; email: string; created_at: string; updated_at: string };
export type EmailAction = { kind: "email_send"; to: string[]; cc: string[]; bcc: string[]; subject: string; body: string };
export type AttachmentEmailAction = { kind: "email_send_with_attachments"; to: string[]; cc: string[]; bcc: string[]; subject: string; body: string };
export type EmailThreadReplyAction = { kind: "email_thread_reply"; parent_action_id: string; to: string[]; cc: string[]; bcc: []; subject: string; body: string };
export type CalendarAction = { kind: "calendar_create"; title: string; description: string; location: string; start_at: string; end_at: string; time_zone: string; attendees: string[] };
export type CalendarReminderAction = { kind: "calendar_create_with_reminder"; title: string; description: string; location: string; start_at: string; end_at: string; time_zone: string; attendees: string[]; reminder_minutes_before_start: 5 | 10 | 15 | 30 | 60 | 120 | 1440 };
export type DocumentShareAction = { kind: "document_share"; recipients: string[] };
export type LinkedInSocialPublishAction = { kind: "social_publish_linkedin"; text: string };
export type ActionPayload = EmailAction | AttachmentEmailAction | EmailThreadReplyAction | CalendarAction | CalendarReminderAction | DocumentShareAction | LinkedInSocialPublishAction;
export type ActionInput = { connection_id: string; payload: ActionPayload; attachment_ids?: string[]; artifact_ids?: string[] };
export type ActionAttachment = { id: string; filename: string; content_type: string; byte_size: number; sha256: string };
export type AgentRunState = "queued" | "planning" | "running" | "awaiting_approval" | "needs_input" | "blocked" | "completed" | "failed" | "cancelled";
export type AgentTool = { name: string; version: string; kind: "task" | "approved_action"; consequential: boolean; approval_required: boolean; timeout_seconds: number };
export type AgentActionProposal = {
  id: string; kind: EmailAction["kind"] | CalendarAction["kind"] | LinkedInSocialPublishAction["kind"]; payload: EmailAction | CalendarAction | LinkedInSocialPublishAction; rationale: string;
  proposal_hash: string; state: "suggested" | "promoting" | "promoted" | "dismissed" | "expired";
  promoted_action_id: string | null; created_at: string; expires_at: string; promoted_at: string | null; dismissed_at: string | null;
};
export type AgentStep = { id: string; ordinal: number; tool: string | null; state: string; error_code: string | null; depends_on: number[] };
export type PersonalGoalState = "draft" | "active" | "paused" | "blocked" | "completed" | "cancelled" | "archived";
export type PersonalGoal = {
  id: string; objective: string; success_criteria: string[]; constraints: string[];
  deadline_at: string | null; timezone: string; revision: number; state: PersonalGoalState;
  milestones: { label: string; due_at: string | null; completed: boolean }[];
  budget: { max_runs: number; max_planner_tokens: number | null };
  authorized_resources: { kind: "document" | "memory_namespace"; reference: string }[];
  next_review_at: string | null; created_at: string; updated_at: string;
  run_links: { run_id: string; goal_revision: number; state: AgentRunState; created_at: string }[];
};
export type PersonalGoalCreate = {
  objective: string; success_criteria: string[]; constraints: string[]; deadline_at: string | null;
  timezone: string; state: "draft" | "active"; milestones: { label: string; due_at: string | null; completed: boolean }[];
  budget: { max_runs: number; max_planner_tokens: number | null }; authorized_resources: []; next_review_at: string | null;
};
export type AutomationSchedule = { kind: "daily" | "weekly"; hour: number; minute: number; weekdays: string[] };
export type PersonalAutomation = {
  id: string; goal_id: string; goal_revision: number; revision: number; state: "active" | "paused" | "cancelled";
  timezone: string; schedule: AutomationSchedule; output_language: string; overlap_policy: "skip" | "buffer_one";
  catchup_window_seconds: number; quiet_hours: { start: string; end: string } | null; expires_at: string | null;
  schedule_applied_revision: number | null; schedule_applied_enabled: boolean; schedule_error_code: string | null;
  created_at: string; updated_at: string;
};
export type MemoryFact = {
  id: string; namespace: "profile" | "preferences" | "project" | "organization" | "writing";
  key: string; value: string; language: string; version: number; active: boolean;
};
export type MemoryProposal = {
  id: string; run_id: string; namespace: MemoryFact["namespace"]; key: string; value: string; language: string;
  source_refs: { source_id: string; type: string; document_id?: string; version_id?: string; sha256?: string }[];
  state: "proposed" | "accepted" | "rejected" | "expired"; accepted_fact_id: string | null;
  expires_at: string; created_at: string; reviewed_at: string | null;
};
export type AgentContext = {
  enabled: boolean;
  items: { source_id: string; label: string; excerpt: string; sha256: string; provenance: { document_id: string; version_id: string } }[];
  invalidated: { source_id: string; label: string; reason: string }[];
  memory: { facts: { namespace: string; key: string; value: string; language: string }[]; provenance: { id: string; version: number }[] };
};

export type AgentNotification = {
  id: string; automation_id: string | null; occurrence_id: string | null; kind: string; title: string; message: string;
  state: "delivered" | "read"; visible_at: string; read_at: string | null; created_at: string;
};
export type AgentRun = {
  id: string; persistent_goal_id: string | null; persistent_goal_revision: number | null; goal: string; output_language: string; document_ids: string[]; action_ids: string[]; action_proposals: AgentActionProposal[];
  memory_namespaces: string[]; state: AgentRunState; phase: string; message: string; error_code: string | null; cancel_requested: boolean;
  event_sequence: number; planner_calls: number; planner_tokens: number; planner_mode: string | null;
  runtime_version: number; planner_actual_tokens: number; planner_cost_microusd: number;
  decisions: { sequence: number; planner_call: number; decision: string; payload: Record<string, unknown>; model: string; prompt_sha256: string; tool_schema_sha256: string; observation_count: number; total_tokens: number | null; cost_microusd: number | null; created_at: string }[];
  created_at: string; updated_at: string; deadline_at: string;
  steps: AgentStep[]; tool_invocations: { id: string; step_id: string; tool: string; version: string; state: string; consequential: boolean; approval_required: boolean;
    receipt: { status: string; resource_type: string; resource_id: string | null; summary: Record<string, unknown>; created_at: string } | null }[];
};
export type AgentRunInput = { goal: string; document_ids: string[]; action_ids: string[]; memory_namespaces: string[]; output_language: string };
export type ExternalAction = {
  id: string; connection_id: string; kind: ActionPayload["kind"];
  state: "awaiting_approval" | "queued" | "executing" | "succeeded" | "failed" | "cancelled" | "expired" | "outcome_unknown";
  preview: { account: string; provider: "google" | "microsoft" | "linkedin"; payload: ActionPayload; attachments?: ActionAttachment[]; shared_artifact?: ActionAttachment; document_sharing?: { source: string; access: "reader"; notifications: "recipient" }; reply_context?: { parent_action_id: string; root_action_id: string; thread_id: string; parent_message_id: string; parent_provider_id: string; references: string[] }; expires_at: string; calendar: string | null; guest_notifications: string | null };
  preview_hash: string; message: string; error_code: string | null; created_at: string; expires_at: string;
  approved_at: string | null; finished_at: string | null;
  receipt: { provider: string; provider_id?: string; thread_id?: string; status: string; confirmed_at: string; message_id?: string; recipient?: string; access?: string; artifact_sha256?: string; author?: string; visibility?: string } | null;
  audit?: { action: string; created_at: string }[];
};
export type CellFormat = "text" | "number" | "integer" | "percent";
export type TablePreview = { columns: { id: string; label: string; format: CellFormat; aggregate: string; calculated: boolean }[]; rows: (string | number | null)[][]; totals: (number | null)[] };
export type CoworkerDraft = DraftMetadata & (
  | { kind?: never; report: { title: string; summary: string; sections: { heading: string; paragraphs: string[]; source_ids: string[] }[] }; email: EmailDraft }
  | { kind: "email"; email: EmailDraft; source_ids: string[] }
  | { kind: "document"; document: { title: string; summary: string; sections: WorkSection[] } }
  | { kind: "social"; title: string; posts: { platform: "facebook" | "linkedin" | "other"; label: string; text: string; suggested_timing: string | null; source_ids: string[] }[] }
  | { kind: "meeting"; title: string; summary: string; labels: { notes: string; decisions: string; actions: string; owner: string; deadline: string; recorded: string; suggested: string };
      notes: { text: string; source_ids: string[] }[]; decisions: { text: string; source_ids: string[] }[];
      actions: { text: string; owner: string | null; deadline: string | null; basis: "recorded" | "suggested"; source_ids: string[] }[] }
  | { kind: "plan"; title: string; overview: string; labels: Record<"high" | "normal" | "low" | "provided" | "suggested", string>;
      items: { task: string; when: string; priority: "high" | "normal" | "low"; basis: "provided" | "suggested"; source_ids: string[] }[] }
  | { kind: "presentation"; title: string; slides: { layout: "cover" | "content" | "chart"; title: string; bullets: string[]; speaker_notes: string; source_ids: string[];
      chart: { kind: "bar" | "line"; categories: string[]; series: { label: string; values: number[] }[]; unit: string } | null }[] }
  | { kind: "spreadsheet"; title: string; summary: string; summary_label: string; sheet_name: string; source_ids: string[]; chart: { title: string } | null }
  | { kind: "research"; title: string; labels: Record<"sources" | "evidence" | "retrieved" | "source_date" | "undated" | "gaps", string>;
      findings: { heading: string; text: string; citations: { source_id: string; quote: string }[] }[] }
);
export type CoworkerTask = {
  id: string; state: TaskState; phase: string; message: string; error_code: string | null;
  instruction: string; output_language: string; created_at: string; event_sequence: number;
  skill_id?: SkillId; workflow_version?: string;
  input: { notes: string; document_ids: string[]; research?: ResearchOptions } | null;
  artifacts: Artifact[]; usage: { model_attempts: number; accounted_tokens: number };
  draft: CoworkerDraft | null;
  preview?: TablePreview | null;
  sources: ResearchSource[];
  research?: (ResearchOptions & { retrieved_at: string; skipped_results: number }) | null;
};
export type Workspace = {
  account_id: string; workspace_name: string; preferences: { language?: string };
  usage: { tasks_today: number }; limits: { daily_tasks: number; upload_bytes: number };
};
export type SourceDocument = { id: string; filename: string; state: string; byte_size: number };
export type TaskInput = { skill_id?: SkillId; instruction: string; notes: string; document_ids: string[]; output_language: string; research?: ResearchOptions };
export type ProgressEvent = { sequence: number; state: TaskState; phase: string; message: string };
export const terminal = (state: TaskState) => ["completed", "needs_input", "failed", "cancelled"].includes(state);

export class WorkspaceError extends Error {
  constructor(message: string, readonly status = 0) { super(message); }
}

export function sourceLink(value?: string): string | undefined {
  if (!value || value.length > 2048 || /[\s\\\x00-\x1f\x7f]/.test(value)) return;
  try {
    if (/[\x00-\x1f\x7f\\]/.test(decodeURIComponent(value))) return;
    const url = new URL(value);
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || url.port ||
        !/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}$/.test(url.hostname) ||
        /\.(localhost|local|internal|lan|home|invalid|test|onion)$/.test(url.hostname)) return;
    return url.href;
  } catch { return; }
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
  skills(signal?: AbortSignal) { return this.json<{ skills: WorkSkill[]; upload_formats?: string[] }>("/api/v1/skills", { signal }); }
  list(signal?: AbortSignal) { return this.json<{ tasks: CoworkerTask[] }>("/api/v1/tasks", { signal }); }
  documents(signal?: AbortSignal) { return this.json<{ documents: SourceDocument[] }>("/api/v1/documents", { signal }); }
  deleteDocument(id: string) { return this.json<{ message: string }>(`/api/v1/documents/${identifier(id)}`, { method: "DELETE" }); }
  task(id: string, signal?: AbortSignal) { return this.json<CoworkerTask>(`/api/v1/tasks/${identifier(id)}`, { signal }); }
  cancel(id: string) { return this.json<CoworkerTask>(`/api/v1/tasks/${identifier(id)}/cancel`, { method: "POST" }); }
  connections(signal?: AbortSignal) { return this.json<{ enabled: boolean; reminders_enabled: boolean; document_sharing_enabled: boolean; threading_enabled: boolean; social_publishing_enabled: boolean; connections: ConnectedAccount[] }>("/api/v1/connections", { signal }); }
  connectGoogle(capability: "email" | "calendar" | "drive") {
    return this.json<{ authorization_url: string; state: string }>("/api/v1/connections/google/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ capability }) });
  }
  finishGoogle(code: string, state: string) {
    return this.response("/api/v1/connections/google/finish", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code, state }) }, 45000).then(response => response.json() as Promise<ConnectedAccount>);
  }
  connectMicrosoft(capability: "email" | "calendar") {
    return this.json<{ authorization_url: string; state: string }>("/api/v1/connections/microsoft/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ capability }) });
  }
  finishMicrosoft(code: string, state: string) {
    return this.response("/api/v1/connections/microsoft/finish", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code, state }) }, 45000).then(response => response.json() as Promise<ConnectedAccount>);
  }
  connectLinkedIn() {
    return this.json<{ authorization_url: string; state: string }>("/api/v1/connections/linkedin/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ capability: "social" }) });
  }
  finishLinkedIn(code: string, state: string) {
    return this.response("/api/v1/connections/linkedin/finish", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code, state }) }, 45000).then(response => response.json() as Promise<ConnectedAccount>);
  }
  disconnect(id: string) { return this.json<{ message: string }>(`/api/v1/connections/${identifier(id)}`, { method: "DELETE" }); }
  actionRecipients(signal?: AbortSignal) { return this.json<{ enabled: boolean; recipients: ActionRecipient[] }>("/api/v1/action-recipients", { signal }); }
  createActionRecipient(name: string, email: string) {
    return this.json<ActionRecipient>("/api/v1/action-recipients", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, email }) });
  }
  updateActionRecipient(id: string, name: string, email: string) {
    return this.json<ActionRecipient>(`/api/v1/action-recipients/${identifier(id)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, email }) });
  }
  deleteActionRecipient(id: string) { return this.json<{ deleted: boolean; id: string }>(`/api/v1/action-recipients/${identifier(id)}`, { method: "DELETE" }); }
  actionArtifacts(signal?: AbortSignal) { return this.json<{ attachments_enabled: boolean; document_sharing_enabled: boolean; artifacts: Artifact[] }>("/api/v1/artifacts", { signal }); }
  actions(signal?: AbortSignal) { return this.json<{ actions: ExternalAction[] }>("/api/v1/actions", { signal }); }
  action(id: string, signal?: AbortSignal) { return this.json<ExternalAction>(`/api/v1/actions/${identifier(id)}`, { signal }); }
  prepareAction(input: ActionInput, key: string) {
    return this.json<ExternalAction>("/api/v1/actions", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(input) });
  }
  approveAction(action: ExternalAction) {
    return this.json<ExternalAction>(`/api/v1/actions/${identifier(action.id)}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preview_hash: action.preview_hash }) });
  }
  cancelAction(id: string) { return this.json<ExternalAction>(`/api/v1/actions/${identifier(id)}/cancel`, { method: "POST" }); }
  reconcileAction(id: string) { return this.response(`/api/v1/actions/${identifier(id)}/reconcile`, { method: "POST" }, 65000).then(response => response.json() as Promise<ExternalAction>); }
  goals(signal?: AbortSignal) { return this.json<{ enabled: boolean; goals: PersonalGoal[] }>("/api/v1/goals", { signal }); }
  goal(id: string, signal?: AbortSignal) { return this.json<PersonalGoal>(`/api/v1/goals/${identifier(id)}`, { signal }); }
  createGoal(input: PersonalGoalCreate, key: string) {
    return this.json<PersonalGoal>("/api/v1/goals", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(input) });
  }
  updateGoal(id: string, revision: number, input: Partial<Pick<PersonalGoalCreate, "objective" | "success_criteria" | "constraints" | "deadline_at" | "timezone" | "milestones" | "budget" | "next_review_at">>) {
    return this.json<PersonalGoal>(`/api/v1/goals/${identifier(id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: revision, ...input }) });
  }
  transitionGoal(id: string, revision: number, action: "pause" | "resume" | "cancel") {
    return this.json<PersonalGoal>(`/api/v1/goals/${identifier(id)}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: revision }) });
  }
  runGoal(id: string, revision: number, outputLanguage: string, key: string) {
    return this.json<AgentRun>(`/api/v1/goals/${identifier(id)}/run`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify({ expected_revision: revision, output_language: outputLanguage }) });
  }
  automations(signal?: AbortSignal) { return this.json<{ enabled: boolean; automations: PersonalAutomation[] }>("/api/v1/automations", { signal }); }
  createAutomation(input: {
    goal_id: string; goal_revision: number; timezone: string; schedule: AutomationSchedule; output_language: string;
    overlap_policy: "skip" | "buffer_one"; catchup_window_seconds: number;
    quiet_hours: { start: string; end: string } | null; expires_at: string | null;
  }, key: string) {
    return this.json<PersonalAutomation>("/api/v1/automations", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(input) });
  }
  transitionAutomation(id: string, revision: number, action: "pause" | "resume" | "cancel") {
    return this.json<PersonalAutomation>(`/api/v1/automations/${identifier(id)}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: revision }) });
  }
  notifications(signal?: AbortSignal) { return this.json<{ enabled: boolean; notifications: AgentNotification[] }>("/api/v1/notifications", { signal }); }
  readNotification(id: string) { return this.json<{ id: string; state: "read"; read_at: string }>(`/api/v1/notifications/${identifier(id)}/read`, { method: "POST" }); }
  memory(signal?: AbortSignal) { return this.json<{ enabled: boolean; facts: MemoryFact[] }>("/api/v1/memory", { signal }); }
  memoryProposals(signal?: AbortSignal) { return this.json<{ enabled: boolean; proposals: MemoryProposal[] }>("/api/v1/memory-proposals", { signal }); }
  acceptMemoryProposal(id: string) { return this.json<{ proposal: MemoryProposal; fact: MemoryFact | null }>(`/api/v1/memory-proposals/${identifier(id)}/accept`, { method: "POST" }); }
  rejectMemoryProposal(id: string) { return this.json<MemoryProposal>(`/api/v1/memory-proposals/${identifier(id)}/reject`, { method: "POST" }); }
  agentContext(id: string, signal?: AbortSignal) { return this.json<AgentContext>(`/api/v1/agent-runs/${identifier(id)}/context`, { signal }); }
  agentTools(signal?: AbortSignal) { return this.json<{ enabled: boolean; tools: AgentTool[] }>("/api/v1/agent-tools", { signal }); }
  agentRuns(signal?: AbortSignal) { return this.json<{ runs: AgentRun[] }>("/api/v1/agent-runs", { signal }); }
  agentRun(id: string, signal?: AbortSignal) { return this.json<AgentRun>(`/api/v1/agent-runs/${identifier(id)}`, { signal }); }
  createAgentRun(input: AgentRunInput, key: string) {
    return this.json<AgentRun>("/api/v1/agent-runs", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(input) });
  }
  cancelAgentRun(id: string) { return this.json<AgentRun>(`/api/v1/agent-runs/${identifier(id)}/cancel`, { method: "POST" }); }
  promoteActionProposal(runId: string, proposalId: string, proposalHash: string, connectionId: string) {
    return this.json<ExternalAction>(`/api/v1/agent-runs/${identifier(runId)}/action-proposals/${identifier(proposalId)}/promote`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ connection_id: identifier(connectionId), proposal_hash: proposalHash }),
    });
  }
  dismissActionProposal(runId: string, proposalId: string, proposalHash: string) {
    return this.json<AgentActionProposal>(`/api/v1/agent-runs/${identifier(runId)}/action-proposals/${identifier(proposalId)}/dismiss`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ proposal_hash: proposalHash }),
    });
  }
  create(input: TaskInput, key: string) {
    return this.json<CoworkerTask>("/api/v1/tasks", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(input) });
  }

  async upload(file: File): Promise<SourceDocument> {
    if (!/\.(txt|docx|pdf|csv|xlsx|pptx)$/i.test(file.name) || file.size < 1 || file.size > 8 * 1024 * 1024) {
      throw new WorkspaceError("Choose a supported document, presentation, or spreadsheet up to 8 MB.");
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
