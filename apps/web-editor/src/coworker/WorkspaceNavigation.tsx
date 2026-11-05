import NavigationIcon from "./WorkspaceNavigationIcon";
import type { CoworkerView } from "./client";
import { coworkerNavigation } from "../../../coworker/src/navigation.mjs";

export default function WorkspaceNavigation({ active, onNavigate, editorHref = "/editor" }: {
  active: CoworkerView | "editor"; onNavigate: (view: CoworkerView) => void; editorHref?: string;
}) {
  function item(view: CoworkerView, label: string, icon: string) {
    return <button key={view} type="button" className={"rukh-design-nav-link" + (active === view ? " is-active" : "")} aria-current={active === view ? "page" : undefined} onClick={() => onNavigate(view)}><NavigationIcon name={icon} />{label}</button>;
  }
  return <>
    <nav aria-label="Primary workspace navigation">
      {item("conversations", "Coworker", "chat")}
      <a href={editorHref} className={"rukh-design-nav-link" + (active === "editor" ? " is-active" : "")} aria-current={active === "editor" ? "page" : undefined}><NavigationIcon name="layout" />Web Editor</a>
      {item("projects", "Projects", "folder")}
      {item("actions", "Plugins", "grid")}
    </nav>
    <nav className="rukh-design-workspace-links" aria-label="Workspace tools">
      <span className="rukh-design-section-label">WORKSPACE</span>
      {item("library", "Files", "file-text")}
      {item("goals", "Goals", "target")}
      {item("automations", "Automations", "clock")}
    </nav>
    <button type="button" className="rukh-design-settings" onClick={() => onNavigate("settings")}>Settings</button>
    <details className="rukh-design-more-tools">
      <summary>More tools</summary>
      <nav aria-label="Additional tools">{coworkerNavigation.filter(value => ["drafts", "agent", "browser", "sandbox", "transactions", "negotiations"].includes(value.view)).map(value => item(value.view as CoworkerView, value.label, value.icon))}</nav>
    </details>
  </>;
}
