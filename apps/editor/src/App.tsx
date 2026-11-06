import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import "./styles.css";
import { type Session } from "@supabase/supabase-js";
import { getRukhAuthClient } from "@rukh/auth";
import WorkspaceNavigation from "../../web-editor/src/coworker/WorkspaceNavigation";
import { RukhCompanionMark } from "../../web-editor/src/coworker/CoworkerWelcome";
import WritingAssistant from "../../web-editor/src/App";
import ThemeToggle from "../../web-editor/src/components/ThemeToggle";
import { ErrorBoundary } from "../../web-editor/src/components/ErrorBoundary";
import { CoworkerClient, isTextArtifact, type Artifact, type CoworkerTask, type ConversationRecord, type SourceDocument } from "../../web-editor/src/coworker/client";
import { clearEditorDraft, persistEditorCopy, readEditorDraft, writeEditorDraft, type EditorDraftRecord } from "./persistence.mjs";

type ArtifactItem = { artifact: Artifact; task: CoworkerTask };
type HandoffAttempt = {
  fingerprint: string;
  createKey: string;
  messageKey: string;
  uploaded?: SourceDocument;
  sourceVersionId?: string;
  conversationId?: string;
};
type SaveAttempt = { fingerprint: string; uploaded?: SourceDocument };
type SavedEditorRecord = { text: string; documentId: string; sha256: string; name: string };
type PendingSavedDocument = { id: string; sha256: string; text: string; name: string };

type LibraryView = "documents" | "history" | "trash";
type WritingLibraryItem =
  | { kind: "source"; id: string; filename: string; createdAt?: string; preview: string; source: SourceDocument }
  | { kind: "artifact"; id: string; filename: string; createdAt?: string; preview: string; artifactItem: ArtifactItem };

function formatDocumentDate(value?: string): string {
  if (!value) return "Recently added";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently added";
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(date);
}

function formatDocumentSize(bytes: number): string {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function isEditableSourceDocument(source: SourceDocument): boolean {
  return source.kind.toLowerCase() === "txt" && source.filename.toLowerCase().endsWith(".txt") && source.byte_size <= 1024 * 1024;
}


export default function App() {
  const coworkerEnabled = import.meta.env.VITE_COWORKER_ENABLED !== "false";
  const auth = useMemo(() => coworkerEnabled
    ? getRukhAuthClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY)
    : null, [coworkerEnabled]);
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(Boolean(auth));
  const [tasks, setTasks] = useState<CoworkerTask[]>([]);
  const [sourceDocuments, setSourceDocuments] = useState<SourceDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState("");
  const [documentSearch, setDocumentSearch] = useState("");
  const [libraryView, setLibraryView] = useState<LibraryView>("documents");
  const [editorOpen, setEditorOpen] = useState(false);
  const [recentConversations, setRecentConversations] = useState<ConversationRecord[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [reload, setReload] = useState(0);
  const [initialText, setInitialText] = useState<string | undefined>("");
  const [openedArtifact, setOpenedArtifact] = useState("");
  const [mobileLibraryOpen, setMobileLibraryOpen] = useState(false);
  const [editorContextOpen, setEditorContextOpen] = useState(false);
  const mobileLibraryTriggerRef = useRef<HTMLButtonElement | null>(null);
  const mobileLibraryCloseRef = useRef<HTMLButtonElement | null>(null);
  const mobileLibraryPanelRef = useRef<HTMLElement | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [editorText, setEditorText] = useState("");
  const [openedArtifactId, setOpenedArtifactId] = useState("");
  const [originConversationId, setOriginConversationId] = useState<string | null>(() => typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("conversation") : null);
  const [originProjectId, setOriginProjectId] = useState<string | null>(() => typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("project") : null);
  const [draftRestored, setDraftRestored] = useState(false);
  const [savedDocumentId, setSavedDocumentId] = useState("");
  const [savedSha256, setSavedSha256] = useState("");
  const [savedDocumentName, setSavedDocumentName] = useState("");
  const [saveStatus, setSaveStatus] = useState("");
  const [saveError, setSaveError] = useState("");
  const [pendingSavedDocument, setPendingSavedDocument] = useState<PendingSavedDocument | null>(null);
  const handoffAttempt = useRef<HandoffAttempt | null>(null);
  const saveAttempt = useRef<SaveAttempt | null>(null);
  const previousUserId = useRef<string | null>(null);
  const artifactQueryHandled = useRef(false);
  const lastSavedRecord = useRef<SavedEditorRecord | null>(null);
  const pendingSavedDocumentRef = useRef<PendingSavedDocument | null>(null);
  const onTextChange = useCallback((value: string) => {
    setEditorText(value);
    if (pendingSavedDocumentRef.current?.text === value) return;
    const saved = lastSavedRecord.current;
    if (saved && saved.text === value) {
      setSavedDocumentId(saved.documentId);
      setSavedSha256(saved.sha256);
      setSavedDocumentName(saved.name);
      setSaveStatus("Saved to workspace");
    } else {
      pendingSavedDocumentRef.current = null;
      setPendingSavedDocument(null);
      setSavedDocumentId("");
      setSavedSha256("");
      setSavedDocumentName("");
      setSaveStatus(value.trim() ? "Unsaved changes" : "");
    }
    setSaveError("");
  }, []);

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
      setSourceDocuments([]);
      setDocumentsError("");
      setLibraryError("");
    });
    return () => { alive = false; data.subscription.unsubscribe(); };
  }, [auth]);

  useEffect(() => {
    const userId = session?.user.id ?? null;
    const previousId = previousUserId.current;
    if (previousId && previousId !== userId && typeof window !== "undefined") {
      try { clearEditorDraft(window.sessionStorage, previousId); } catch { /* Storage may be unavailable. */ }
      lastSavedRecord.current = null;
      saveAttempt.current = null;
    }
    previousUserId.current = userId;
    if (!userId || typeof window === "undefined") {
      setDraftRestored(false);
      setEditorText("");
      setInitialText(undefined);
      setOpenedArtifact("");
      setOpenedArtifactId("");
      setSavedDocumentId("");
      setSavedSha256("");
      setSavedDocumentName("");
      setSaveStatus("");
      setSaveError("");
      setPendingSavedDocument(null);
      pendingSavedDocumentRef.current = null;
      lastSavedRecord.current = null;
      if (!userId) { setOriginConversationId(null); setOriginProjectId(null); }
      return;
    }
    const params = new URLSearchParams(window.location.search);
    try {
      const restored = readEditorDraft(window.sessionStorage, userId);
      if (restored) {
        setEditorText(restored.text);
        setInitialText(restored.text);
        setOpenedArtifact(restored.openedArtifact);
        setOpenedArtifactId(restored.openedArtifactId);
        setOriginConversationId(params.get("conversation") ?? restored.originConversationId);
        setOriginProjectId(params.get("project") ?? restored.originProjectId);
        if (restored.savedDocumentId && restored.savedSha256) {
          const pending = { id: restored.savedDocumentId, sha256: restored.savedSha256, text: restored.text, name: restored.savedDocumentName };
          pendingSavedDocumentRef.current = pending;
          setPendingSavedDocument(pending);
          setSavedDocumentId(restored.savedDocumentId);
          setSavedSha256(restored.savedSha256);
          setSavedDocumentName(restored.savedDocumentName);
          setSaveStatus("Verifying saved copy…");
        } else {
          setSavedDocumentId("");
          setSavedSha256("");
          setSavedDocumentName("");
          setSaveStatus(restored.text.trim() ? "Unsaved changes" : "");
        }
      } else {
        setOriginConversationId(params.get("conversation"));
        setOriginProjectId(params.get("project"));
      }
    } catch {
      setSaveError("The editor draft could not be restored in this tab.");
    }
    setDraftRestored(true);
  }, [session?.user.id]);

  useEffect(() => {
    if (!session || !draftRestored || typeof window === "undefined") return;
    const record: EditorDraftRecord = {
      text: editorText,
      openedArtifact,
      openedArtifactId,
      originConversationId,
      originProjectId,
      savedDocumentId: savedDocumentId || null,
      savedSha256: savedSha256 || null,
      savedDocumentName,
    };
    try { writeEditorDraft(window.sessionStorage, session.user.id, record); }
    catch { setSaveError("This browser could not preserve the editor draft in this tab."); }
  }, [session?.user.id, draftRestored, editorText, openedArtifact, openedArtifactId, originConversationId, originProjectId, savedDocumentId, savedSha256, savedDocumentName]);

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

  useEffect(() => {
    if (!client) {
      setSourceDocuments([]);
      setDocumentsLoading(false);
      setDocumentsError("");
      return;
    }
    const controller = new AbortController();
    setDocumentsLoading(true);
    setDocumentsError("");
    client.documents(controller.signal).then(({ documents }) => {
      if (!controller.signal.aborted) setSourceDocuments(documents);
    }).catch(error => {
      if (!controller.signal.aborted) setDocumentsError(error instanceof Error ? error.message : "Documents could not be loaded.");
    }).finally(() => {
      if (!controller.signal.aborted) setDocumentsLoading(false);
    });
    return () => controller.abort();
  }, [client, reload]);

  useEffect(() => {
    if (!client) { setRecentConversations([]); return; }
    const controller = new AbortController();
    client.conversations(controller.signal).then(({ items }) => {
      if (!controller.signal.aborted) setRecentConversations(items.slice(0, 3));
    }).catch(() => {
      if (!controller.signal.aborted) setRecentConversations([]);
    });
    return () => controller.abort();
  }, [client, reload]);

  useEffect(() => {
    if (!editorContextOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setEditorContextOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [editorContextOpen]);

  useEffect(() => {
    if (!client || !pendingSavedDocument || editorText !== pendingSavedDocument.text) return;
    let active = true;
    void (async () => {
      try {
        const [manifest, listing] = await Promise.all([client.workspaceManifest(), client.documents()]);
        if (!active) return;
        const manifestRecord = manifest.documents.find(item => item.document_id === pendingSavedDocument.id && item.available && item.sha256 === pendingSavedDocument.sha256);
        const listedRecord = listing.documents.find(item => item.id === pendingSavedDocument.id && item.state === "available");
        if (manifestRecord || listedRecord) {
          const record: SavedEditorRecord = {
            text: pendingSavedDocument.text,
            documentId: pendingSavedDocument.id,
            sha256: pendingSavedDocument.sha256,
            name: manifestRecord?.name ?? listedRecord?.filename ?? pendingSavedDocument.name,
          };
          lastSavedRecord.current = record;
          setSavedDocumentId(record.documentId);
          setSavedSha256(record.sha256);
          setSavedDocumentName(record.name);
          setSaveStatus("Saved to workspace");
          setSaveError("");
        } else {
          setSavedDocumentId("");
          setSavedSha256("");
          setSavedDocumentName("");
          setSaveStatus("Unsaved changes");
        }
      } catch (error) {
        if (active) {
          setSavedDocumentId("");
          setSavedSha256("");
          setSavedDocumentName("");
          setSaveStatus("Save status unavailable");
          setSaveError(error instanceof Error ? error.message : "The saved copy could not be verified.");
        }
      } finally {
        if (active) {
          pendingSavedDocumentRef.current = null;
          setPendingSavedDocument(null);
        }
      }
    })();
    return () => { active = false; };
  }, [client, pendingSavedDocument, editorText]);

  const artifacts = useMemo<ArtifactItem[]>(() =>
    tasks.flatMap(task => task.artifacts.map(artifact => ({ artifact, task })))
      .sort((a, b) => (b.artifact.created_at ?? b.task.created_at).localeCompare(a.artifact.created_at ?? a.task.created_at))
      .slice(0, 12),
  [tasks]);

  const libraryItems = useMemo<WritingLibraryItem[]>(() => {
    const uploaded: WritingLibraryItem[] = sourceDocuments.map(source => ({
      kind: "source",
      id: source.id,
      filename: source.filename,
      createdAt: source.created_at,
      preview: source.kind.toUpperCase() + " document · " + formatDocumentSize(source.byte_size),
      source,
    }));
    const generated: WritingLibraryItem[] = artifacts.map(artifactItem => ({
      kind: "artifact",
      id: artifactItem.artifact.id,
      filename: artifactItem.artifact.filename,
      createdAt: artifactItem.artifact.created_at ?? artifactItem.task.created_at,
      preview: artifactItem.task.instruction?.trim() || "Generated by Rukh AI",
      artifactItem,
    }));
    return [...uploaded, ...generated].sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
  }, [sourceDocuments, artifacts]);

  const filteredLibraryItems = useMemo(() => {
    const query = documentSearch.trim().toLocaleLowerCase();
    if (!query) return libraryItems;
    return libraryItems.filter(item => (item.filename + " " + item.preview).toLocaleLowerCase().includes(query));
  }, [libraryItems, documentSearch]);

  const coworkerUrl = import.meta.env.VITE_COWORKER_APP_URL ?? "/coworker";
  const coworkerReturnUrl = useMemo(() => {
    if (typeof window === "undefined") return coworkerUrl;
    const destination = new URL(coworkerUrl, window.location.origin);
    if (originConversationId) destination.searchParams.set("conversation", originConversationId);
    if (originProjectId) destination.searchParams.set("project", originProjectId);
    return destination.toString();
  }, [coworkerUrl, originConversationId, originProjectId]);

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

  async function openArtifact(item: ArtifactItem): Promise<boolean> {
    if (!client || busy) return false;
    if (isTextArtifact(item.artifact) && editorText.trim() && saveStatus !== "Saved to workspace" && !window.confirm("Replace the text currently in the editor with this saved file?")) return false;
    setBusy(item.artifact.id);
    setLibraryError("");
    setNotice("");
    setSaveError("");
    try {
      if (isTextArtifact(item.artifact)) {
        const content = await client.readTextArtifact(item.artifact);
        lastSavedRecord.current = null;
        pendingSavedDocumentRef.current = null;
        setPendingSavedDocument(null);
        setSavedDocumentId("");
        setSavedSha256("");
        setSavedDocumentName("");
        setSaveStatus(content.trim() ? "Unsaved changes" : "");
        setInitialText(content);
        setEditorOpen(true);
        setLibraryView("documents");
        setEditorContextOpen(false);
        setEditorText(content);
        setOpenedArtifact(item.artifact.filename);
        setOpenedArtifactId(item.artifact.id);
        setMobileLibraryOpen(false);
        setNotice(`Opened ${item.artifact.filename}. Save a new workspace copy to keep your edits; the original artifact is unchanged.`);
      } else {
        await client.download(item.artifact);
        setMobileLibraryOpen(false);
        setNotice(`Download started for ${item.artifact.filename}.`);
      }
      return true;
    } catch (error) {
      setLibraryError(error instanceof Error ? error.message : "The file could not be opened.");
      return false;
    } finally {
      setBusy("");
    }
  }

  function createNewDocument() {
    if (editorText.trim() && saveStatus !== "Saved to workspace" && !window.confirm("Start a new document? Your current unsaved editor draft will be replaced in this tab.")) return;
    lastSavedRecord.current = null;
    pendingSavedDocumentRef.current = null;
    saveAttempt.current = null;
    setPendingSavedDocument(null);
    setInitialText("");
    setEditorText("");
    setOpenedArtifact("");
    setOpenedArtifactId("");
    setSavedDocumentId("");
    setSavedSha256("");
    setSavedDocumentName("");
    setSaveStatus("");
    setSaveError("");
    setNotice("");
    setDocumentsError("");
    setLibraryView("documents");
    setEditorContextOpen(false);
    setMobileLibraryOpen(false);
    setEditorOpen(true);
  }

  function backToDocuments() {
    setEditorOpen(false);
    setEditorContextOpen(false);
    setMobileLibraryOpen(false);
    setLibraryView("documents");
  }

  async function openSourceDocument(source: SourceDocument): Promise<boolean> {
    if (!client || busy) return false;
    if (!isEditableSourceDocument(source)) {
      await downloadSourceDocument(source);
      return false;
    }
    if (editorText.trim() && saveStatus !== "Saved to workspace" && !window.confirm("Replace the text currently in the editor with this uploaded file?")) return false;
    setBusy(source.id);
    setDocumentsError("");
    setNotice("");
    setSaveError("");
    try {
      const content = await client.readTextDocument(source);
      lastSavedRecord.current = null;
      pendingSavedDocumentRef.current = null;
      setPendingSavedDocument(null);
      setSavedDocumentId("");
      setSavedSha256("");
      setSavedDocumentName("");
      setSaveStatus(content.trim() ? "Unsaved changes" : "");
      setInitialText(content);
      setEditorText(content);
      setOpenedArtifact(source.filename);
      setOpenedArtifactId(source.id);
      setEditorOpen(true);
      setLibraryView("documents");
      setEditorContextOpen(false);
      setMobileLibraryOpen(false);
      setNotice("Opened " + source.filename + ". Save your changes as a new copy; the uploaded original remains unchanged.");
      return true;
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "The uploaded file could not be opened.");
      return false;
    } finally {
      setBusy("");
    }
  }

  async function downloadSourceDocument(source: SourceDocument) {
    if (!client || busy) return;
    setBusy(source.id);
    setDocumentsError("");
    try {
      await client.downloadSourceDocument(source);
      setNotice("Download started for " + source.filename + ".");
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "The uploaded file could not be downloaded.");
    } finally {
      setBusy("");
    }
  }

  async function downloadArtifactFile(item: ArtifactItem) {
    if (!client || busy) return;
    setBusy(item.artifact.id);
    setDocumentsError("");
    try {
      await client.download(item.artifact);
      setNotice("Download started for " + item.artifact.filename + ".");
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "The generated file could not be downloaded.");
    } finally {
      setBusy("");
    }
  }

  async function removeSourceDocument(source: SourceDocument) {
    if (!client || busy || !window.confirm("Remove " + source.filename + " from your active workspace?")) return;
    setBusy(source.id);
    setDocumentsError("");
    try {
      const result = await client.deleteDocument(source.id);
      setSourceDocuments(previous => previous.filter(item => item.id !== source.id));
      setNotice(result.message || source.filename + " was removed from Documents.");
      setReload(value => value + 1);
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "The document could not be removed.");
    } finally {
      setBusy("");
    }
  }

  async function uploadSourceDocument(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    if (!client) {
      setDocumentsError("Sign in to AI Coworker before uploading files to your workspace.");
      return;
    }
    if (busy) return;
    setBusy("upload");
    setDocumentsError("");
    setNotice("");
    try {
      const uploaded = await client.upload(file);
      setSourceDocuments(previous => [uploaded, ...previous.filter(item => item.id !== uploaded.id)]);
      setReload(value => value + 1);
      setNotice("Uploaded " + uploaded.filename + ". It is now available in Documents.");
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "The document could not be uploaded.");
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    if (artifactQueryHandled.current || !client || libraryLoading || !draftRestored || typeof window === "undefined") return;
    const artifactId = new URLSearchParams(window.location.search).get("artifact_id");
    if (!artifactId) { artifactQueryHandled.current = true; return; }
    const item = artifacts.find(entry => entry.artifact.id === artifactId);
    if (!item) {
      if (!libraryError) setLibraryError("The requested text artifact is not available in this workspace.");
      artifactQueryHandled.current = true;
      return;
    }
    artifactQueryHandled.current = true;
    void openArtifact(item).then(opened => {
      if (!opened) return;
      const next = new URL(window.location.href);
      next.searchParams.delete("artifact_id");
      window.history.replaceState({}, "", next.toString());
    });
  }, [client, artifacts, libraryLoading, draftRestored, libraryError]);

  async function saveToWorkspace() {
    if (!client) {
      setSaveStatus("Sign-in required");
      setSaveError("Sign in to AI Coworker before saving this editor copy to your workspace.");
      return;
    }
    if (!editorText.trim()) {
      setSaveStatus("");
      setSaveError("Add text to the editor before saving.");
      return;
    }
    const baseName = (openedArtifact || "Untitled document").replace(/\.[^.]+$/, "");
    const safeName = baseName.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^\.+/, "").slice(0, 88) || "rukh-editor-draft";
    const filename = openedArtifact ? `${safeName}-edited.txt` : `${safeName}.txt`;
    const fingerprint = JSON.stringify({ userId: session?.user.id, text: editorText, filename });
    if (saveAttempt.current?.fingerprint !== fingerprint) saveAttempt.current = { fingerprint };
    const attempt = saveAttempt.current;
    if (!attempt) { setSaveError("The save could not be initialized. Try again."); return; }

    setBusy("save");
    setSaveStatus("Saving to workspace…");
    setSaveError("");
    try {
      const saved = await persistEditorCopy(client, editorText, filename, attempt);
      if (originProjectId) {
        const project = await client.project(originProjectId);
        await client.linkProjectResource(project.id, "document", saved.documentId, project.revision);
      }
      const record: SavedEditorRecord = { text: editorText, ...saved };
      lastSavedRecord.current = record;
      pendingSavedDocumentRef.current = null;
      setPendingSavedDocument(null);
      setSavedDocumentId(saved.documentId);
      setSavedSha256(saved.sha256);
      setSavedDocumentName(saved.name);
      setSaveStatus("Saved to workspace");
      setSaveError("");
      setNotice(`Saved ${saved.name} as a new workspace copy. The original artifact was not overwritten.`);
      setReload(value => value + 1);
      saveAttempt.current = null;
    } catch (error) {
      setSaveStatus("Save failed");
      setSaveError(error instanceof Error ? error.message : "The editor copy could not be saved.");
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

    const fingerprint = JSON.stringify({ userId: session?.user.id, text: editorText, originConversationId });
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
        if (originConversationId) attempt.conversationId = originConversationId;
        else {
          const conversation = await client.createConversation(title, attempt.createKey);
          attempt.conversationId = conversation.id;
        }
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
      if (originProjectId) destination.searchParams.set("project", originProjectId);
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
      <div className={"rukh-editor-app" + (editorOpen ? "" : " rukh-editor-app--documents")}>
        <header className="rukh-editor-topbar" aria-hidden={mobileLibraryOpen ? true : undefined}>
          <div className="rukh-editor-topbar-heading">
            {coworkerEnabled && <button
              ref={mobileLibraryTriggerRef}
              className="rukh-editor-mobile-files"
              type="button"
              aria-label="Open navigation"
              aria-controls="rukh-editor-library"
              aria-expanded={mobileLibraryOpen}
              onClick={() => { setEditorContextOpen(false); setMobileLibraryOpen(true); }}
            ><span aria-hidden="true">☰</span></button>}
            <strong>Writing Assistant</strong>
          </div>
          <div className="rukh-editor-top-actions">
            {!editorOpen ? (
              <span className="rukh-documents-session-status" role="status">
                {authLoading ? "Restoring workspace…" : client ? "Private workspace" : "Sign in to upload documents"}
              </span>
            ) : (
              <>
                <button type="button" className="rukh-editor-back-button" onClick={backToDocuments}>← Documents</button>
                {openedArtifact && <span className="rukh-opened-file" title={openedArtifact}>Editing a copy of {openedArtifact}</span>}
                {coworkerEnabled && <>
                  {saveStatus && <span className="rukh-editor-save-status" role="status">{saveStatus}</span>}
                  {saveError && <span className="rukh-editor-save-error" role="alert">{saveError}</span>}
                  <button type="button" className="rukh-save-workspace-button" onClick={() => void saveToWorkspace()}
                    disabled={!editorText.trim() || busy === "save" || saveStatus === "Verifying saved copy…" || (Boolean(savedDocumentId) && saveStatus === "Saved to workspace")}
                    aria-label="Save editor copy to workspace">
                    {busy === "save" ? "Saving…" : saveStatus === "Verifying saved copy…" ? "Verifying…" : savedDocumentId && saveStatus === "Saved to workspace" ? "Saved" : "Save to workspace"}
                  </button>
                  <button type="button" className="rukh-handoff-button" onClick={() => void sendToCoworker()} disabled={busy === "handoff"}>
                    {busy === "handoff" ? "Sending…" : "Send to AI Coworker ↗"}
                  </button>
                  <a href={coworkerReturnUrl} className="rukh-coworker-link">{originConversationId ? "Return to Coworker" : "AI Coworker"}</a>
                </>}
                {coworkerEnabled && <button
                  type="button"
                  className="rukh-editor-context-trigger"
                  aria-controls="rukh-editor-context"
                  aria-expanded={editorContextOpen}
                  onClick={() => { setMobileLibraryOpen(false); setEditorContextOpen(value => !value); }}
                >Activity &amp; context</button>}
                {!coworkerEnabled && <a className="rukh-workspace-home" href="/workspaces" target="_blank" rel="noreferrer">All workspaces</a>}
              </>
            )}
          </div>
        </header>
        <div className={`rukh-editor-content${coworkerEnabled ? "" : " rukh-editor-content--standalone"}`}>
          {coworkerEnabled && <aside
            ref={mobileLibraryPanelRef}
            id="rukh-editor-library"
            className={"rukh-editor-library" + (mobileLibraryOpen ? " rukh-editor-library--open" : "")}
            aria-label="Workspace navigation"
            role={mobileLibraryOpen ? "dialog" : undefined}
            aria-modal={mobileLibraryOpen ? true : undefined}
            aria-labelledby="rukh-editor-recent-chats-title"
          >
            <div className="rukh-editor-sidebar-brand">
              <a href="/coworker" className="rukh-design-brand"><RukhCompanionMark /><strong>rukh<sup>AI</sup></strong></a>
              <button className="rukh-library-close" ref={mobileLibraryCloseRef} type="button" aria-label="Close navigation" onClick={() => setMobileLibraryOpen(false)}>×</button>
            </div>
            <a href="/coworker" className="rukh-design-new rukh-editor-new-chat">+ New chat</a>
            <WorkspaceNavigation active="writing" writingHref="/writing" onNavigate={view => window.location.assign("/coworker?view=" + encodeURIComponent(view))} />
            {!editorOpen && <nav className="rukh-writing-library-nav" aria-label="Writing Assistant document sections">
              <span className="rukh-writing-library-nav__label">DOCUMENTS</span>
              <button type="button" className={libraryView === "documents" ? "is-active" : ""} aria-current={libraryView === "documents" ? "page" : undefined}
                onClick={() => { setLibraryView("documents"); setMobileLibraryOpen(false); }}><span aria-hidden="true">▤</span>Documents</button>
              <button type="button" className={libraryView === "history" ? "is-active" : ""} aria-current={libraryView === "history" ? "page" : undefined}
                onClick={() => { setLibraryView("history"); setMobileLibraryOpen(false); }}><span aria-hidden="true">◷</span>Version history</button>
              <button type="button" className={libraryView === "trash" ? "is-active" : ""} aria-current={libraryView === "trash" ? "page" : undefined}
                onClick={() => { setLibraryView("trash"); setMobileLibraryOpen(false); }}><span aria-hidden="true">▱</span>Trash</button>
            </nav>}
            <section className="rukh-editor-recent-chats" aria-labelledby="rukh-editor-recent-chats-title">
              <div className="rukh-editor-sidebar-heading">
                <span id="rukh-editor-recent-chats-title">RECENT CHATS</span>
                <a href="/coworker" aria-label="Open all conversations">⌕</a>
              </div>
              {!client && <p className="rukh-editor-sidebar-empty">Sign in to see your conversations.</p>}
              {client && recentConversations.length === 0 && <p className="rukh-editor-sidebar-empty">Your recent conversations will appear here.</p>}
              {recentConversations.length > 0 && <ul className="rukh-editor-chat-list">
                {recentConversations.map(item => <li key={item.id}>
                  <a href={"/coworker?conversation=" + encodeURIComponent(item.id)} title={item.title}>{item.title}</a>
                </li>)}
              </ul>}
            </section>
            <details className="rukh-editor-recent-files">
              <summary>Recent files</summary>
              <div className="rukh-library-heading">
                <div><span>WORKSPACE</span><h2 id="rukh-library-title">Recent files</h2></div>
                <div className="rukh-library-actions">
                  <button className="rukh-library-refresh" type="button" aria-label="Refresh recent files" onClick={() => setReload(value => value + 1)} disabled={!client || libraryLoading}>↻</button>
                </div>
              </div>
              {!auth && <div className="rukh-library-empty"><p>Connect your Rukh AI account to browse saved Coworker files.</p><a href={coworkerUrl}>Open AI Coworker</a></div>}
              {auth && !session && !authLoading && <div className="rukh-library-empty"><p>Sign in to AI Coworker to see recent files and send drafts.</p><a href={coworkerUrl}>Sign in to AI Coworker</a></div>}
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
            </details>
            <div className="rukh-design-account">
              <div><span className="rukh-design-account-avatar">{(session?.user.email?.[0] ?? "R").toUpperCase()}</span><span><strong title={session?.user.email ?? "Personal workspace"}>{session?.user.email ?? "Personal workspace"}</strong><small>Personal workspace</small></span></div>
              <ThemeToggle />
              <a href="/coworker?view=settings" aria-label="Settings" className="rukh-editor-settings-link">⚙</a>
            </div>
          </aside>}
          <section className="rukh-document-dashboard" aria-label="Writing Assistant documents" hidden={editorOpen} aria-hidden={mobileLibraryOpen ? true : undefined}>
            <input ref={uploadInputRef} className="rukh-document-upload-input" type="file" accept=".txt,.docx,.pdf,.csv,.xlsx,.pptx"
              aria-label="Upload a document file" onChange={uploadSourceDocument} />
            <header className="rukh-documents-heading">
              <div>
                <p className="rukh-documents-eyebrow">WRITING ASSISTANT</p>
                <h1>{libraryView === "documents" ? "Documents" : libraryView === "history" ? "Version history" : "Trash"}</h1>
                <p>{libraryView === "documents" ? "Your drafts and saved files, together in one place." : libraryView === "history" ? "Review earlier versions of your writing." : "Manage documents removed from your active workspace."}</p>
              </div>
              {libraryView === "documents" && <div className="rukh-documents-actions">
                {editorText.trim() && <button type="button" className="rukh-document-button rukh-document-button--quiet" onClick={() => setEditorOpen(true)}>Continue editing</button>}
                <button type="button" className="rukh-document-button rukh-document-button--primary" onClick={createNewDocument}><span aria-hidden="true">＋</span>New document</button>
                <button type="button" className="rukh-document-button rukh-document-button--secondary" onClick={() => uploadInputRef.current?.click()}
                  disabled={!client || authLoading || busy === "upload"} title={!client ? "Sign in to upload files" : "Upload a document"}><span aria-hidden="true">↑</span>{busy === "upload" ? "Uploading…" : "Upload file"}</button>
              </div>}
            </header>
            {libraryView === "documents" ? (
              <>
                <div className="rukh-documents-toolbar">
                  <label className="rukh-documents-search">
                    <span aria-hidden="true">⌕</span>
                    <input type="search" value={documentSearch} onChange={event => setDocumentSearch(event.target.value)} placeholder="Search documents…" aria-label="Search documents" />
                  </label>
                  <span className="rukh-documents-count">{filteredLibraryItems.length} {filteredLibraryItems.length === 1 ? "document" : "documents"}</span>
                </div>
                {documentsError && <p className="rukh-documents-message rukh-documents-message--error" role="alert">{documentsError}</p>}
                {libraryError && <p className="rukh-documents-message rukh-documents-message--error" role="alert">{libraryError}</p>}
                {notice && <p className="rukh-documents-message" role="status">{notice}</p>}
                {documentsLoading || libraryLoading ? (
                  <div className="rukh-document-empty-state" role="status">Loading your documents…</div>
                ) : filteredLibraryItems.length ? (
                  <section className="rukh-document-grid" aria-label="Saved documents">
                    {filteredLibraryItems.map(item => {
                      const isSource = item.kind === "source";
                      const canOpen = isSource ? isEditableSourceDocument(item.source) : isTextArtifact(item.artifactItem.artifact);
                      const typeLabel = isSource ? item.source.kind.toUpperCase() : "AI OUTPUT";
                      const busyForItem = busy === item.id;
                      const preview = item.preview.length > 180 ? item.preview.slice(0, 177) + "…" : item.preview;
                      return (
                        <article className="rukh-document-card" key={item.kind + ":" + item.id}>
                          <div className="rukh-document-card__meta">
                            <span className="rukh-document-card__file-icon" aria-hidden="true">▤</span>
                            <time dateTime={item.createdAt || undefined}>{formatDocumentDate(item.createdAt)}</time>
                          </div>
                          <h2 title={item.filename}>{item.filename}</h2>
                          <p className="rukh-document-card__preview">{preview}</p>
                          <div className="rukh-document-card__footer">
                            <span className="rukh-document-card__type">{typeLabel}</span>
                            <div className="rukh-document-card__actions">
                              <button type="button" className="rukh-document-card__open" disabled={busyForItem}
                                onClick={() => {
                                  if (isSource) {
                                    if (canOpen) void openSourceDocument(item.source);
                                    else void downloadSourceDocument(item.source);
                                  } else {
                                    void openArtifact(item.artifactItem);
                                  }
                                }}>{busyForItem ? "Working…" : canOpen ? "Open" : "Download"}</button>
                              <button type="button" className="rukh-document-card__icon-action" aria-label={"Download " + item.filename} title="Download"
                                disabled={busyForItem} onClick={() => {
                                  if (isSource) void downloadSourceDocument(item.source);
                                  else void downloadArtifactFile(item.artifactItem);
                                }}>↓</button>
                              {isSource && <button type="button" className="rukh-document-card__icon-action" aria-label={"Remove " + item.filename} title="Remove from workspace"
                                disabled={busyForItem} onClick={() => void removeSourceDocument(item.source)}>⌫</button>}
                            </div>
                          </div>
                        </article>
                      );
                    })}
                  </section>
                ) : (
                  <div className="rukh-document-empty-state">
                    <span className="rukh-document-empty-state__icon" aria-hidden="true">▤</span>
                    <h2>{documentSearch.trim() ? "No matching documents" : "No documents yet"}</h2>
                    <p>{documentSearch.trim() ? "Try another search term or clear your search." : client ? "Create a new document or upload a file to start your writing library." : "Create a local draft now, or sign in to upload and access saved workspace files."}</p>
                    {!documentSearch.trim() && <div className="rukh-document-empty-state__actions">
                      <button type="button" className="rukh-document-button rukh-document-button--primary" onClick={createNewDocument}>Create a document</button>
                      <button type="button" className="rukh-document-button rukh-document-button--secondary" onClick={() => uploadInputRef.current?.click()} disabled={!client || authLoading}>Upload a file</button>
                    </div>}
                  </div>
                )}
              </>
            ) : libraryView === "history" ? (
              <div className="rukh-document-empty-state">
                <span className="rukh-document-empty-state__icon" aria-hidden="true">◷</span>
                <h2>Version history is not available yet</h2>
                <p>The current workspace API stores saved copies as separate documents and does not expose earlier versions for browsing.</p>
                <button type="button" className="rukh-document-button rukh-document-button--secondary" onClick={() => setLibraryView("documents")}>Back to Documents</button>
              </div>
            ) : (
              <div className="rukh-document-empty-state">
                <span className="rukh-document-empty-state__icon" aria-hidden="true">▱</span>
                <h2>Trash and restore are not available yet</h2>
                <p>Removing a document hides it from the active library. The current workspace API does not expose a recoverable Trash view.</p>
                <button type="button" className="rukh-document-button rukh-document-button--secondary" onClick={() => setLibraryView("documents")}>Back to Documents</button>
              </div>
            )}
          </section>
          {mobileLibraryOpen && <button className="rukh-editor-mobile-backdrop" type="button" aria-hidden="true" tabIndex={-1} onClick={() => setMobileLibraryOpen(false)} />}
          <section className="rukh-editor-canvas" aria-label="Writing editor" hidden={!editorOpen} aria-hidden={mobileLibraryOpen || !editorOpen ? true : undefined}>
            <div className="rukh-writing-mode">
            <WritingAssistant initialText={initialText} onTextChange={onTextChange} documentTitle={savedDocumentName || openedArtifact || "Untitled document"} />
            </div>
          </section>
        </div>
        {coworkerEnabled && editorContextOpen && <button className="rukh-editor-context-backdrop" type="button" aria-label="Dismiss activity and context panel" onClick={() => setEditorContextOpen(false)} />}
        {coworkerEnabled && <aside id="rukh-editor-context" className={"rukh-editor-context-panel" + (editorContextOpen ? " is-open" : "")} aria-label="Activity and context" hidden={!editorContextOpen}>
          <header><h2>Activity &amp; context</h2><button type="button" aria-label="Close activity and context" onClick={() => setEditorContextOpen(false)}>×</button></header>
          <section><span>WORKSPACE</span><strong>{session?.user.email ?? "Personal workspace"}</strong><p>Your writing work stays in your private workspace.</p></section>
          <section><span>PROJECT CONTEXT</span><p>{originProjectId ? "This writing session was opened with project context." : "No project is linked to this writing session."}</p></section>
          <section><span>COWORKER CONVERSATION</span><p>{originConversationId ? "This editor was opened from a Coworker conversation." : "No Coworker conversation is linked yet."}</p><a href={coworkerReturnUrl}>Open Coworker</a></section>
          <section><span>RECENT OUTPUTS</span>
            {artifacts.length === 0 ? <p>No generated outputs are available yet.</p> : <ul>{artifacts.slice(0, 3).map(item => <li key={item.artifact.id}><button type="button" disabled={Boolean(busy)} onClick={() => void openArtifact(item)}>{item.artifact.filename}</button></li>)}</ul>}
          </section>
          <p className="rukh-editor-context-note">Writing Assistant keeps your text in a private workspace. Save a copy or send it to AI Coworker when you are ready.</p>
        </aside>}
      </div>
    </ErrorBoundary>
  );
}
