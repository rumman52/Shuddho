import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoworkerClient, WorkspaceError, isTextArtifact, terminal, type ConversationRecord, type CoworkerTask, type CoworkerView, type EmailDraft, type ResearchOptions, type SkillId, type SourceDocument, type WorkSkill, type Workspace } from "./client";
import DraftPreview, { draftTitle } from "./DraftPreview";
import ActionWorkspace from "./ActionWorkspace";
import AgentWorkspace from "./AgentWorkspace";
import ConversationWorkspace from "./ConversationWorkspace";
import WorkspaceNavigation from "./WorkspaceNavigation";
import PluginsWorkspace from "./PluginsWorkspace";
import ProjectWorkspace from "./ProjectWorkspace";
import FilesWorkspace from "./FilesWorkspace";
import SettingsWorkspace from "./SettingsWorkspace";
import { RukhCompanionMark } from "./CoworkerWelcome";
import NavigationIcon from "./WorkspaceNavigationIcon";
import GoalWorkspace from "./GoalWorkspace";
import AutomationWorkspace from "./AutomationWorkspace";
import BrowserWorkspace from "./BrowserWorkspace";
import FlyWorkspace from "./FlyWorkspace";
import NegotiationWorkspace from "./NegotiationWorkspace";
import TransactionWorkspace from "./TransactionWorkspace";
import { hasPendingGoogleCallback } from "./googleCallback";
import { hasPendingMicrosoftCallback } from "./microsoftCallback";
import { hasPendingLinkedInCallback } from "./linkedinCallback";
import { requestedNotificationView } from "./pushNavigation";
import { getInitialCoworkerViewFromLocation } from "../../../coworker/src/navigation.mjs";


const originalService: WorkSkill = {
  id: "report_email", name: "Report & email", description: "Turn your sources into a report and an email draft.",
  instruction: "Turn these sources into a professional report and a short email sharing the key findings.",
  output: "Report, email, DOCX, PDF",
};

const labels = { queued: "Queued", running: "In progress", cancelling: "Stopping", completed: "Ready", needs_input: "Details needed", failed: "Could not finish", cancelled: "Cancelled" };
const languages = [
  ["auto", "Same as source"], ["en", "English"], ["bn", "বাংলা · Bangla"], ["hi", "हिन्दी · Hindi"],
  ["ar", "العربية · Arabic"], ["es", "Español · Spanish"], ["fr", "Français · French"], ["de", "Deutsch · German"],
  ["pt", "Português · Portuguese"], ["ur", "اردو · Urdu"], ["zh", "中文 · Chinese"], ["ja", "日本語 · Japanese"],
  ["ko", "한국어 · Korean"], ["it", "Italiano · Italian"], ["ru", "Русский · Russian"], ["id", "Bahasa Indonesia"],
  ["tr", "Türkçe · Turkish"], ["vi", "Tiếng Việt · Vietnamese"], ["ta", "தமிழ் · Tamil"], ["te", "తెలుగు · Telugu"],
  ["mr", "मराठी · Marathi"], ["ne", "नेपाली · Nepali"], ["fa", "فارسی · Persian"], ["he", "עברית · Hebrew"],
  ["th", "ไทย · Thai"], ["ms", "Bahasa Melayu"], ["nl", "Nederlands · Dutch"], ["pl", "Polski · Polish"],
  ["uk", "Українська · Ukrainian"], ["sv", "Svenska · Swedish"], ["sw", "Kiswahili · Swahili"], ["fil", "Filipino"],
];
const message = (error: unknown) => error instanceof Error ? error.message : "This action could not finish. Please try again.";

export function TaskResult({ task, client, revise, prepareEmail, prepareSocial }: { task: CoworkerTask; client: CoworkerClient; revise: () => void; prepareEmail?: (draft: EmailDraft) => void; prepareSocial?: (text: string) => void }) {
  const [downloadError, setDownloadError] = useState("");
  const [downloading, setDownloading] = useState("");
  const draft = task.draft;
  return <section className="cw-result" aria-label="Task result" data-task-id={task.id}>
    <div className="cw-result-heading"><div><span className="cw-eyebrow">Your work</span><h2 dir="auto" lang={draft?.output_language}>{draft ? draftTitle(draft) : "Your draft"}</h2></div><span className={`cw-status cw-status-${task.state}`}>{labels[task.state]}</span></div>
    <p role="status" className={task.state === "failed" ? "cw-error" : "cw-task-message"}>{task.message}</p>
    {!terminal(task.state) && <ol className="cw-steps" aria-label="Task progress">
      {[["extract", "Read sources"], ...(task.skill_id === "research" ? [["research", "Search the web"]] : []), ["draft", "Prepare drafts"], ["export", "Create files"], ["complete", "Check downloads"]].map(([phase, label], index) =>
        <li key={phase} aria-current={task.phase === phase ? "step" : undefined}><span>{index + 1}</span>{label}</li>)}
    </ol>}
    {draft && <>
      {draft.missing_information.length > 0 && <aside className="cw-missing"><strong>A few details need your input</strong><ul>{draft.missing_information.map((item, index) => <li key={index} dir="auto">{item}</li>)}</ul><button type="button" className="cw-secondary" onClick={revise}>Add details & revise</button></aside>}
      <DraftPreview draft={draft} sources={task.sources} preview={task.preview} />
      {prepareEmail && "email" in draft && terminal(task.state) && <button className="cw-secondary" onClick={() => prepareEmail(draft.email)}>Prepare this email for sending</button>}
      {prepareSocial && draft.kind === "social" && terminal(task.state) && draft.posts.filter(post => post.platform === "linkedin").map((post, index) => <button key={"linkedin-" + index} className="cw-secondary" onClick={() => prepareSocial(post.text)}>Prepare this LinkedIn post for publishing</button>)}
      {task.research && <p className="cw-fineprint">Search: <bdi>{task.research.query}</bdi> · Date range: {task.research.time_range === "any" ? "Any time" : `Past ${task.research.time_range}`}. {task.research.skipped_results > 0 && `${task.research.skipped_results} results were excluded because usable evidence was unavailable, duplicated, or outside the date range.`}</p>}
      <p className="cw-fineprint">{task.skill_id === "research" ? "Review each finding against its evidence. Source dates are estimates of publication or update; retrieval today does not establish current accuracy." : "Review the facts and wording before using these drafts. Source references point to your provided material."}</p>
    </>}
    {task.artifacts.length > 0 && <div className="cw-downloads" aria-label="Downloads">{task.artifacts.map(artifact => <div className="cw-download-item" key={artifact.id}>
      <button type="button" className="cw-secondary" disabled={Boolean(downloading)} onClick={async () => {
        setDownloadError(""); setDownloading(artifact.id);
        try { await client.download(artifact); } catch (error) { setDownloadError(message(error)); }
        finally { setDownloading(""); }
      }}><span aria-hidden="true">↓ </span>{downloading === artifact.id ? "Preparing…" : artifact.filename}</button>
      {isTextArtifact(artifact) && <a className="cw-secondary cw-open-editor-link" href={`/writing?artifact_id=${encodeURIComponent(artifact.id)}`}>Open in Writing Assistant</a>}
    </div>)}</div>}
    {downloadError && <p className="cw-error" role="alert">{downloadError}</p>}
    {terminal(task.state) && task.input && <button type="button" className="cw-text-button" onClick={revise}>Use these sources for a new draft</button>}
  </section>;
}

export default function CoworkerWorkspace({ client, email, signOut, initialDraft = "", onInitialDraftChange }: {
  client: CoworkerClient;
  email: string;
  signOut: () => Promise<void>;
  initialDraft?: string;
  onInitialDraftChange?: (draft: string) => void;
}) {
  const [newChatRevision, setNewChatRevision] = useState(0);
  const [projectEntryRevision, setProjectEntryRevision] = useState(0);
  const [projectCreateMode, setProjectCreateMode] = useState(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("view") === "projects";
  });
  const [view, setView] = useState<CoworkerView>(() => {
    if (hasPendingGoogleCallback() || hasPendingMicrosoftCallback() || hasPendingLinkedInCallback()) return "actions";
    // An explicit Fly deep link wins over a saved, unsent Coworker draft.
    // Previously the draft forced /fly to mount Coworker instead.
    if (typeof window !== "undefined" && String(window.location?.pathname ?? "").replace(/\/+$/, "") === "/fly") return "sandbox";
    if (typeof window !== "undefined") {
      const explicitView = new URLSearchParams(window.location.search).get("view");
      const locationView = getInitialCoworkerViewFromLocation(window.location.pathname, window.location.search);
      // An explicit workspace destination (including Projects after sign-in)
      // must win over a saved, unsent Coworker draft.
      if (explicitView && explicitView !== "conversations") return locationView;
      if (initialDraft.trim()) return "conversations";
      return requestedNotificationView(window.location.search) ?? locationView;
    }
    return "conversations";
  });
  const [actionDraft, setActionDraft] = useState<EmailDraft | null>(null);
  const [socialActionDraft, setSocialActionDraft] = useState<string | null>(null);
  const [focusAgentRunId, setFocusAgentRunId] = useState<string | null>(null);
  const [focusActionId, setFocusActionId] = useState<string | null>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const navigationRef = useRef<HTMLElement | null>(null);
  const navigationTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [recentConversations, setRecentConversations] = useState<ConversationRecord[]>([]);
  const [recentSearch, setRecentSearch] = useState("");
  const [recentSearchOpen, setRecentSearchOpen] = useState(false);
  const [skills, setSkills] = useState<WorkSkill[]>([originalService]);
  const [uploadFormats, setUploadFormats] = useState(["txt", "docx", "pdf"]);
  const [skillId, setSkillId] = useState<SkillId>("report_email");
  const [research, setResearch] = useState<ResearchOptions>({ query: "", time_range: "any" });
  const [history, setHistory] = useState<CoworkerTask[]>([]);
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [task, setTask] = useState<CoworkerTask | null>(null);
  const [instruction, setInstruction] = useState(originalService.instruction);
  const [notes, setNotes] = useState("");
  const [language, setLanguage] = useState("en");
  const [customLanguage, setCustomLanguage] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [connection, setConnection] = useState("");
  const [reload, setReload] = useState(0);
  const submission = useRef<{ fingerprint: string; key: string }>();
  const accountEmail = useRef(email);
  const notesInput = useRef<HTMLTextAreaElement>(null);
  const outputColumn = useRef<HTMLDivElement>(null);
  const activeSkill = skills.find(skill => skill.id === skillId);
  const accountLabel = workspace?.workspace_name?.trim() || email;
  const recentChatItems = recentConversations
    .filter(item => !recentSearch.trim() || item.title.toLocaleLowerCase().includes(recentSearch.trim().toLocaleLowerCase()))
    .slice(0, 3);

  useEffect(() => {
    if (accountEmail.current === email) return;
    accountEmail.current = email;
    setView("drafts");
    setActionDraft(null);
    setSocialActionDraft(null);
    setFocusActionId(null);
    setFocusAgentRunId(null);
    setWorkspace(null);
    setSkills([originalService]);
    setUploadFormats(["txt", "docx", "pdf"]);
    setSkillId("report_email");
    setResearch({ query: "", time_range: "any" });
    setHistory([]);
    setDocuments([]);
    setSelectedDocs([]);
    setSelected("");
    setTask(null);
    setInstruction(originalService.instruction);
    setNotes("");
    setLanguage("en");
    setCustomLanguage("");
    setBusy("");
    setError("");
    setNotice("");
    setConnection("");
    submission.current = undefined;
  }, [email]);

  function navigateView(nextView: CoworkerView) {
    if (nextView === "projects") {
      setProjectEntryRevision(value => value + 1);
      setProjectCreateMode(true);
    } else {
      setProjectCreateMode(false);
    }
    if (typeof window !== "undefined" && window.history?.pushState) {
      const destination = new URL(nextView === "sandbox" ? "/fly" : "/coworker", window.location.origin);
      if (nextView !== "conversations" && nextView !== "sandbox") destination.searchParams.set("view", nextView);
      const nextLocation = destination.pathname + destination.search;
      if (window.location.pathname + window.location.search !== nextLocation) {
        window.history.pushState({ rukhView: nextView }, "", nextLocation);
      }
    }
    setView(nextView);
    setNavigationOpen(false);
  }

  function openRecentConversation(conversationId: string) {
    if (typeof window !== "undefined" && window.history?.pushState) {
      const destination = new URL("/coworker", window.location.origin);
      destination.searchParams.set("conversation", conversationId);
      window.history.pushState({ rukhView: "conversations" }, "", destination.pathname + destination.search);
    }
    setRecentSearch("");
    setRecentSearchOpen(false);
    setView("conversations");
    setNavigationOpen(false);
  }

  function viewTask() {
    const scroll = () => {
      outputColumn.current?.focus({ preventScroll: true });
      outputColumn.current?.scrollIntoView({ block: "start" });
    };
    if (view !== "drafts") { setView("drafts"); requestAnimationFrame(scroll); }
    else scroll();
  }

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    const catalog = client.skills(controller.signal).catch(error => {
      // A Part 2 API supports only the original service. Other failures must
      // surface, especially authentication errors, rather than enabling tools.
      if (error instanceof WorkspaceError && error.status === 404) return { skills: [originalService], upload_formats: ["txt", "docx", "pdf"] };
      throw error;
    });
    Promise.all([client.me(controller.signal), client.list(controller.signal), client.documents(controller.signal), catalog]).then(([profile, tasks, files, catalog]) => {
      if (controller.signal.aborted) return;
      setWorkspace(profile); setHistory(tasks.tasks); setDocuments(files.documents); setSkills(catalog.skills);
      setUploadFormats((catalog.upload_formats ?? ["txt", "docx", "pdf"]).filter(format => ["txt", "docx", "pdf", "csv", "xlsx", "pptx"].includes(format)));
      setSelected(current => {
        if (current && tasks.tasks.some(item => item.id === current)) return current;
        let saved = "";
        try { saved = sessionStorage.getItem("shuddho:coworker:" + profile.account_id) ?? ""; } catch { /* Storage is optional. */ }
        return tasks.tasks.some(item => item.id === saved) ? saved : tasks.tasks[0]?.id ?? "";
      });
    }).catch(error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [client, reload]);

  useEffect(() => {
    if (view === "conversations") return;
    const controller = new AbortController();
    client.conversations(controller.signal).then(({ items }) => {
      if (!controller.signal.aborted) setRecentConversations(items);
    }).catch(() => {
      if (!controller.signal.aborted) setRecentConversations([]);
    });
    return () => controller.abort();
  }, [client, view]);

  useEffect(() => {
    if (!selected || !workspace) return;
    try { sessionStorage.setItem("shuddho:coworker:" + workspace.account_id, selected); } catch { /* Server history is authoritative. */ }
    const controller = new AbortController();
    setTask(null); setConnection("");
    void client.watch(selected, controller.signal, next => {
      setTask(next);
      setHistory(previous => [next, ...previous.filter(item => item.id !== next.id)].sort((a, b) => b.created_at.localeCompare(a.created_at)));
    }, event => setTask(previous => previous?.id === selected ? { ...previous, state: event.state, phase: event.phase, message: event.message, event_sequence: event.sequence } : previous), setConnection);
    return () => controller.abort();
  }, [client, selected, workspace?.account_id]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy("submit"); setError(""); setNotice("");
    const input = { ...(skillId === "report_email" ? {} : { skill_id: skillId }), instruction, notes, document_ids: selectedDocs, output_language: language === "custom" ? customLanguage : language,
      ...(skillId === "research" ? { research } : {}) };
    const fingerprint = JSON.stringify(input);
    if (submission.current?.fingerprint !== fingerprint) submission.current = { fingerprint, key: crypto.randomUUID() };
    try {
      const next = await client.create(input, submission.current.key);
      setTask(next); setSelected(next.id); setHistory(previous => [next, ...previous.filter(item => item.id !== next.id)]);
      if (window.matchMedia("(max-width: 680px)").matches) requestAnimationFrame(viewTask);
      // Retain the key for an unchanged brief, including a lost response. A
      // deliberate revision or changed input starts a new task.
      try { setWorkspace(await client.me()); } catch { /* Task creation already succeeded. History can refresh usage later. */ }
    } catch (error) { setError(message(error)); }
    finally { setBusy(""); }
  }

  function revise() {
    if (!task?.input) return;
    setSkillId(task.skill_id ?? "report_email");
    setInstruction(task.instruction); setNotes(task.input.notes); setSelectedDocs(task.input.document_ids);
    setResearch(task.input.research ?? { query: "", time_range: "any" });
    if (languages.some(([code]) => code === task.output_language)) setLanguage(task.output_language);
    else { setLanguage("custom"); setCustomLanguage(task.output_language); }
    submission.current = undefined;
    setNotice("Your original sources are ready above. Add the missing details or change the request, then create a new draft.");
    notesInput.current?.focus(); notesInput.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  useEffect(() => {
    if (!navigationOpen || typeof document === "undefined" || typeof window === "undefined") return;
    const panel = navigationRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(panel?.querySelectorAll<HTMLElement>("a[href],button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex='-1'])") ?? []);
    const frame = window.requestAnimationFrame(() => focusable()[0]?.focus());
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); setNavigationOpen(false); return; }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) { event.preventDefault(); return; }
      const first = items[0]; const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      window.requestAnimationFrame(() => navigationTriggerRef.current?.focus());
    };
  }, [navigationOpen]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const restoreView = () => {
      const path = String(window.location.pathname ?? "").replace(/\/+$/, "");
      const isProjects = new URLSearchParams(window.location.search).get("view") === "projects";
      const nextView = path === "/fly" ? "sandbox" : getInitialCoworkerViewFromLocation(path, window.location.search);
      if (isProjects) setProjectEntryRevision(value => value + 1);
      setProjectCreateMode(isProjects);
      setView(nextView);
    };
    window.addEventListener("popstate", restoreView);
    return () => window.removeEventListener("popstate", restoreView);
  }, []);

  return <main className={`cw-workspace rukh-cw-workspace${view === "conversations" ? " rukh-cw-chat" : " rukh-cw-sections"}`}>
    <header className="cw-header"><button ref={navigationTriggerRef} className="rukh-mobile-nav-trigger" type="button"
      aria-label="Open workspace navigation" aria-controls="rukh-cw-sidebar" aria-expanded={navigationOpen}
      onClick={() => setNavigationOpen(true)}><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3 5h14M3 10h14M3 15h9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg></button><div>{!(view === "projects" && projectCreateMode) && <span className="cw-eyebrow">{view === "sandbox" ? "RUKH AI / FLY" : "RUKH AI / COWORKER"}</span>}<h1>{view === "projects" && projectCreateMode ? "New project" : view === "conversations" ? "What are we working on?" : ({ projects: "Projects", library: "Files", settings: "Settings", actions: "Plugins", goals: "Goals", automations: "Automations", drafts: "Files & drafts", agent: "Agent activity", browser: "Browser", sandbox: "Fly", transactions: "Transactions", negotiations: "Negotiations" } as Record<string, string>)[view]}</h1>{!(view === "projects" && projectCreateMode) && <p>{view === "sandbox" ? "A dedicated coding environment with a multi-file explorer, source editor, isolated runtime output and Rukh Agent handoff. Repository write access and additional runtimes are not connected yet." : "A persistent workspace for conversations, focused work and connected tools."}</p>}{selected && !(view === "projects" && projectCreateMode) && <button className="cw-text-button cw-view-task" type="button" onClick={viewTask}>View current task <span aria-hidden="true">↓</span></button>}</div>
      <details className="rukh-section-context">
        <summary className="rukh-design-context" aria-label="Activity and context"><span>Activity &amp; context</span><NavigationIcon name="sliders" /></summary>
        <div className="rukh-section-context-panel" role="region" aria-label="Activity and context details">
          <div className="rukh-section-context-heading"><strong>Recent activity</strong><small>Your personal workspace</small></div>
          {recentConversations.slice(0, 5).map(item => <button type="button" key={item.id} onClick={() => openRecentConversation(item.id)}><span>{item.title}</span><small>{new Date(item.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</small></button>)}
          {recentConversations.length === 0 && <p>No recent activity yet. Conversations you create will appear here.</p>}
          <p className="rukh-section-context-note">Projects keep related conversations and files together in your private workspace.</p>
        </div>
      </details>
    </header>
    {error && <div className="cw-error cw-banner" role="alert">{error} {!workspace && <button className="cw-text-button" onClick={() => setReload(value => value + 1)}>Try again</button>}</div>}
    {notice && <p className="cw-notice cw-banner" role="status">{notice}</p>}
    <div className={"rukh-cw-shell" + (view === "conversations" ? " rukh-cw-shell-chat" : "")}>
      {view !== "conversations" && <>
        {navigationOpen && <button className="rukh-cw-navigation-backdrop" type="button" aria-label="Close workspace navigation" onClick={() => setNavigationOpen(false)} />}
        <aside ref={navigationRef} id="rukh-cw-sidebar" className={"rukh-cw-sidebar rukh-design-sidebar" + (navigationOpen ? " rukh-cw-sidebar-open is-open" : "")}
          aria-label="Coworker navigation" role={navigationOpen ? "dialog" : undefined} aria-modal={navigationOpen ? true : undefined}>
          <a href="/coworker" className="rukh-design-brand"><RukhCompanionMark /><strong>rukh<sup>AI</sup></strong></a>
          <button type="button" className="rukh-design-new" onClick={() => { onInitialDraftChange?.(""); setNewChatRevision(value => value + 1); navigateView("conversations"); }}>+ New chat</button>
          <WorkspaceNavigation active={view} settingsInFooter onNavigate={nextView => { if (nextView === "agent") setFocusAgentRunId(null); navigateView(nextView); }} />
          <section className="rukh-design-history" aria-label="Recent chats">
            <div className="rukh-design-history-heading"><span className="rukh-design-section-label">RECENT CHATS</span>
              <button type="button" className="rukh-design-history-search" aria-label="Search recent chats" aria-expanded={recentSearchOpen} onClick={() => { setRecentSearchOpen(value => !value); if (recentSearchOpen) setRecentSearch(""); }}><NavigationIcon name="search" /></button>
            </div>
            {recentSearchOpen && <input className="rukh-design-history-search-input" type="search" aria-label="Filter recent chats" placeholder="Search chats…" value={recentSearch} onChange={event => setRecentSearch(event.target.value)} />}
            <ul className="rukh-design-history-list">
              {recentChatItems.map(item => <li key={item.id}><button type="button" title={item.title} onClick={() => openRecentConversation(item.id)}>{item.title}</button></li>)}
            </ul>
            {recentChatItems.length === 0 && <p role="status">{recentSearch ? "No chats match your search." : "Your recent chats will appear here."}</p>}
          </section>
          <div className="rukh-design-account rukh-cw-account-footer">
            <div><span className="rukh-design-account-avatar">{accountLabel.trim().charAt(0).toUpperCase() || "A"}</span><span><strong title={accountLabel}>{accountLabel}</strong><small>Personal workspace</small></span></div>
            <button type="button" className={"rukh-design-settings-icon" + (view === "settings" ? " is-active" : "")} aria-label="Settings" title="Settings" aria-current={view === "settings" ? "page" : undefined} onClick={() => navigateView("settings")}><NavigationIcon name="settings" /></button>
            <button type="button" className="rukh-design-signout-icon" aria-label="Sign out" title="Sign out" disabled={Boolean(busy)} onClick={async () => { setBusy("signout"); try { await signOut(); } catch (error) { setError(message(error)); setBusy(""); } }}><NavigationIcon name="log-out" /></button>
          </div>
        </aside>
      </>}
      <section className="rukh-cw-content" aria-label={view === "projects" ? "Projects workspace" : view === "sandbox" ? "Fly workspace" : "Coworker workspace"}>
    {view === "library" && <FilesWorkspace client={client} />}
    {view === "settings" && <SettingsWorkspace client={client} email={email} />}
    {view === "projects" && <ProjectWorkspace key={projectEntryRevision} client={client} initialCreate onCreateModeChange={setProjectCreateMode} />}
    {view === "goals" && workspace && <GoalWorkspace client={client} openAgent={() => { setFocusAgentRunId(null); navigateView("agent"); }} openAutomations={() => navigateView("automations")} />}
    {view === "automations" && workspace && <AutomationWorkspace client={client} />}
    {view === "browser" && workspace && <BrowserWorkspace client={client} />}
    {view === "sandbox" && workspace && <FlyWorkspace client={client} accountId={workspace.account_id} />}
    {view === "transactions" && workspace && <TransactionWorkspace client={client} reviewAction={action => { setFocusActionId(action.id); setView("actions"); }} />}
    {view === "negotiations" && workspace && <NegotiationWorkspace client={client} reviewAction={action => { setFocusActionId(action.id); setView("actions"); }} />}
    {view === "actions" && workspace && <PluginsWorkspace client={client}>{onConnectionsChanged => <ActionWorkspace onConnectionsChanged={onConnectionsChanged} client={client} account={workspace.account_id} emailDraft={actionDraft} socialDraft={socialActionDraft} focusActionId={focusActionId} onFocused={() => setFocusActionId(null)} />}</PluginsWorkspace>}
    {view === "conversations" && <ConversationWorkspace key={newChatRevision} startEmpty={newChatRevision > 0} client={client} email={email} signOut={async () => { try { await signOut(); } catch (error) { setError(message(error)); } }} initialDraft={initialDraft} onInitialDraftChange={onInitialDraftChange} onNavigate={navigateView} openAgent={runId => { setFocusAgentRunId(runId); navigateView("agent"); }} />}
    {view === "agent" && workspace && <AgentWorkspace key={focusAgentRunId ?? "recent"} client={client} focusRunId={focusAgentRunId} documents={documents} openActions={() => setView("actions")} reviewAction={action => { setFocusActionId(action.id); setView("actions"); }} />}
    <div className="cw-layout" hidden={view !== "drafts"}><section className="cw-compose" aria-label="Create a coworker task">
      <div className="cw-card-title"><span className="cw-step-number">01</span><div><h2>Give your coworker a brief</h2><p>Bring the facts. Describe the outcome.</p></div></div>
      <form onSubmit={submit}>
        {(skills.length > 1 || !activeSkill) && <div className="cw-service-field"><label htmlFor="cw-work-service">Work service</label><select id="cw-work-service" aria-describedby="cw-service-description" value={skillId} disabled={Boolean(busy)} onChange={event => {
          const next = skills.find(skill => skill.id === event.target.value);
          if (!next) return;
          // Preserve a customized brief; replace only an untouched preset.
          if (instruction === activeSkill?.instruction || !instruction.trim()) setInstruction(next.instruction);
          setSkillId(next.id); submission.current = undefined;
        }}>{skills.map(skill => <option value={skill.id} key={skill.id}>{skill.name}</option>)}{!activeSkill && <option value={skillId} disabled>Service currently unavailable</option>}</select><span id="cw-service-description" className="cw-service-description">{activeSkill?.description ?? "Choose an available service to create a new task. Your saved draft remains available."}</span></div>}
        <label>What would you like to create?<textarea dir="auto" rows={3} value={instruction} minLength={3} maxLength={2000} required onChange={event => setInstruction(event.target.value)} /></label>
        {skillId === "research" && <fieldset className="cw-research-options"><legend>Web research</legend>
          <label>Public search query<input dir="auto" value={research.query} minLength={3} maxLength={400} required aria-describedby="cw-search-help" onChange={event => setResearch(previous => ({ ...previous, query: event.target.value }))} placeholder="For example, compare public transport options in Dhaka" /></label>
          <p className="cw-fineprint" id="cw-search-help">This query is sent to our search provider. Keep private details in your notes or files; those are not sent to web search.</p>
          <label>Source date range<select value={research.time_range} onChange={event => setResearch(previous => ({ ...previous, time_range: event.target.value as ResearchOptions["time_range"] }))}>
            <option value="any">Any time</option><option value="day">Past day</option><option value="week">Past week</option><option value="month">Past month</option><option value="year">Past year</option>
          </select></label><p className="cw-fineprint">Research uses up to five pages. A date range excludes pages without a usable publication or update date.</p>
        </fieldset>}
        <label>Your notes{skillId !== "report_email" && " (optional)"}<textarea ref={notesInput} dir="auto" rows={8} maxLength={20000} value={notes} required={skillId === "report_email" && !selectedDocs.length} onChange={event => setNotes(event.target.value)} placeholder="Paste notes, useful facts, or details you would like your coworker to use…" /><span className="cw-field-meta">{notes.length.toLocaleString()} / 20,000 characters</span></label>
        <label className="cw-upload">Add source files<input type="file" multiple accept={uploadFormats.map(format => "." + format).join(",")} disabled={Boolean(busy) || selectedDocs.length >= 5 || !workspace} onChange={async event => {
          const files = Array.from(event.currentTarget.files ?? []); event.currentTarget.value = "";
          if (files.length + selectedDocs.length > 5) { setError("Use up to five source files per task."); return; }
          setBusy("upload"); setError("");
          try {
            for (const file of files) {
              const doc = await client.upload(file);
              setDocuments(previous => [doc, ...previous.filter(item => item.id !== doc.id)]);
              setSelectedDocs(previous => [...previous, doc.id]);
            }
          } catch (error) { setError(message(error)); }
          finally { setBusy(""); }
        }} /><small>{busy === "upload" ? "Uploading your sources…" : `${uploadFormats.map(format => format === "pdf" ? "text-based PDF" : format.toUpperCase()).join(", ")} · Up to 8 MB each`}</small></label>
        {uploadFormats.includes("xlsx") && <p className="cw-fineprint">Spreadsheets: saved values, up to 4 sheets, 200 rows and 20 columns. Presentations: text, notes and saved chart data, up to 20 slides. Images and scans need pasted text.</p>}
        {selectedDocs.length > 0 && <ul className="cw-file-chips" aria-label="Selected sources">{selectedDocs.map(id => <li key={id}><span>{documents.find(doc => doc.id === id)?.filename ?? "Saved source"}</span><button type="button" aria-label={`Remove ${documents.find(doc => doc.id === id)?.filename ?? "saved source"} from this task`} disabled={Boolean(busy)} onClick={() => setSelectedDocs(previous => previous.filter(item => item !== id))}>×</button></li>)}</ul>}
        {documents.length > 0 && <details className="cw-saved-files"><summary>Use a previous upload</summary><div>{documents.map(doc => <div className="cw-saved-file" key={doc.id}><label><input type="checkbox" checked={selectedDocs.includes(doc.id)} disabled={Boolean(busy) || !selectedDocs.includes(doc.id) && selectedDocs.length >= 5} onChange={event => setSelectedDocs(previous => event.target.checked ? [...previous, doc.id] : previous.filter(id => id !== doc.id))} /><span>{doc.filename}</span></label><button type="button" className="cw-text-button" disabled={Boolean(busy)} aria-label={`Delete upload ${doc.filename}`} onClick={async () => {
          if (!window.confirm(`Delete the uploaded file “${doc.filename}”? Existing drafts will remain.`)) return;
          setBusy("delete"); setError("");
          try {
            const result = await client.deleteDocument(doc.id);
            setSelectedDocs(previous => previous.filter(id => id !== doc.id));
            setDocuments(previous => previous.filter(item => item.id !== doc.id)); setNotice(result.message);
          } catch (error) { setError(message(error)); }
          finally { setBusy(""); }
        }}>Delete</button></div>)}</div></details>}
        <label>Output language<select value={language} onChange={event => setLanguage(event.target.value)}>{languages.map(([code, name]) => <option key={code} value={code}>{name}</option>)}<option value="custom">Another language</option></select></label>
        {language === "custom" && <label>Language code<input value={customLanguage} onChange={event => setCustomLanguage(event.target.value)} placeholder="For example, en-GB or si" pattern="[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*" maxLength={35} required /></label>}
        {activeSkill && skills.length > 1 && <p className="cw-output-formats">{activeSkill.output}</p>}
        <button className="cw-primary" type="submit" disabled={Boolean(busy) || !workspace || !activeSkill || skillId === "report_email" && !notes.trim() && selectedDocs.length === 0}>{busy === "submit" ? "Starting your task…" : skillId === "report_email" ? "Create report & email draft" : "Create draft"}<span aria-hidden="true">↗</span></button>
        <p className="cw-fineprint">Once submitted, your task continues if you close this page. You review the results before using them.</p>
        {workspace && <p className="cw-usage">{workspace.usage.tasks_today} of {workspace.limits.daily_tasks} daily coworker tasks used</p>}
      </form>
    </section>
    <div className="cw-output-column" ref={outputColumn} tabIndex={-1}>
      {connection && <p className="cw-notice" role="status">{connection}</p>}
      {task ? <><TaskResult key={task.id} task={task} client={client} revise={revise} prepareEmail={draft => { setActionDraft(draft); setSocialActionDraft(null); setView("actions"); }} prepareSocial={text => { setSocialActionDraft(text); setActionDraft(null); setView("actions"); }} />{!terminal(task.state) && <button className="cw-text-button cw-cancel" type="button" disabled={busy === "cancel" || task.state === "cancelling"} onClick={async () => {
        setBusy("cancel"); setError("");
        try { setTask(await client.cancel(task.id)); } catch (error) { setError(message(error)); }
        finally { setBusy(""); }
      }}>{task.state === "cancelling" ? "Stopping…" : "Cancel this task"}</button>}</> : selected ? <p className="cw-loading" role="status">Loading your task…</p> : <section className="cw-empty"><span className="cw-empty-mark" aria-hidden="true">✦</span><span className="cw-eyebrow">From scattered notes to finished drafts</span><h2>Make space for the work<br />that matters.</h2><p>Choose the work you need, add your details, and leave with a draft you can review and use.</p><div className="cw-format-tags"><span>DOCX</span><span>PDF</span><span>TEXT</span></div></section>}
      {history.length > 0 && <section className="cw-history"><div className="cw-history-title"><h2>Recent work</h2><button className="cw-text-button" type="button" onClick={() => setReload(value => value + 1)}>Refresh</button></div><ul>{history.map(item => <li key={item.id}><button type="button" aria-pressed={selected === item.id} onClick={() => setSelected(item.id)}><div><strong>{item.instruction}</strong><small>{skills.find(skill => skill.id === (item.skill_id ?? "report_email"))?.name ?? "Saved work"} · {new Date(item.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })} · {item.output_language}</small></div><span className={`cw-status cw-status-${item.state}`}>{labels[item.state]}</span></button></li>)}</ul></section>}
    </div>
    </div>
      </section>
    </div>
  </main>;
}
