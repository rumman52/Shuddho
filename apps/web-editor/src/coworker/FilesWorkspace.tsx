import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { CoworkerClient, type SourceDocument } from "./client";
import NavigationIcon from "./WorkspaceNavigationIcon";

export default function FilesWorkspace({ client }: { client: CoworkerClient }) {
  const [files, setFiles] = useState<SourceDocument[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const uploadRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError("");
    client.documents(controller.signal).then(value => { if (!controller.signal.aborted) setFiles(value.documents); })
      .catch(error => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Files could not be loaded."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [client, revision]);
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget; const file = input.files?.[0]; if (!file || busy) return;
    setBusy(true); setError(""); setNotice("");
    try { const saved = await client.upload(file); setNotice(`Uploaded ${saved.filename}.`); setRevision(value => value + 1); }
    catch (error) { setError(error instanceof Error ? error.message : "Upload failed."); }
    finally { input.value = ""; setBusy(false); }
  }
  async function remove(file: SourceDocument) {
    if (busy || !window.confirm(`Delete ${file.filename}? This removes this source file from your workspace.`)) return;
    setBusy(true); setError("");
    try { const result = await client.deleteDocument(file.id); setNotice(result.message); setRevision(value => value + 1); }
    catch (error) { setError(error instanceof Error ? error.message : "File could not be deleted."); }
    finally { setBusy(false); }
  }
  return <section className="rukh-designed-page" aria-label="Files">
    <header className="rukh-page-heading"><div><h1>Your work, all together.</h1><p>Files you upload stay in your private workspace.</p></div><button className="cw-primary" disabled={busy} onClick={() => uploadRef.current?.click()}>{busy ? "Uploading…" : "+ Upload file"}</button></header>
    <input ref={uploadRef} className="rukh-sr-only" type="file" aria-label="Upload workspace file" accept=".txt,.docx,.pdf,.csv,.xlsx,.pptx" onChange={event => { void upload(event); }} disabled={busy} />
    {error && <p className="cw-error" role="alert">{error}<button className="cw-text-button" onClick={() => setRevision(value => value + 1)}>Retry</button></p>}
    {notice && <p className="cw-notice" role="status">{notice}</p>}
    <label className="rukh-page-search"><NavigationIcon name="search" /><input type="search" placeholder="Search files" aria-label="Search files" value={search} onChange={event => setSearch(event.target.value)} /></label>
    {loading ? <p role="status">Loading files…</p> : files.length === 0 ? <p className="rukh-page-empty">Upload a file to keep your source material close to your work.</p> : <ul className="rukh-file-list">{files.filter(item => item.filename.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map(item => <li key={item.id}><NavigationIcon name="file-text" /><div><strong>{item.filename}</strong><small>{Math.ceil(item.byte_size / 1024)} KB · {item.state}</small></div><button className="cw-text-button" disabled={busy} onClick={() => { void remove(item); }}>Delete</button></li>)}</ul>}
    <p className="rukh-panel-footnote">Choose files explicitly in a conversation. Uploading does not start Agent work.</p>
  </section>;
}
