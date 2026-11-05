import { useEffect, useState, type ReactNode } from "react";
import { CoworkerClient, type ConnectedAccount } from "./client";
import NavigationIcon from "./WorkspaceNavigationIcon";
const catalog = [
  { name: "Gmail", provider: "google", capability: "email", icon: "file-text", description: "Prepare emails for your approval." },
  { name: "Google Calendar", provider: "google", capability: "calendar", icon: "calendar", description: "Prepare events and review their details." },
  { name: "Google Drive", provider: "google", capability: "drive", icon: "folder", description: "Share supported documents after review." },
  { name: "Microsoft 365", provider: "microsoft", capability: "email", icon: "grid", description: "Connect supported Outlook and calendar actions." },
  { name: "LinkedIn", provider: "linkedin", capability: "social", icon: "globe", description: "Prepare posts for explicit approval." },
];
export default function PluginsWorkspace({ client, children }: { client: CoworkerClient; children: (onConnectionsChanged: (value: ConnectedAccount[]) => void) => ReactNode }) {
  const [connections, setConnections] = useState<ConnectedAccount[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [socialEnabled, setSocialEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    client.connections(controller.signal).then(value => { if (!controller.signal.aborted) { setConnections(value.connections); setEnabled(value.enabled); setSocialEnabled(value.social_publishing_enabled); } })
      .catch(error => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Connections could not be loaded."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [client]);
  return <section className="rukh-designed-page" aria-label="Plugins"><header className="rukh-page-heading"><div><h1>Connect the tools you work with.</h1><p>Choose what Rukh can access. Review important actions before they happen.</p></div></header>
    {error && <p className="cw-error" role="alert">{error}</p>}
    <label className="rukh-page-search"><NavigationIcon name="search" /><input type="search" aria-label="Search plugins" placeholder="Search plugins" value={search} onChange={event => setSearch(event.target.value)} /></label>
    {loading && <p role="status">Loading connections…</p>}
    <div className="rukh-project-grid">{catalog.filter(item => item.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map(item => {
      const connected = connections.some(value => value.provider === item.provider && value.capability === item.capability && value.active);
      const available = enabled && (item.provider !== "microsoft" || import.meta.env.VITE_MICROSOFT_ACTIONS_ENABLED === "true") && (item.provider !== "linkedin" || socialEnabled);
      return <button key={item.name} className="rukh-project-card" onClick={() => setSelected(item.name)}><span className="rukh-welcome-icon"><NavigationIcon name={item.icon} /></span><strong>{item.name}</strong><p>{item.description}</p><small>{loading ? "Checking…" : error ? "Status unavailable" : connected ? "Connected" : available ? "Not connected" : "Unavailable in this workspace"}</small></button>;
    })}</div>
    {selected && <section className="rukh-plugin-detail"><h2>{selected}</h2><p>Use the connection controls below to review permissions and connect or disconnect your account. A connection alone does not approve external actions.</p><button className="cw-text-button" onClick={() => setSelected("")}>Close details</button></section>}
    <details className="rukh-plugin-management" open={Boolean(selected)}><summary>Connections, permissions &amp; approvals</summary>{children(setConnections)}</details>
  </section>;
}
