import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoworkerClient, type ProjectRecord, type ProjectDetail, type ConversationRecord, type SourceDocument } from "./client";
import NavigationIcon from "./WorkspaceNavigationIcon";
const message = (error: unknown) => error instanceof Error ? error.message : "The project could not be updated.";

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
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [resource, setResource] = useState("");
  const [revision, setRevision] = useState(0);
  const attempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const sequence = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    client.projects(controller.signal).then(value => { if (!controller.signal.aborted) setProjects(value.items); })
      .catch(error => { if (!controller.signal.aborted) setError(message(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [client, revision]);

  async function open(id: string) {
    const current = ++sequence.current;
    setBusy(true); setError(""); setNotice("");
    try {
      const [detail, conversations, documents] = await Promise.all([client.project(id), client.conversations(), client.documents()]);
      if (current !== sequence.current) return;
      setProject(detail); setChats(conversations.items); setFiles(documents.documents); setResource("");
    } catch (error) { if (current === sequence.current) setError(message(error)); }
    finally { if (current === sequence.current) setBusy(false); }
  }

  function edit(current: ProjectDetail | null) {
    setEditing(true); setName(current?.name ?? ""); setDescription(current?.description ?? ""); setError(""); setNotice("");
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy || !name.trim()) return;
    setBusy(true); setError("");
    try {
      if (project) {
        const saved = await client.editProject(project.id, name.trim(), description.trim(), project.revision);
        setProject(current => current ? { ...current, ...saved } : null);
      } else {
        const fingerprint = JSON.stringify({ name: name.trim(), description: description.trim() });
        if (attempt.current?.fingerprint !== fingerprint) attempt.current = { fingerprint, key: crypto.randomUUID() };
        const created = await client.createProject(name.trim(), description.trim(), attempt.current.key);
        setProject({ ...created, resources: [] });
        try { const [conversations, documents] = await Promise.all([client.conversations(), client.documents()]); setChats(conversations.items); setFiles(documents.documents); }
        catch (error) { setError("Project saved, but existing work could not be loaded. " + message(error)); }
        attempt.current = null;
      }
      setEditing(false); setRevision(value => value + 1); setNotice("Project saved.");
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }
  async function link() {
    if (!project || !resource || busy) return;
    const [type, id] = resource.split(":");
    setBusy(true); setError("");
    try { setProject(await client.linkProjectResource(project.id, type as "conversation" | "document", id, project.revision)); setResource(""); }
    catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }
  async function unlink(type: "conversation" | "document", id: string) {
    if (!project || busy) return;
    setBusy(true); setError("");
    try { setProject(await client.unlinkProjectResource(project.id, type, id, project.revision)); }
    catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }
  return <section className="rukh-designed-page" aria-label="Projects">
    <header className="rukh-page-heading"><div><h1>{project ? project.name : "Give every idea a place to grow."}</h1><p>{project ? project.description || "Keep conversations and files together." : "Keep your conversations, files, and work together."}</p></div>
      {!editing && (project ? <button className="cw-secondary" disabled={busy} onClick={() => edit(project)}>Edit project</button> : <button className="cw-primary" disabled={loading || Boolean(error)} onClick={() => edit(null)}>+ New project</button>)}
    </header>
    {error && <div className="cw-error" role="alert">{error}<button className="cw-text-button" onClick={() => { if (project) void open(project.id); else setRevision(value => value + 1); }}>Refresh</button></div>}
    {notice && <p className="cw-notice" role="status">{notice}</p>}
    {loading && <p role="status">Loading projects…</p>}
    {editing ? <form className="rukh-project-form" onSubmit={save}>
      <h2>{project ? "Edit project" : "Create a new project"}</h2>
      <label>Project name<input autoFocus aria-label="Project name" maxLength={100} required value={name} onChange={event => setName(event.target.value)} disabled={busy} /></label>
      <label>Description<textarea aria-label="Project description" maxLength={2000} rows={4} value={description} onChange={event => setDescription(event.target.value)} disabled={busy} /></label>
      <p>Only you can access this project. Adding files does not authorize an Agent to read or act on them.</p>
      <div className="rukh-page-actions"><button className="cw-secondary" type="button" disabled={busy} onClick={() => setEditing(false)}>Cancel</button><button className="cw-primary" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save project"}</button></div>
    </form> : project ? <>
      <div className="rukh-page-actions"><button className="cw-text-button" onClick={() => { ++sequence.current; setProject(null); setError(""); setNotice(""); }}>← All projects</button><a className="cw-primary" href={`/coworker?project=${encodeURIComponent(project.id)}`}>+ New project chat</a></div>
      <section className="rukh-project-resources"><h2>Conversations &amp; files</h2>
        {project.resources.length === 0 && <p className="rukh-muted">Start a project chat or link an existing conversation or file.</p>}
        <ul>{project.resources.map(item => <li key={item.resource_type + item.resource_id}><NavigationIcon name={item.resource_type === "conversation" ? "chat" : "file-text"} />
          {item.resource_type === "conversation" ? <a href={`/coworker?conversation=${encodeURIComponent(item.resource_id)}&project=${encodeURIComponent(project.id)}`}>{item.title}</a> : <span>{item.title}</span>}
          <button type="button" className="cw-text-button" disabled={busy} aria-label={`Remove ${item.title} from project`} onClick={() => { void unlink(item.resource_type, item.resource_id); }}>Remove</button></li>)}</ul>
        <label>Link existing work<select value={resource} aria-label="Link existing work" disabled={busy} onChange={event => setResource(event.target.value)}><option value="">Choose a conversation or file</option>
          {chats.filter(item => !project.resources.some(link => link.resource_id === item.id)).map(item => <option key={item.id} value={`conversation:${item.id}`}>{item.title}</option>)}
          {files.filter(item => !project.resources.some(link => link.resource_id === item.id)).map(item => <option key={item.id} value={`document:${item.id}`}>{item.filename}</option>)}
        </select></label><button className="cw-secondary" disabled={busy || !resource} onClick={() => { void link(); }}>Add to project</button>
      </section>
    </> : !loading && !error && <>
      <label className="rukh-page-search"><NavigationIcon name="search" /><input type="search" aria-label="Search projects" placeholder="Search projects" value={search} onChange={event => setSearch(event.target.value)} /></label>
      <div className="rukh-project-grid">{projects.filter(item => item.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map(item => <button type="button" className="rukh-project-card" key={item.id} disabled={busy} onClick={() => { void open(item.id); }}><span className="rukh-welcome-icon"><NavigationIcon name="folder" /></span><strong>{item.name}</strong><p>{item.description || "Conversations and files for your work."}</p><small>Updated {new Date(item.updated_at).toLocaleDateString()}</small></button>)}</div>
      {projects.length === 0 && <p className="rukh-page-empty">Your projects will appear here. Create your first project to get started.</p>}
    </>}
  </section>;
}
