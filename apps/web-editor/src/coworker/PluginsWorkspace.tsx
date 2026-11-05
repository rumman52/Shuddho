import { useEffect, useState, type ReactNode } from "react";
import { CoworkerClient, type ConnectedAccount } from "./client";
import NavigationIcon from "./WorkspaceNavigationIcon";
const catalog = [
  { name: "Google Drive", provider: "google", capability: "drive", icon: "folder", description: "Find and work with your documents.", supported: true, featured: true },
  { name: "GitHub", provider: "github", capability: "code", icon: "terminal", description: "Bring repositories into your work.", supported: false, featured: true },
  { name: "Google Calendar", provider: "google", capability: "calendar", icon: "calendar", description: "Make room for what matters.", supported: true, featured: true },
  { name: "Gmail", provider: "google", capability: "email", icon: "file-text", description: "Draft and review your messages.", supported: true, featured: true },
  { name: "Notion", provider: "notion", capability: "knowledge", icon: "file-text", description: "Keep knowledge close to the work.", supported: false, featured: true },
  { name: "Slack", provider: "slack", capability: "messaging", icon: "chat", description: "Turn team updates into next steps.", supported: false, featured: true },
  { name: "Microsoft 365", provider: "microsoft", capability: "email", icon: "grid", description: "Connect supported Outlook and calendar actions.", supported: true, featured: false },
  { name: "LinkedIn", provider: "linkedin", capability: "social", icon: "globe", description: "Prepare posts for explicit approval.", supported: true, featured: false },
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
  return <section className="rukh-designed-page" aria-label="Plugins"><header className="rukh-page-heading"><div><h1>Plugins</h1><p>Connect the tools you already use. You stay in control.</p></div></header>
    {error && <p className="cw-error" role="alert">{error}</p>}
    <label className="rukh-page-search"><NavigationIcon name="search" /><input type="search" aria-label="Search plugins" placeholder="Search plugins…" value={search} onChange={event => setSearch(event.target.value)} /></label>
    {loading && <p role="status">Loading connections…</p>}
    {(() => {
      const filtered = catalog.filter(item => item.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
      const primary = search ? filtered : filtered.filter(item => item.featured);
      const additional = search ? [] : filtered.filter(item => !item.featured);
      const card = (item: typeof catalog[number]) => {
        const connected = connections.some(value => value.provider === item.provider && value.capability === item.capability && value.active);
        const available = item.supported && enabled && (item.provider !== "microsoft" || import.meta.env.VITE_MICROSOFT_ACTIONS_ENABLED === "true") && (item.provider !== "linkedin" || socialEnabled);
        const status = !item.supported ? "Coming soon" : loading ? "Checking…" : error ? "Status unavailable" : connected ? "Connected" : available ? "Not connected" : "Unavailable in this workspace";
        return <button type="button" key={item.name} className="rukh-project-card" onClick={() => setSelected(item.name)}><span className="rukh-welcome-icon"><NavigationIcon name={item.icon} /></span><strong>{item.name}</strong><p>{item.description}</p><small>{status}</small></button>;
      };
      return <>
        <div className="rukh-project-grid">{primary.map(card)}</div>
        {additional.length > 0 && <details className="rukh-plugin-additional"><summary>More integrations</summary><div className="rukh-project-grid">{additional.map(card)}</div></details>}
      </>;
    })()}
    {selected && <section className="rukh-plugin-detail"><h2>{selected}</h2><p>{catalog.find(item => item.name === selected)?.supported ? "Use the connection controls below to review permissions and connect or disconnect your account. A connection alone does not approve external actions." : "This connector is shown in the approved design but is not currently enabled by a provider integration. No account access is granted."}</p><button className="cw-text-button" type="button" onClick={() => setSelected("")}>Close details</button></section>}
    <details className="rukh-plugin-management"><summary>Connections, permissions &amp; approvals</summary>{children(setConnections)}</details>
  </section>;
}
