import { useEffect, useMemo, useRef, useState } from "react";
import { CoworkerClient } from "../../web-editor/src/coworker/client";
import bengaliFont from "@fontsource/noto-sans-bengali/files/noto-sans-bengali-bengali-400-normal.woff2?inline";
import { persistEditorCopy, sha256Hex } from "./persistence.mjs";

const starter = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,sans-serif;color:#20291F;background:#fff}header,footer{padding:24px 30px}header{display:flex;justify-content:space-between;border-bottom:1px solid #DFE3DA}header strong{font-size:24px}main{padding:32px}h1{font-size:34px;line-height:1.4;max-width:520px;margin:0}p{color:#687064;line-height:1.7}button{padding:14px 20px;border:0;border-radius:10px;background:#245A43;color:white;font:inherit}section[data-layer=hero]{display:flex;flex-direction:column;gap:24px;padding:32px}section[data-layer=features]{margin-top:48px;padding:24px;background:#F4F6F1;border-radius:14px}footer{font-size:12px;color:#687064}</style></head>
<body><header data-layer="header"><strong>rukh</strong><span>Get started ↗</span></header><main>
<section data-layer="hero"><h1>Make room for<br>your best work.</h1><p>An AI coworker for ideas, projects, and everything in between.</p><button>Meet your coworker</button></section>
<section data-layer="features"><strong>Think. Create. Follow through.</strong><p>Start with a conversation.</p></section>
</main><footer data-layer="footer">Your ideas, brought to life.</footer></body></html>`;

function previewSource(source: string): string {
  const document = new DOMParser().parseFromString(source, "text/html");
  document.querySelectorAll("script, iframe, object, embed, base, link, template, meta[http-equiv], animate, set, animateMotion, animateTransform").forEach(node => node.remove());
  document.querySelectorAll("*").forEach(node => {
    for (const attribute of Array.from(node.attributes)) {
      if (["href", "action", "formaction", "target", "ping"].includes(attribute.localName.toLowerCase()) || attribute.name.toLowerCase().startsWith("on")) {
        node.removeAttributeNS(attribute.namespaceURI, attribute.localName);
      }
    }
  });
  const policy = document.createElement("meta");
  policy.httpEquiv = "Content-Security-Policy";
  policy.content = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'";
  const font = document.createElement("style");
  font.textContent = `@font-face{font-family:RukhBengali;src:url("${bengaliFont}") format("woff2");font-weight:400}body{font-family:Inter,system-ui,RukhBengali,sans-serif}`;
  document.head.append(font);
  document.head.prepend(policy);
  return "<!doctype html>" + document.documentElement.outerHTML;
}

type SavedVersion = { source: string; at: string; documentId: string };
export default function WebsiteEditor({ client, userId, conversationId, projectId }: { client: CoworkerClient | null; userId: string | null; conversationId: string | null; projectId: string | null }) {
  const [source, setSource] = useState(starter);
  const [view, setView] = useState<"design" | "code" | "history">("design");
  const [layer, setLayer] = useState("hero");
  const [padding, setPadding] = useState(32);
  const [background, setBackground] = useState("#FFFFFF");
  const [layoutGap, setLayoutGap] = useState(24);
  const [fontSize, setFontSize] = useState(34);
  const [fontFamily, setFontFamily] = useState("Inter");
  const [versions, setVersions] = useState<SavedVersion[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [savedSource, setSavedSource] = useState("");
  const [metadataRevision, setMetadataRevision] = useState(0);
  const [restoredUser, setRestoredUser] = useState<string | null>(null);
  const metadataGeneration = useRef(0);
  const savedMetadata = useRef<{ savedSource: string; versions: SavedVersion[] }>({ savedSource: "", versions: [] });
  const previousUser = useRef<string | null>(null);
  const activeUser = useRef(userId); activeUser.current = userId;
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const saveAttempt = useRef<{ fingerprint: string; uploaded?: { id: string; filename: string; state: string; byte_size: number } } | null>(null);
  const handoff = useRef<{ fingerprint: string; conversationKey: string; messageKey: string; conversationId?: string } | null>(null);
  const preview = useMemo(() => typeof DOMParser === "undefined" ? "" : previewSource(source), [source]);

  useEffect(() => {
    let alive = true;
    const generation = metadataGeneration.current;
    const previous = previousUser.current;
    if (previous !== userId) savedMetadata.current = { savedSource: "", versions: [] };
    if (previous && previous !== userId) {
      try { sessionStorage.removeItem(`rukh-website-draft:v1:${previous}`); } catch { /* optional storage */ }
      setSource(starter); setVersions([]); setSavedSource(""); setError(""); setBusy(false);
      saveAttempt.current = null; handoff.current = null;
    }
    previousUser.current = userId;
    if (!userId) { setRestoredUser(null); return; }
    try {
      const record = JSON.parse(sessionStorage.getItem(`rukh-website-draft:v1:${userId}`) ?? "null");
      if (record && typeof record.source === "string") {
        setSource(record.source); setSavedSource(""); setVersions([]);
        const savedVersions: SavedVersion[] = Array.isArray(record.versions) ? record.versions.filter((item: SavedVersion) => typeof item.source === "string" && typeof item.at === "string" && typeof item.documentId === "string").slice(0, 10) : [];
        savedMetadata.current = { savedSource: typeof record.savedSource === "string" ? record.savedSource : "", versions: savedVersions };
        if (client) void client.workspaceManifest().then(async manifest => {
          if (!alive || activeUser.current !== userId || metadataGeneration.current !== generation) return;
          const available = new Map(manifest.documents.filter(item => item.available).map(item => [item.document_id, item.sha256]));
          const matches = await Promise.all(savedVersions.map(async item => available.get(item.documentId) === await sha256Hex(item.source)));
          if (!alive || activeUser.current !== userId || metadataGeneration.current !== generation) return;
          const verified = savedVersions.filter((_, index) => matches[index]);
          const verifiedSource = verified.some(item => item.source === record.savedSource) ? record.savedSource : "";
          savedMetadata.current = { savedSource: verifiedSource, versions: verified };
          setVersions(verified); setSavedSource(verifiedSource); setMetadataRevision(value => value + 1);
        }).catch(() => { /* Retain the draft, never claim an unverified save. */ });
      }
    } catch { /* an invalid local draft never blocks the editor */ }
    setRestoredUser(userId);
    return () => { alive = false; };
  }, [userId, client]);
  useEffect(() => {
    if (!userId || restoredUser !== userId) return;
    try { sessionStorage.setItem(`rukh-website-draft:v1:${userId}`, JSON.stringify({ source, ...savedMetadata.current })); } catch { /* server save is still explicit */ }
  }, [source, savedSource, versions, userId, restoredUser, metadataRevision]);

  function updateStyle(property: string, value: string) {
    const document = new DOMParser().parseFromString(source, "text/html");
    const target = layer === "page" ? document.body : document.querySelector<HTMLElement>(`[data-layer="${layer}"]`);
    if (!target) { setError("This source does not contain the selected layer. Edit the source in Code."); return; }
    if (property === "gap") {
      target.style.display = "flex";
      target.style.flexDirection = "column";
      target.style.setProperty(property, value);
    } else if (property === "font-size" || property === "font-family") {
      const textTarget = target.matches("h1,h2,h3,p") ? target : target.querySelector<HTMLElement>("h1,h2,h3,p");
      if (!textTarget) { setError("This layer has no editable text. Select a text layer or edit the source in Code."); return; }
      textTarget.style.setProperty(property, value);
    } else {
      target.style.setProperty(property, value);
    }
    setSource("<!doctype html>\n" + document.documentElement.outerHTML); setError("");
  }
  async function save() {
    const owner = userId;
    const assertCurrent = () => { if (!mounted.current || activeUser.current !== owner) throw new Error("The account changed. Open the editor again to save."); };
    if (!client) throw new Error("Sign in to Coworker before saving this website to your workspace.");
    metadataGeneration.current += 1;
    const fingerprint = source;
    if (saveAttempt.current?.fingerprint !== fingerprint) saveAttempt.current = { fingerprint };
    const saved = await persistEditorCopy(client, source, "website-source.html.txt", saveAttempt.current);
    assertCurrent();
    if (projectId) { const project = await client.project(projectId); assertCurrent(); await client.linkProjectResource(project.id, "document", saved.documentId, project.revision); assertCurrent(); }
    const version = { source, at: new Date().toISOString(), documentId: saved.documentId };
    savedMetadata.current = { savedSource: source, versions: [version, ...savedMetadata.current.versions.filter(item => item.source !== source)].slice(0, 10) };
    setSavedSource(source);
    setVersions(current => [version, ...current.filter(item => item.source !== source)].slice(0, 10));
    saveAttempt.current = null;
    return saved;
  }
  async function perform(review = false) {
    if (busy) return; const owner = userId;
    const current = () => mounted.current && activeUser.current === owner;
    setBusy(true); setError("");
    try {
      const saved = await save();
      if (!current()) return;
      if (review && client) {
        const manifest = await client.workspaceManifest();
        if (!current()) return;
        const file = manifest.documents.find(item => item.document_id === saved.documentId && item.available);
        if (!file) throw new Error("The website source is saved but is not yet available to attach. Retry review shortly.");
        if (handoff.current?.fingerprint !== source) handoff.current = { fingerprint: source, conversationKey: crypto.randomUUID(), messageKey: crypto.randomUUID() };
        const pending = handoff.current;
        pending.conversationId ??= conversationId ?? (await client.createConversation("Website review", pending.conversationKey)).id;
        if (!current()) return;
        if (projectId) { const project = await client.project(projectId); if (!current()) return; await client.linkProjectResource(project.id, "conversation", pending.conversationId, project.revision); }
        if (!current()) return;
        await client.appendConversationMessage(pending.conversationId, "Review the attached website source. Suggest improvements; do not publish or perform external actions without approval.", pending.messageKey, [file.version_id]);
        if (!current()) return;
        const query = new URLSearchParams({ conversation: pending.conversationId, ...(projectId ? { project: projectId } : {}) });
        window.location.assign("/coworker?" + query);
      }
    } catch (error) { if (current()) setError(error instanceof Error ? error.message : "The website could not be saved."); }
    finally { if (current()) setBusy(false); }
  }
  return <section className="rukh-website-editor" aria-label="Website editor">
    <header className="rukh-website-title"><strong>Rukh landing page</strong><span role="status">{busy ? "Saving…" : source === savedSource ? "Draft saved" : "Unsaved draft"}</span><button className="cw-secondary" type="button" onClick={() => setView("design")}>Preview</button><button className="cw-primary" type="button" disabled={busy} onClick={() => { void perform(); }}>{busy ? "Saving…" : "Save to workspace"}</button></header>
    {error && <p className="cw-error" role="alert">{error}</p>}
    <nav className="rukh-website-tabs" aria-label="Website views">{["design", "code", "history"].map(value => <button key={value} type="button" aria-pressed={view === value} onClick={() => setView(value as typeof view)}>{value[0].toUpperCase() + value.slice(1)}</button>)}</nav>
    {view === "code" ? <label className="rukh-website-code-label">Website source<textarea aria-label="Website source" value={source} disabled={busy} onChange={event => setSource(event.target.value)} spellCheck={false} /></label> : view === "history" ? <section className="rukh-website-history"><h2>Saved versions</h2><p>Versions from this tab, verified against available workspace files.</p>{versions.length === 0 ? <p>No saved versions yet.</p> : versions.map(item => <button key={item.documentId} disabled={busy} onClick={() => { setSource(item.source); setView("design"); }}>Restore {new Date(item.at).toLocaleString()}</button>)}</section> : <div className="rukh-website-layout">
      <aside className="rukh-website-layers" aria-label="Website layers"><strong>LAYERS</strong>{["page", "header", "hero", "features", "footer"].map(value => <button key={value} aria-pressed={layer === value} onClick={() => setLayer(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}</aside>
      <iframe title="Website preview" className="rukh-website-preview" sandbox="" srcDoc={preview} />
      <aside className="rukh-website-inspector"><h2>Design</h2><p>Selected: {layer === "hero" ? "Hero section" : layer[0].toUpperCase() + layer.slice(1)}</p><section><h3>Layout</h3><label>Stack gap<input aria-label="Layout gap" type="number" min={0} max={96} value={layoutGap} disabled={busy} onChange={event => { const value = Math.max(0, Math.min(96, Number(event.target.value))); setLayoutGap(value); updateStyle("gap", value + "px"); }} /></label></section><section><h3>Typography</h3><label>Font family<select aria-label="Font family" value={fontFamily} disabled={busy} onChange={event => { setFontFamily(event.target.value); updateStyle("font-family", event.target.value); }}><option value="Inter">Inter</option><option value="Arial">Arial</option><option value="Georgia">Georgia</option><option value="system-ui">System UI</option></select></label><label>Font size<input aria-label="Typography size" type="number" min={12} max={96} value={fontSize} disabled={busy} onChange={event => { const value = Math.max(12, Math.min(96, Number(event.target.value))); setFontSize(value); updateStyle("font-size", value + "px"); }} /></label></section><section><h3>Background</h3><label>Color<input aria-label="Section background" type="color" value={background} disabled={busy} onChange={event => { setBackground(event.target.value); updateStyle("background-color", event.target.value); }} /></label></section><section><h3>Spacing</h3><label>Padding<input aria-label="Section spacing" type="number" min={0} max={200} value={padding} disabled={busy} onChange={event => { const value = Math.max(0, Math.min(200, Number(event.target.value))); setPadding(value); updateStyle("padding", value + "px"); }} /></label></section><p className="rukh-website-preview-note">Scripts and external content are blocked in this preview.</p></aside>
    </div>}
    <footer className="rukh-website-footer"><a className="cw-secondary" href={"/coworker" + (conversationId || projectId ? "?" + new URLSearchParams({ ...(conversationId ? { conversation: conversationId } : {}), ...(projectId ? { project: projectId } : {}) }) : "")}>← Back to Coworker</a><button className="cw-primary" disabled={busy} onClick={() => { void perform(true); }}>Review with Rukh</button></footer>
  </section>;
}
