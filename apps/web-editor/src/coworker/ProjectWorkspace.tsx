import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  CoworkerClient,
  type ProjectRecord,
  type ProjectDetail,
  type ProjectResource,
  type ConversationRecord,
  type SourceDocument,
} from "./client";
import NavigationIcon from "./WorkspaceNavigationIcon";
import "./project-workspace.css";

const message = (error: unknown) => error instanceof Error ? error.message : "The project could not be updated.";

function updatedLabel(value: string) {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "Recently updated";
  const date = new Date(timestamp);
  const today = new Date();
  const dayNumber = (day: Date) => Date.UTC(day.getFullYear(), day.getMonth(), day.getDate());
  const age = Math.floor((dayNumber(today) - dayNumber(date)) / 86400000);
  if (age === 0) return "today";
  if (age === 1) return "yesterday";
  if (age > 1 && age < 7) return new Intl.DateTimeFormat(undefined, { weekday: "long" }).format(date);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

type ProjectTab = "overview" | "chats" | "files";

export default function ProjectWorkspace({ client }: { client: CoworkerClient }) {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [chats, setChats] = useState<ConversationRecord[]>([]);
  const [files, setFiles] = useState<SourceDocument[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [resource, setResource] = useState("");
  const [activeTab, setActiveTab] = useState<ProjectTab>("overview");
  const [revision, setRevision] = useState(0);
  const attempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const sequence = useRef(0);
  const uploadRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    client.projects(controller.signal)
      .then(value => { if (!controller.signal.aborted) setProjects(value.items); })
      .catch(cause => { if (!controller.signal.aborted) setError(message(cause)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [client, revision]);

  async function open(id: string) {
    const current = ++sequence.current;
    setBusy(true);
    setError("");
    setNotice("");
    setActiveTab("overview");
    try {
      const [detail, conversations, documents] = await Promise.all([
        client.project(id),
        client.conversations(),
        client.documents(),
      ]);
      if (current !== sequence.current) return;
      setProject(detail);
      setChats(conversations.items);
      setFiles(documents.documents);
      setResource("");
    } catch (cause) {
      if (current === sequence.current) setError(message(cause));
    } finally {
      if (current === sequence.current) setBusy(false);
    }
  }

  function backToProjects() {
    ++sequence.current;
    setProject(null);
    setError("");
    setNotice("");
    setResource("");
    setActiveTab("overview");
  }

  function edit(current: ProjectDetail | null) {
    setEditing(true);
    setName(current?.name ?? "");
    setDescription(current?.description ?? "");
    setError("");
    setNotice("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy || !name.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (project) {
        const saved = await client.editProject(project.id, name.trim(), description.trim(), project.revision);
        setProject(current => current ? { ...current, ...saved } : null);
      } else {
        const fingerprint = JSON.stringify({ name: name.trim(), description: description.trim() });
        if (attempt.current?.fingerprint !== fingerprint) {
          attempt.current = { fingerprint, key: crypto.randomUUID() };
        }
        const created = await client.createProject(name.trim(), description.trim(), attempt.current.key);
        setProject({ ...created, resources: [] });
        setActiveTab("overview");
        try {
          const [conversations, documents] = await Promise.all([client.conversations(), client.documents()]);
          setChats(conversations.items);
          setFiles(documents.documents);
        } catch (cause) {
          setError("Project saved, but existing work could not be loaded. " + message(cause));
        }
        attempt.current = null;
      }
      setEditing(false);
      setRevision(value => value + 1);
      setNotice("Project saved.");
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function removeProject() {
    if (!project || busy) return;
    const current = project;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await client.deleteProject(current.id, current.revision);
      ++sequence.current;
      setProject(null);
      setProjects(items => items.filter(item => item.id !== current.id));
      setConfirmDelete(false);
      setResource("");
      setActiveTab("overview");
      setNotice(result.message || "Project deleted.");
      setRevision(value => value + 1);
    } catch (cause) {
      setConfirmDelete(false);
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function link() {
    if (!project || !resource || busy) return;
    const [type, id] = resource.split(":");
    if (type !== "conversation" && type !== "document") return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await client.linkProjectResource(project.id, type, id, project.revision);
      setProject(saved);
      setResource("");
      setNotice("Added to project.");
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function unlink(type: "conversation" | "document", id: string) {
    if (!project || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setProject(await client.unlinkProjectResource(project.id, type, id, project.revision));
      setNotice("Removed from project.");
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file || !project || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    let uploaded: SourceDocument | null = null;
    try {
      uploaded = await client.upload(file);
      const latest = await client.project(project.id);
      const saved = await client.linkProjectResource(latest.id, "document", uploaded.id, latest.revision);
      setProject(saved);
      setNotice("Uploaded " + uploaded.filename + " and added it to this project.");
      try {
        const documents = await client.documents();
        setFiles(documents.documents);
      } catch (cause) {
        setError("The file was added to this project, but the file list could not refresh. " + message(cause));
      }
    } catch (cause) {
      if (uploaded) {
        try {
          const [latest, documents] = await Promise.all([client.project(project.id), client.documents()]);
          setProject(latest);
          setFiles(documents.documents);
        } catch {
          // The uploaded source remains in the private workspace even if refresh fails.
        }
        setError(uploaded.filename + " was uploaded, but could not be linked to this project. " + message(cause));
      } else {
        setError(message(cause));
      }
    } finally {
      input.value = "";
      setBusy(false);
    }
  }

  const projectChats = project?.resources.filter(item => item.resource_type === "conversation") ?? [];
  const projectFiles = project?.resources.filter(item => item.resource_type === "document") ?? [];
  const recentChats = projectChats
    .map(item => ({ ...item, updated_at: chats.find(chat => chat.id === item.resource_id)?.updated_at ?? project?.updated_at ?? "" }))
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
  const availableChats = chats.filter(item => !project?.resources.some(link => link.resource_type === "conversation" && link.resource_id === item.id));
  const availableFiles = files.filter(item => !project?.resources.some(link => link.resource_type === "document" && link.resource_id === item.id));
  const filteredProjects = projects.filter(item => {
    const query = search.trim().toLocaleLowerCase();
    return !query || item.name.toLocaleLowerCase().includes(query) || item.description.toLocaleLowerCase().includes(query);
  });

  function conversationRow(item: ProjectResource) {
    return <li key={item.resource_id}>
      <span className="rukh-project-resource-icon"><NavigationIcon name="chat" /></span>
      <div className="rukh-project-resource-copy">
        <a href={"/coworker?conversation=" + encodeURIComponent(item.resource_id) + "&project=" + encodeURIComponent(project!.id)}>{item.title}</a>
        <small>Conversation</small>
      </div>
      <button type="button" className="cw-text-button" disabled={busy} aria-label={"Remove " + item.title + " from project"} onClick={() => { void unlink("conversation", item.resource_id); }}>Remove</button>
    </li>;
  }

  function fileRow(item: ProjectResource) {
    const source = files.find(file => file.id === item.resource_id);
    return <li key={item.resource_id}>
      <span className="rukh-project-resource-icon"><NavigationIcon name="file-text" /></span>
      <div className="rukh-project-resource-copy">
        <strong>{item.title}</strong>
        <small>{source ? Math.ceil(source.byte_size / 1024) + " KB · " + source.state : "Project file"}</small>
      </div>
      <button type="button" className="cw-text-button" disabled={busy} aria-label={"Remove " + item.title + " from project"} onClick={() => { void unlink("document", item.resource_id); }}>Remove</button>
    </li>;
  }

  const linkExistingWork = project ? <section className="rukh-project-panel rukh-project-link-panel" aria-label="Add existing work">
    <div className="rukh-project-panel-heading">
      <div><h2>Bring existing work into this project</h2><p>Link conversations and files already saved in your workspace.</p></div>
    </div>
    <div className="rukh-project-link-controls">
      <label htmlFor="rukh-project-link-select">Link existing work</label>
      <select id="rukh-project-link-select" value={resource} disabled={busy} onChange={event => setResource(event.target.value)}>
        <option value="">Choose a conversation or file</option>
        {availableChats.length > 0 && <optgroup label="Conversations">
          {availableChats.map(item => <option key={item.id} value={"conversation:" + item.id}>{item.title}</option>)}
        </optgroup>}
        {availableFiles.length > 0 && <optgroup label="Files">
          {availableFiles.map(item => <option key={item.id} value={"document:" + item.id}>{item.filename}</option>)}
        </optgroup>}
      </select>
      <button type="button" className="cw-secondary" disabled={busy || !resource} onClick={() => { void link(); }}>Add to project</button>
    </div>
  </section> : null;

  return <section className="rukh-designed-page rukh-projects-page" aria-label="Projects">
    {!project ? <>
      <header className="rukh-page-heading rukh-projects-heading">
        <div>
          <span className="rukh-project-eyebrow">YOUR WORKSPACE</span>
          <h1>Projects</h1>
          <p>Give every idea a place to grow.</p>
        </div>
        <button className="cw-primary" disabled={loading || Boolean(error)} onClick={() => edit(null)}>+ New project</button>
      </header>
      {error && <div className="cw-error" role="alert">{error}<button className="cw-text-button" onClick={() => setRevision(value => value + 1)}>Refresh</button></div>}
      {notice && <p className="cw-notice" role="status">{notice}</p>}
      <div className="rukh-projects-toolbar">
        <label className="rukh-project-search">
          <NavigationIcon name="search" />
          <input type="search" aria-label="Search projects" placeholder="Search projects…" value={search} onChange={event => setSearch(event.target.value)} />
        </label>
      </div>
      {loading ? <p className="rukh-project-loading" role="status">Loading projects…</p> : filteredProjects.length > 0 ? <div className="rukh-project-grid">
        {filteredProjects.map(item => <button type="button" className="rukh-project-card" key={item.id} disabled={busy} onClick={() => { void open(item.id); }}>
          <span className="rukh-project-card-icon"><NavigationIcon name="folder" /></span>
          <span className="rukh-project-card-title">{item.name}</span>
          <span className="rukh-project-card-meta">{typeof item.conversation_count === "number" ? `${item.conversation_count} ${item.conversation_count === 1 ? "chat" : "chats"} · ` : ""}Updated {updatedLabel(item.updated_at)}</span>
        </button>)}
      </div> : projects.length === 0 ? <div className="rukh-project-empty-home">
        <span className="rukh-project-empty-icon"><NavigationIcon name="folder" /></span>
        <h2>Your projects start here</h2>
        <p>Create a project to keep its conversations and source files in one organized space.</p>
        <button className="cw-primary" disabled={loading} onClick={() => edit(null)}>Create your first project</button>
      </div> : <p className="rukh-project-no-results">No projects match “{search}”. Try another search.</p>}
    </> : <>
      <div className="rukh-project-detail-topbar">
        <button type="button" className="rukh-project-back" onClick={backToProjects}><NavigationIcon name="arrow-left" />All projects</button>
        <div className="rukh-project-detail-actions">
          <button type="button" className="cw-secondary" disabled={busy} onClick={() => edit(project)}>Edit project</button>
          <a className="cw-primary" href={"/coworker?project=" + encodeURIComponent(project.id)}>+ New project chat</a>
          <button type="button" className="rukh-project-danger" disabled={busy} aria-label={"Delete project " + project.name} onClick={() => setConfirmDelete(true)}>Delete project</button>
        </div>
      </div>
      <header className="rukh-project-hero">
        <span className="rukh-project-hero-icon"><NavigationIcon name="folder" /></span>
        <div className="rukh-project-hero-copy">
          <span className="rukh-project-eyebrow">PROJECT WORKSPACE</span>
          <h1>{project.name}</h1>
          <p>{project.description || "Keep the conversations and files for this work together."}</p>
        </div>
        <div className="rukh-project-stats" aria-label="Project contents">
          <span><strong>{projectChats.length}</strong><small>Chats</small></span>
          <span><strong>{projectFiles.length}</strong><small>Files</small></span>
          <span><strong>{updatedLabel(project.updated_at)}</strong><small>Updated</small></span>
        </div>
      </header>
      <nav className="rukh-project-tabs" role="tablist" aria-label="Project sections">
        {(["overview", "chats", "files"] as const).map(tab => <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? "is-active" : ""} onClick={() => setActiveTab(tab)}>
          {tab === "overview" ? "Overview" : tab === "chats" ? "Chats" : "Files"}
          {tab === "chats" && <span>{projectChats.length}</span>}
          {tab === "files" && <span>{projectFiles.length}</span>}
        </button>)}
      </nav>
      {error && <div className="cw-error" role="alert">{error}<button className="cw-text-button" onClick={() => { void open(project.id); }}>Refresh</button></div>}
      {notice && <p className="cw-notice" role="status">{notice}</p>}
      {activeTab === "overview" && <div className="rukh-project-overview">
        <div className="rukh-project-overview-grid">
          <section className="rukh-project-panel">
            <div className="rukh-project-panel-heading">
              <div><h2>Recent chats</h2><p>Conversations connected to this project.</p></div>
              <button type="button" className="cw-text-button" onClick={() => setActiveTab("chats")}>View all</button>
            </div>
            {recentChats.length > 0 ? <ul className="rukh-project-resource-list">{recentChats.slice(0, 4).map(conversationRow)}</ul> : <div className="rukh-project-empty-inline">
              <span><NavigationIcon name="chat" /></span><strong>No chats yet</strong><p>Start a conversation and keep it with this project.</p>
              <a href={"/coworker?project=" + encodeURIComponent(project.id)}>+ New project chat</a>
            </div>}
          </section>
          <section className="rukh-project-panel">
            <div className="rukh-project-panel-heading">
              <div><h2>Project files</h2><p>Reference material saved with this project.</p></div>
              <button type="button" className="cw-text-button" onClick={() => setActiveTab("files")}>View all</button>
            </div>
            {projectFiles.length > 0 ? <ul className="rukh-project-resource-list">{projectFiles.slice(0, 4).map(fileRow)}</ul> : <div className="rukh-project-empty-inline">
              <span><NavigationIcon name="file-text" /></span><strong>No files added</strong><p>Upload a source or link a file from your workspace.</p>
              <button type="button" onClick={() => setActiveTab("files")} disabled={busy}>Browse files</button>
            </div>}
          </section>
        </div>
        {linkExistingWork}
      </div>}
      {activeTab === "chats" && <div className="rukh-project-tab-content">
        <section className="rukh-project-panel">
          <div className="rukh-project-panel-heading">
            <div><h2>Project chats</h2><p>Start a new conversation or reopen work already connected to this project.</p></div>
            <a className="cw-primary" href={"/coworker?project=" + encodeURIComponent(project.id)}>+ New project chat</a>
          </div>
          {recentChats.length > 0 ? <ul className="rukh-project-resource-list">{recentChats.map(conversationRow)}</ul> : <div className="rukh-project-empty-inline">
            <span><NavigationIcon name="chat" /></span><strong>No conversations in this project</strong><p>Your new project chats will appear here.</p>
            <a href={"/coworker?project=" + encodeURIComponent(project.id)}>Start a project chat</a>
          </div>}
        </section>
        {linkExistingWork}
      </div>}
      {activeTab === "files" && <div className="rukh-project-tab-content">
        <section className="rukh-project-panel">
          <div className="rukh-project-panel-heading">
            <div><h2>Project files</h2><p>Keep source documents close to the conversations they support.</p></div>
            <button type="button" className="cw-primary" disabled={busy} onClick={() => uploadRef.current?.click()}>{busy ? "Uploading…" : "+ Upload file"}</button>
          </div>
          <input ref={uploadRef} className="rukh-project-sr-only" type="file" aria-label="Upload project file" accept=".txt,.docx,.pdf" onChange={event => { void uploadFile(event); }} disabled={busy} />
          {projectFiles.length > 0 ? <ul className="rukh-project-resource-list">{projectFiles.map(fileRow)}</ul> : <div className="rukh-project-empty-inline">
            <span><NavigationIcon name="file-text" /></span><strong>No files added yet</strong><p>Upload a TXT, DOCX or PDF source, or link an existing workspace file.</p>
            <button type="button" onClick={() => uploadRef.current?.click()} disabled={busy}>+ Upload a file</button>
          </div>}
        </section>
        {linkExistingWork}
      </div>}
    </>}
    {confirmDelete && project && <div className="rukh-project-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) setConfirmDelete(false); }}>
      <section className="rukh-project-dialog rukh-project-delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="rukh-project-delete-title" aria-describedby="rukh-project-delete-description" onKeyDown={event => { if (event.key === "Escape" && !busy) setConfirmDelete(false); }}>
        <div className="rukh-project-form">
          <span className="rukh-project-eyebrow">DELETE PROJECT</span>
          <h2 id="rukh-project-delete-title">Delete “{project.name}”?</h2>
          <p id="rukh-project-delete-description">This removes the project and its links. Your conversations and files will remain in your workspace.</p>
          <div className="rukh-project-dialog-actions">
            <button className="cw-secondary" type="button" autoFocus disabled={busy} onClick={() => setConfirmDelete(false)}>Cancel</button>
            <button className="rukh-project-danger" type="button" disabled={busy} aria-label="Confirm delete project" onClick={() => { void removeProject(); }}>{busy ? "Deleting…" : "Delete project"}</button>
          </div>
        </div>
      </section>
    </div>}
    {editing && <div className="rukh-project-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) setEditing(false); }}>
      <section className="rukh-project-dialog" role="dialog" aria-modal="true" aria-labelledby="rukh-project-dialog-title" onKeyDown={event => { if (event.key === "Escape" && !busy) setEditing(false); }}>
        <form className="rukh-project-form" onSubmit={save}>
          <span className="rukh-project-eyebrow">{project ? "PROJECT SETTINGS" : "NEW PROJECT"}</span>
          <h2 id="rukh-project-dialog-title">{project ? "Edit project" : "Create a new project"}</h2>
          <p className="rukh-project-dialog-description">Give this workspace a clear name and a short description so it is easy to find later.</p>
          <label>Project name<input autoFocus aria-label="Project name" maxLength={100} required value={name} onChange={event => setName(event.target.value)} disabled={busy} placeholder="e.g. Website redesign" /></label>
          <label>Description<textarea aria-label="Project description" maxLength={2000} rows={4} value={description} onChange={event => setDescription(event.target.value)} disabled={busy} placeholder="What are you working on?" /></label>
          <p className="rukh-project-privacy-note">Only you can access this project. Linking a file or conversation does not authorize an Agent to read or act on it.</p>
          <div className="rukh-project-dialog-actions">
            <button className="cw-secondary" type="button" disabled={busy} onClick={() => setEditing(false)}>Cancel</button>
            <button className="cw-primary" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save project"}</button>
          </div>
        </form>
      </section>
    </div>}
  </section>;
}
