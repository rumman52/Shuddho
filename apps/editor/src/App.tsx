import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import WritingAssistant from "../../web-editor/src/App";
import { ErrorBoundary } from "../../web-editor/src/components/ErrorBoundary";
import { CoworkerClient, isTextArtifact, type Artifact, type CoworkerTask } from "../../web-editor/src/coworker/client";
import { publicAuthConfig } from "../../web-editor/src/coworker/authConfig";

let authSingleton: SupabaseClient | null = null;
function getAuthClient(): SupabaseClient | null {
  const url = import.meta.env.VITE_SUPABASE_URL;
  const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
  if (!publicAuthConfig(url, key)) return null;
  authSingleton ??= createClient(url, key, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  return authSingleton;
}

type ArtifactItem = { artifact: Artifact; task: CoworkerTask };

export default function App() {
  const auth = useMemo(getAuthClient, []);
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(Boolean(auth));
  const [tasks, setTasks] = useState<CoworkerTask[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [reload, setReload] = useState(0);
  const [initialText, setInitialText] = useState<string | undefined>();
  const [openedArtifact, setOpenedArtifact] = useState("");
  const [editorText, setEditorText] = useState("");
  const onTextChange = useCallback((value: string) => setEditorText(value), []);

  const client = useMemo(() => auth && session ? new CoworkerClient(
    import.meta.env.VITE_COWORKER_API_BASE_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "/backend"),
    async () => {
      const current = (await auth.auth.getSession()).data.session;
      return current?.user.id === session.user.id ? current.access_token : null;
    },
  ) : null, [auth, session?.user.id]);

  useEffect(() => {
    if (!auth) return;
    let alive = true;
    auth.auth.getSession().then(({ data, error }) => {
      if (!alive) return;
      setSession(data.session);
      setAuthLoading(false);
      if (error) setLibraryError("Your sign-in session could not be restored. Open Coworker and sign in again.");
    }).catch(() => {
      if (alive) {
        setAuthLoading(false);
        setLibraryError("Your sign-in session could not be restored. Open Coworker and sign in again.");
      }
    });
    const { data } = auth.auth.onAuthStateChange((_event, next) => {
      if (!alive) return;
      setSession(next);
      setTasks([]);
      setLibraryError("");
    });
    return () => { alive = false; data.subscription.unsubscribe(); };
  }, [auth]);

  useEffect(() => {
    if (!client) { setTasks([]); setLibraryLoading(false); return; }
    const controller = new AbortController();
    setLibraryLoading(true);
    setLibraryError("");
    client.list(controller.signal).then(({ tasks: result }) => {
      if (!controller.signal.aborted) setTasks(result);
    }).catch(error => {
      if (!controller.signal.aborted) setLibraryError(error instanceof Error ? error.message : "Recent files could not be loaded.");
    }).finally(() => {
      if (!controller.signal.aborted) setLibraryLoading(false);
    });
    return () => controller.abort();
  }, [client, reload]);

  const artifacts = useMemo<ArtifactItem[]>(() =>
    tasks.flatMap(task => task.artifacts.map(artifact => ({ artifact, task })))
      .sort((a, b) => (b.artifact.created_at ?? b.task.created_at).localeCompare(a.artifact.created_at ?? a.task.created_at))
      .slice(0, 12),
  [tasks]);

  const coworkerUrl = import.meta.env.VITE_COWORKER_APP_URL ?? "/coworker";

  async function openArtifact(item: ArtifactItem) {
    if (!client || busy) return;
    setBusy(item.artifact.id);
    setLibraryError("");
    setNotice("");
    try {
      if (isTextArtifact(item.artifact)) {
        const content = await client.readTextArtifact(item.artifact);
        setInitialText(content);
        setOpenedArtifact(item.artifact.filename);
        setNotice(`Opened ${item.artifact.filename} in the editor. Changes here do not overwrite the saved artifact.`);
      } else {
        await client.download(item.artifact);
        setNotice(`Download started for ${item.artifact.filename}.`);
      }
    } catch (error) {
      setLibraryError(error instanceof Error ? error.message : "The file could not be opened.");
    } finally {
      setBusy("");
    }
  }

  async function sendToCoworker() {
    if (busy) return;
    if (!client) {
      setNotice("Sign in to Coworker first. Your editor text will remain in this tab.");
      window.location.assign(coworkerUrl);
      return;
    }
    const content = editorText.trim();
    if (!content) {
      setLibraryError("Add some text to the editor before sending it to Coworker.");
      return;
    }
    setBusy("handoff");
    setLibraryError("");
    setNotice("");
    try {
      const file = new File([editorText], "rukh-editor-draft.txt", { type: "text/plain" });
      const uploaded = await client.upload(file);
      const manifest = await client.workspaceManifest();
      const source = manifest.documents.find(item => item.document_id === uploaded.id && item.available);
      if (!source) throw new Error("The uploaded draft is not yet available as a verified workspace source. Refresh and try again.");
      const firstLine = content.split(/\r?\n/).find(line => line.trim())?.trim() ?? "Editor draft";
      const title = firstLine.slice(0, 80) || "Editor draft";
      const conversation = await client.createConversation(title, crypto.randomUUID());
      await client.appendConversationMessage(
        conversation.id,
        "I am handing off this editor draft for help. Please review the attached source, ask for missing context, and suggest the next useful step. Do not perform external actions without my explicit approval.",
        crypto.randomUUID(),
        [source.version_id],
      );
      const destination = new URL(coworkerUrl, window.location.origin);
      destination.searchParams.set("conversation", conversation.id);
      window.location.assign(destination.toString());
    } catch (error) {
      setLibraryError(error instanceof Error ? error.message : "The handoff could not be completed.");
    } finally {
      setBusy("");
    }
  }

  return (
    <ErrorBoundary>
      <div className="rukh-editor-app">
        <header className="rukh-editor-topbar">
          <a className="rukh-editor-brand" href="/editor">
            <span className="rukh-brand-mark" aria-hidden="true">r</span>
            <span><strong>Rukh AI</strong><small>Editor</small></span>
          </a>
          <div className="rukh-editor-top-actions">
            {openedArtifact && <span className="rukh-opened-file" title={openedArtifact}>Editing a copy of {openedArtifact}</span>}
            <button type="button" className="rukh-handoff-button" onClick={() => void sendToCoworker()} disabled={busy === "handoff"}>
              {busy === "handoff" ? "Sending…" : "Send to Coworker ↗"}
            </button>
            <a href={coworkerUrl} className="rukh-coworker-link">Open Coworker</a>
          </div>
        </header>
        <div className="rukh-editor-content">
          <section className="rukh-editor-canvas" aria-label="Writing editor">
            <WritingAssistant initialText={initialText} onTextChange={onTextChange} />
          </section>
          <aside className="rukh-editor-library" aria-label="Recent coworker files">
            <div className="rukh-library-heading">
              <div><span>WORKSPACE</span><h2>Recent files</h2></div>
              <button type="button" onClick={() => setReload(value => value + 1)} disabled={!client || libraryLoading}>↻</button>
            </div>
            {!auth && <div className="rukh-library-empty"><p>Connect your workspace sign-in to browse saved Coworker files.</p><a href={coworkerUrl}>Open Coworker</a></div>}
            {auth && !session && !authLoading && <div className="rukh-library-empty"><p>Sign in to Coworker to see your recent files and send drafts.</p><a href={coworkerUrl}>Sign in to Coworker ↗</a></div>}
            {authLoading && <p className="rukh-library-muted">Restoring your workspace session…</p>}
            {libraryError && <p className="rukh-library-error" role="alert">{libraryError}</p>}
            {notice && <p className="rukh-library-notice" role="status">{notice}</p>}
            {client && libraryLoading && <p className="rukh-library-muted">Loading recent files…</p>}
            {client && !libraryLoading && artifacts.length === 0 && !libraryError && <div className="rukh-library-empty"><p>No generated files yet. Completed Coworker work will appear here.</p></div>}
            {client && artifacts.length > 0 && <ul className="rukh-artifact-list">
              {artifacts.map(item => <li key={item.artifact.id}>
                <div><strong>{item.artifact.filename}</strong><small>{item.task.instruction} · {new Date(item.artifact.created_at ?? item.task.created_at).toLocaleDateString()}</small></div>
                <button type="button" disabled={Boolean(busy)} onClick={() => void openArtifact(item)}>
                  {busy === item.artifact.id ? "Opening…" : isTextArtifact(item.artifact) ? "Open" : "Download"}
                </button>
              </li>)}
            </ul>}
            <p className="rukh-library-footnote">Text and Markdown previews use the owner-authenticated route and are checked against their saved SHA-256 digest. Other file types download.</p>
          </aside>
        </div>
      </div>
    </ErrorBoundary>
  );
}
