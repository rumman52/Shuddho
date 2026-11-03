import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./styles.css";
import { type Session } from "@supabase/supabase-js";
import { getRukhAuthClient } from "@rukh/auth";
import WritingAssistant from "../../web-editor/src/App";
import ThemeToggle from "../../web-editor/src/components/ThemeToggle";
import { ErrorBoundary } from "../../web-editor/src/components/ErrorBoundary";
import { CoworkerClient, isTextArtifact, type Artifact, type CoworkerTask, type SourceDocument } from "../../web-editor/src/coworker/client";

type ArtifactItem = { artifact: Artifact; task: CoworkerTask };
type HandoffAttempt = {
  fingerprint: string;
  createKey: string;
  messageKey: string;
  uploaded?: SourceDocument;
  sourceVersionId?: string;
  conversationId?: string;
};

export default function App() {
  const coworkerEnabled = import.meta.env.VITE_COWORKER_ENABLED === "true";
  const auth = useMemo(() => coworkerEnabled
    ? getRukhAuthClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY)
    : null, [coworkerEnabled]);
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
  const [mobileLibraryOpen, setMobileLibraryOpen] = useState(false);
  const mobileLibraryTriggerRef = useRef<HTMLButtonElement | null>(null);
  const mobileLibraryCloseRef = useRef<HTMLButtonElement | null>(null);
  const mobileLibraryPanelRef = useRef<HTMLElement | null>(null);
  const [editorText, setEditorText] = useState("");
  const handoffAttempt = useRef<HandoffAttempt | null>(null);
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

  useEffect(() => {
    if (!mobileLibraryOpen || typeof window === "undefined" || typeof document === "undefined") return;
    const panel = mobileLibraryPanelRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => panel?.querySelectorAll<HTMLElement>(
      "a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex='-1'])"
    ) ?? [];
    const frame = window.requestAnimationFrame(() => {
      (mobileLibraryCloseRef.current ?? focusable()[0])?.focus();
    });
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileLibraryOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = Array.from(focusable());
      if (!items.length) { event.preventDefault(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      window.requestAnimationFrame(() => mobileLibraryTriggerRef.current?.focus());
    };
  }, [mobileLibraryOpen]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(min-width: 901px)");
    const closeOnDesktop = () => { if (media.matches) setMobileLibraryOpen(false); };
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", closeOnDesktop);
      return () => media.removeEventListener("change", closeOnDesktop);
    }
    media.addListener?.(closeOnDesktop);
    return () => media.removeListener?.(closeOnDesktop);
  }, []);

  async function openArtifact(item: ArtifactItem) {
    if (!client || busy) return;
    if (isTextArtifact(item.artifact) && editorText.trim() && !window.confirm("Replace the text currently in the editor with this saved file?")) return;
    setBusy(item.artifact.id);
    setLibraryError("");
    setNotice("");
    try {
      if (isTextArtifact(item.artifact)) {
        const content = await client.readTextArtifact(item.artifact);
        setInitialText(content);
        setOpenedArtifact(item.artifact.filename);
        setMobileLibraryOpen(false);
        setNotice(`Opened ${item.artifact.filename} in the editor. Changes here do not overwrite the saved artifact.`);
      } else {
        await client.download(item.artifact);
        setMobileLibraryOpen(false);
        setNotice(`Download started for ${item.artifact.filename}.`);
      }
    } catch (error) {
      setLibraryError(error instanceof Error ? error.message : "The file could not be opened.");
    } finally {
      setBusy("");
    }
  }

  async function sendToCoworker() {
    if (!coworkerEnabled || busy) return;
    if (!client) {
      setNotice("Sign in to Coworker in a new tab, then return here. Your editor text will remain in this tab.");
      return;
    }
    const content = editorText.trim();
    if (!content) {
      setLibraryError("Add some text to the editor before sending it to Coworker.");
      return;
    }

    const fingerprint = JSON.stringify({ userId: session?.user.id, text: editorText });
    if (handoffAttempt.current?.fingerprint !== fingerprint) {
      handoffAttempt.current = {
        fingerprint,
        createKey: crypto.randomUUID(),
        messageKey: crypto.randomUUID(),
      };
    }
    const attempt = handoffAttempt.current;
    if (!attempt) {
      setLibraryError("The handoff could not be initialized. Try again.");
      return;
    }
    const firstLine = content.split(/\r?\n/).find(line => line.trim())?.trim() ?? "Editor draft";
    const title = firstLine.slice(0, 80) || "Editor draft";

    setBusy("handoff");
    setLibraryError("");
    setNotice("");
    try {
      // Validate the destination before uploading anything or creating server records.
      const destination = new URL(coworkerUrl, window.location.origin);
      if (!["https:", "http:"].includes(destination.protocol) || destination.username || destination.password) {
        throw new Error("The Coworker destination URL is invalid.");
      }
      if (!import.meta.env.DEV && destination.origin !== window.location.origin) {
        throw new Error("Coworker must use the same origin as Editor so the authenticated workspace session is shared.");
      }

      // Preserve each successful stage across retries. The create/message idempotency
      // keys also make retries safe when a server committed but its response was lost.
      if (!attempt.uploaded) {
        const file = new File([editorText], "rukh-editor-draft.txt", { type: "text/plain" });
        attempt.uploaded = await client.upload(file);
      }
      const uploaded = attempt.uploaded;
      if (!uploaded) throw new Error("The draft upload did not return a document record.");

      if (!attempt.sourceVersionId) {
        const manifest = await client.workspaceManifest();
        const source = manifest.documents.find(item => item.document_id === uploaded.id && item.available);
        if (!source) throw new Error("The uploaded draft is not yet available as a verified workspace source. Retry after the workspace manifest refreshes.");
        attempt.sourceVersionId = source.version_id;
      }
      const sourceVersionId = attempt.sourceVersionId;
      if (!sourceVersionId) throw new Error("The uploaded draft has no verified source version.");

      if (!attempt.conversationId) {
        const conversation = await client.createConversation(title, attempt.createKey);
        attempt.conversationId = conversation.id;
      }
      const conversationId = attempt.conversationId;
      if (!conversationId) throw new Error("The Coworker conversation was not created.");

      await client.appendConversationMessage(
        conversationId,
        "I am handing off this editor draft for help. Please review the attached source, ask for missing context, and suggest the next useful step. Do not perform external actions without my explicit approval.",
        attempt.messageKey,
        [sourceVersionId],
      );
      destination.searchParams.set("conversation", conversationId);
      window.location.assign(destination.toString());
      handoffAttempt.current = null;
    } catch (error) {
      setLibraryError(error instanceof Error ? error.message : "The handoff could not be completed.");
    } finally {
      setBusy("");
    }
  }

  return (
    <ErrorBoundary>
      <div className="rukh-editor-app">
        <header className="rukh-editor-topbar" aria-hidden={mobileLibraryOpen ? true : undefined}>
          <a className="rukh-editor-brand" href="/" aria-label="Rukh AI workspace home" target="_blank" rel="noreferrer">
            <span className="rukh-brand-mark" aria-hidden="true">r</span>
            <span><strong>Rukh AI</strong><small>Web Editor</small></span>
          </a>
          <div className="rukh-editor-top-actions">
            {openedArtifact && <span className="rukh-opened-file" title={openedArtifact}>Editing a copy of {openedArtifact}</span>}
            {coworkerEnabled && <button
            ref={mobileLibraryTriggerRef}
            className="rukh-editor-mobile-files"
            type="button"
            aria-label="Open recent files"
            aria-controls="rukh-editor-library"
            aria-expanded={mobileLibraryOpen}
            onClick={() => setMobileLibraryOpen(true)}
          >Recent files</button>}
          <ThemeToggle />
          <a href="/workspaces" className="rukh-workspace-home" target="_blank" rel="noreferrer">All workspaces</a>
            {coworkerEnabled && <>
              <button type="button" className="rukh-handoff-button" onClick={() => void sendToCoworker()} disabled={busy === "handoff"}>
                {busy === "handoff" ? "Sending…" : "Send to AI Coworker ↗"}
              </button>
              <a href={coworkerUrl} className="rukh-coworker-link" target="_blank" rel="noreferrer">AI Coworker</a>
            </>}
          </div>
        </header>
        <div className={`rukh-editor-content${coworkerEnabled ? "" : " rukh-editor-content--standalone"}`}>
          {coworkerEnabled && <aside
            ref={mobileLibraryPanelRef}
            id="rukh-editor-library"
            className={"rukh-editor-library" + (mobileLibraryOpen ? " rukh-editor-library--open" : "")}
            aria-label="Recent AI Coworker files"
            role={mobileLibraryOpen ? "dialog" : undefined}
            aria-modal={mobileLibraryOpen ? true : undefined}
            aria-labelledby="rukh-library-title"
          >
            <div className="rukh-library-heading">
              <div><span>WORKSPACE</span><h2 id="rukh-library-title">Recent files</h2></div>
              <div className="rukh-library-actions">
                <button className="rukh-library-refresh" type="button" aria-label="Refresh recent files" onClick={() => setReload(value => value + 1)} disabled={!client || libraryLoading}>↻</button>
                <button className="rukh-library-close" ref={mobileLibraryCloseRef} type="button" aria-label="Close recent files" onClick={() => setMobileLibraryOpen(false)}>×</button>
              </div>
            </div>
            {!auth && <div className="rukh-library-empty"><p>Connect your Rukh AI account to browse saved Coworker files.</p><a href={coworkerUrl} target="_blank" rel="noreferrer">Open AI Coworker</a></div>}
            {auth && !session && !authLoading && <div className="rukh-library-empty"><p>Sign in to AI Coworker to see recent files and send drafts.</p><a href={coworkerUrl} target="_blank" rel="noreferrer">Sign in to AI Coworker ↗</a></div>}
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
          </aside>}
          {mobileLibraryOpen && <button className="rukh-editor-mobile-backdrop" type="button" aria-hidden="true" tabIndex={-1} onClick={() => setMobileLibraryOpen(false)} />}
          <section className="rukh-editor-canvas" aria-label="Writing editor" aria-hidden={mobileLibraryOpen ? true : undefined}>
            <WritingAssistant initialText={initialText} onTextChange={onTextChange} />
          </section>
        </div>
      </div>
    </ErrorBoundary>
  );
}
