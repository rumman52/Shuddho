import { useEffect, useMemo, useRef, useState } from "react";
import type {
  CoworkerClient,
  GitHubInstallation,
  GitHubRepository,
  GitHubRepositoryBinding,
  GitHubRepositoryFile,
  GitHubRepositoryTree,
} from "./client";
import "./fly-repository-panel.css";

type Props = {
  client: CoworkerClient;
  projectId: string;
  onProjectChange: (projectId: string) => void;
  onBindingChange: (binding: GitHubRepositoryBinding | null) => void;
  onImportFiles: (files: GitHubRepositoryFile[]) => Promise<void>;
};

const MAX_IMPORT_FILES = 8;
const callbackKeys = ["code", "state", "installation_id", "setup_action", "error", "error_description"];

function clearCallbackParameters() {
  const url = new URL(window.location.href);
  for (const key of callbackKeys) url.searchParams.delete(key);
  window.history.replaceState({}, "", url.pathname + url.search + url.hash);
}

function safeGitHubRedirect(value: string, kind: "oauth" | "install") {
  const target = new URL(value);
  const validPath = kind === "oauth"
    ? target.pathname === "/login/oauth/authorize"
    : /^\/apps\/[a-z0-9-]+\/installations\/new$/.test(target.pathname);
  if (target.protocol !== "https:" || target.hostname !== "github.com" || target.port || !validPath || target.username || target.password) {
    throw new Error("GitHub returned an unexpected authorization destination. No redirect was followed.");
  }
  return target.toString();
}

const errorMessage = (value: unknown) =>
  value instanceof Error ? value.message : "GitHub repository access could not complete.";

export default function FlyRepositoryPanel({
  client,
  projectId,
  onProjectChange,
  onBindingChange,
  onImportFiles,
}: Props) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [binding, setBinding] = useState<GitHubRepositoryBinding | null>(null);
  const [installation, setInstallation] = useState<GitHubInstallation | null>(null);
  const [installations, setInstallations] = useState<GitHubInstallation[]>([]);
  const [installationRecordId, setInstallationRecordId] = useState("");
  const [repositories, setRepositories] = useState<GitHubRepository[]>([]);
  const [repositoryId, setRepositoryId] = useState("");
  const [tree, setTree] = useState<GitHubRepositoryTree | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const callbackHandled = useRef(false);

  useEffect(() => {
    let alive = true;
    client.githubStatus().then(value => {
      if (alive) setEnabled(value.enabled);
    }).catch(failure => {
      if (alive) {
        setEnabled(false);
        setError(errorMessage(failure));
      }
    });
    return () => { alive = false; };
  }, [client]);

  useEffect(() => {
    if (!enabled || callbackHandled.current) return;
    let alive = true;
    client.githubInstallations().then(value => {
      if (!alive) return;
      setInstallations(value.items);
      if (value.items.length === 1) {
        setInstallation(value.items[0]);
        setInstallationRecordId(current => current || value.items[0].id);
      }
    }).catch(failure => {
      if (alive) setError(errorMessage(failure));
    });
    return () => { alive = false; };
  }, [client, enabled]);

  useEffect(() => {
    if (callbackHandled.current || typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    const installationId = params.get("installation_id");
    const oauthError = params.get("error");
    if (!code && !installationId && !oauthError) return;
    callbackHandled.current = true;
    clearCallbackParameters();
    if (oauthError) {
      setError("GitHub authorization was not completed. " + (params.get("error_description") ?? "Start the connection again."));
      return;
    }
    if (!state) {
      setError("The GitHub callback is missing its one-time state. Start the connection again.");
      return;
    }
    if (code) {
      setBusy("oauth");
      setError("");
      client.githubFinishOAuth(code, state).then(result => {
        window.location.assign(safeGitHubRedirect(result.install_url, "install"));
      }).catch(failure => {
        setError(errorMessage(failure));
        setBusy("");
      });
      return;
    }
    const parsedInstallationId = Number(installationId);
    if (!Number.isSafeInteger(parsedInstallationId) || parsedInstallationId <= 0) {
      setError("GitHub returned an invalid installation ID.");
      return;
    }
    setBusy("install");
    setError("");
    client.githubCompleteInstall(state, parsedInstallationId).then(result => {
      onProjectChange(result.project_id);
      setInstallation(result.installation);
      setInstallations(current => [...current.filter(item => item.id !== result.installation.id), result.installation]);
      setInstallationRecordId(result.installation.id);
      setRepositories(result.repositories);
      setRepositoryId("");
      setPickerOpen(true);
      setNotice("GitHub installation verified for @" + result.installation.github_login + ". Choose the repository to connect to this project.");
    }).catch(failure => {
      setError(errorMessage(failure));
    }).finally(() => setBusy(""));
  }, [client, onProjectChange]);

  useEffect(() => {
    if (!enabled || !projectId) {
      setBinding(null);
      setTree(null);
      setSelectedPaths([]);
      onBindingChange(null);
      return;
    }
    let alive = true;
    setError("");
    setNotice("");
    setBinding(null);
    setTree(null);
    setSelectedPaths([]);
    onBindingChange(null);
    client.githubRepository(projectId).then(async value => {
      if (!alive) return;
      setBinding(value.repository);
      onBindingChange(value.repository);
      if (value.repository) {
        setInstallationRecordId(value.repository.installation_record_id);
        const result = await client.githubRepositoryTree(projectId);
        if (alive) setTree(result);
      }
    }).catch(failure => {
      if (alive) setError(errorMessage(failure));
    });
    return () => { alive = false; };
  }, [client, enabled, projectId, onBindingChange]);

  const visibleFiles = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (tree?.files ?? []).filter(file => !query || file.path.toLowerCase().includes(query)).slice(0, 120);
  }, [tree, search]);

  async function connectGitHub() {
    if (!projectId || busy) return;
    setBusy("connect");
    setError("");
    setNotice("");
    try {
      const result = await client.githubStart(projectId);
      window.location.assign(safeGitHubRedirect(result.authorization_url, "oauth"));
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy("");
    }
  }

  async function openRepositoryPicker() {
    if (!installationRecordId || busy) return;
    setBusy("repositories");
    setError("");
    try {
      const result = await client.githubRepositories(installationRecordId);
      setRepositories(result.repositories);
      setRepositoryId("");
      setPickerOpen(true);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy("");
    }
  }

  async function bindRepository() {
    if (!projectId || !installationRecordId || !repositoryId || busy) return;
    setBusy("bind");
    setError("");
    try {
      const project = await client.project(projectId);
      const value = await client.githubBindRepository(
        projectId,
        installationRecordId,
        Number(repositoryId),
        project.revision,
      );
      setBinding(value);
      onBindingChange(value);
      setPickerOpen(false);
      setSelectedPaths([]);
      const nextTree = await client.githubRepositoryTree(projectId);
      setTree(nextTree);
      setNotice("Connected " + value.full_name + " on branch " + value.default_branch + ". Repository access is read-only in this phase.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy("");
    }
  }

  async function refreshTree() {
    if (!projectId || busy) return;
    setBusy("refresh");
    setError("");
    try {
      const value = await client.githubRepositoryTree(projectId);
      setTree(value);
      setSelectedPaths([]);
      setNotice("Repository tree refreshed at commit " + value.commit_sha.slice(0, 12) + ".");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy("");
    }
  }

  function togglePath(path: string, checked: boolean) {
    setSelectedPaths(current => {
      if (checked) return current.includes(path) || current.length >= MAX_IMPORT_FILES ? current : [...current, path];
      return current.filter(item => item !== path);
    });
  }

  async function importSelectedFiles() {
    if (!projectId || !selectedPaths.length || busy) return;
    setBusy("import");
    setError("");
    setNotice("");
    try {
      const files: GitHubRepositoryFile[] = [];
      for (const path of selectedPaths) {
        if (!tree?.commit_sha) throw new Error("Refresh the repository tree before importing source files.");
        files.push(await client.githubRepositoryFile(projectId, path, tree.commit_sha));
      }
      await onImportFiles(files);
      setSelectedPaths([]);
      setNotice("Imported " + files.length + " verified repository file snapshot(s) into Fly. They will be attached to the next Agent request.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy("");
    }
  }

  async function disconnectRepository() {
    if (!projectId || busy) return;
    setBusy("disconnect");
    setError("");
    try {
      await client.githubDisconnectRepository(projectId);
      setBinding(null);
      setTree(null);
      setSelectedPaths([]);
      onBindingChange(null);
      setNotice("Repository disconnected from this project. The GitHub installation remains available for other projects.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy("");
    }
  }

  async function revokeInstallation() {
    if (!installationRecordId || busy) return;
    setBusy("revoke");
    setError("");
    try {
      await client.githubDisconnectInstallation(installationRecordId);
      setBinding(null);
      setTree(null);
      setInstallation(null);
      setInstallations(current => current.filter(item => item.id !== installationRecordId));
      setInstallationRecordId("");
      setRepositories([]);
      setPickerOpen(false);
      setConfirmRevoke(false);
      onBindingChange(null);
      setNotice("GitHub authorization revoked. All project bindings using this installation were disconnected.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy("");
    }
  }

  return <section className="rukh-fly-github" aria-label="GitHub repository">
    <div className="rukh-fly-github-heading">
      <div><span>REPOSITORY</span><strong>GitHub</strong></div>
      {binding && <span className="rukh-fly-github-connected">Connected</span>}
    </div>
    {enabled === null && <p className="rukh-fly-github-muted" role="status">Checking GitHub integration…</p>}
    {enabled === false && <p className="rukh-fly-github-muted">GitHub App integration is not configured in this deployment. Fly's local editor remains available.</p>}
    {enabled === true && !projectId && <p className="rukh-fly-github-muted">Select or create a Fly project before connecting a repository.</p>}
    {enabled === true && projectId && !binding && !pickerOpen && installations.length === 0 && <>
      <p className="rukh-fly-github-muted">Connect a GitHub App installation to browse files from a repository you can access.</p>
      <button type="button" className="rukh-fly-github-primary" onClick={() => void connectGitHub()} disabled={Boolean(busy)}>
        {busy === "connect" || busy === "oauth" ? "Connecting…" : "Connect GitHub"}
      </button>
    </>}
    {enabled === true && projectId && !binding && !pickerOpen && installations.length > 0 && <>
      <p className="rukh-fly-github-muted">Choose a verified GitHub App installation to browse its repositories.</p>
      <label className="rukh-fly-github-label">GitHub installation
        <select value={installationRecordId} onChange={event => setInstallationRecordId(event.target.value)} disabled={Boolean(busy)}>
          <option value="">Choose an installation…</option>
          {installations.map(item => <option key={item.id} value={item.id}>{item.account_login} · @{item.github_login}</option>)}
        </select>
      </label>
      <button type="button" className="rukh-fly-github-primary" onClick={() => void openRepositoryPicker()} disabled={Boolean(busy) || !installationRecordId}>
        {busy === "repositories" ? "Loading…" : "Choose repository"}
      </button>
      <button type="button" className="rukh-fly-github-text" onClick={() => void connectGitHub()} disabled={Boolean(busy)}>Add another GitHub installation</button>
    </>}
    {enabled === true && projectId && pickerOpen && <>
      <p className="rukh-fly-github-muted">Installation: <strong>{installation?.account_login ?? installations.find(item => item.id === installationRecordId)?.account_login ?? "Verified GitHub installation"}</strong></p>
      <label className="rukh-fly-github-label">Repository
        <select value={repositoryId} onChange={event => setRepositoryId(event.target.value)} disabled={Boolean(busy)}>
          <option value="">Choose a repository…</option>
          {repositories.map(repo => <option key={repo.id} value={String(repo.id)}>{repo.full_name}{repo.private ? " · private" : ""}</option>)}
        </select>
      </label>
      <div className="rukh-fly-github-actions">
        <button type="button" className="rukh-fly-github-primary" onClick={() => void bindRepository()} disabled={Boolean(busy) || !repositoryId}>
          {busy === "bind" ? "Connecting…" : "Connect repository"}
        </button>
        <button type="button" onClick={() => setPickerOpen(false)} disabled={Boolean(busy)}>Cancel</button>
        <button type="button" onClick={() => void openRepositoryPicker()} disabled={Boolean(busy) || !installationRecordId}>Refresh list</button>
      </div>
    </>}
    {enabled === true && projectId && binding && !pickerOpen && <>
      <div className="rukh-fly-github-repo-name"><strong>{binding.full_name}</strong><small>{binding.default_branch} · {binding.can_write_contents ? "GitHub write permission granted; Fly patch application is not enabled" : "Read-only access"}</small></div>
      <div className="rukh-fly-github-actions">
        <button type="button" onClick={() => void openRepositoryPicker()} disabled={Boolean(busy)}>Change repository</button>
        <button type="button" onClick={() => void refreshTree()} disabled={Boolean(busy)}>{busy === "refresh" ? "Refreshing…" : "Refresh files"}</button>
        <button type="button" onClick={() => void disconnectRepository()} disabled={Boolean(busy)}>Disconnect project</button>
      </div>
      {!binding.can_read_contents && <p className="rukh-fly-github-warning">The App and GitHub user must both have repository read permission.</p>}
      {tree && <>
        <div className="rukh-fly-github-tree-meta"><span>{tree.files.length} source files</span><span>Commit {tree.commit_sha.slice(0, 9)}</span></div>
        {tree.truncated && <p className="rukh-fly-github-muted">The repository tree is truncated to the configured safe file limit.</p>}
        <input aria-label="Search repository files" value={search} onChange={event => setSearch(event.target.value)} placeholder="Filter source files…" disabled={Boolean(busy)} />
        <ul className="rukh-fly-github-file-list">
          {visibleFiles.map(file => <li key={file.path}>
            <label title={file.path}>
              <input type="checkbox" checked={selectedPaths.includes(file.path)} onChange={event => togglePath(file.path, event.target.checked)} disabled={Boolean(busy) || (!selectedPaths.includes(file.path) && selectedPaths.length >= MAX_IMPORT_FILES)} />
              <span>{file.path}</span><small>{Math.ceil(file.size / 1024)} KB</small>
            </label>
          </li>)}
        </ul>
        <button type="button" className="rukh-fly-github-primary" onClick={() => void importSelectedFiles()} disabled={Boolean(busy) || !selectedPaths.length}>
          {busy === "import" ? "Importing…" : "Add " + selectedPaths.length + " file(s) to Fly"}
        </button>
        <p className="rukh-fly-github-muted">Up to {MAX_IMPORT_FILES} selected text files are added to the Fly workspace. Rukh Files creates owner-private snapshots before the Agent receives them.</p>
      </>}
      {confirmRevoke ? <div className="rukh-fly-github-revoke">
        <p>Revoking this installation disconnects every Fly project using the same GitHub installation.</p>
        <button type="button" onClick={() => void revokeInstallation()} disabled={Boolean(busy)}>{busy === "revoke" ? "Revoking…" : "Confirm revoke access"}</button>
        <button type="button" onClick={() => setConfirmRevoke(false)} disabled={Boolean(busy)}>Cancel</button>
      </div> : <button type="button" className="rukh-fly-github-text" onClick={() => setConfirmRevoke(true)} disabled={Boolean(busy)}>Revoke GitHub account access</button>}
    </>}
    {error && <p className="rukh-fly-github-error" role="alert">{error}</p>}
    {notice && <p className="rukh-fly-github-notice" role="status">{notice}</p>}
  </section>;
}
