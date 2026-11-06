import NavigationIcon from "./WorkspaceNavigationIcon";
import type { CoworkerView } from "./client";
import { coworkerNavigation } from "../../../coworker/src/navigation.mjs";

export default function WorkspaceNavigation({ active, onNavigate, editorHref = "/editor", writingHref = "/writing" }: {
  active: CoworkerView | "editor" | "writing";
  onNavigate: (view: CoworkerView) => void;
  editorHref?: string;
  writingHref?: string;
}) {
  function item(view: CoworkerView, label: string, icon: string) {
    return <button key={view} type="button" className={"rukh-design-nav-link" + (active === view ? " is-active" : "")} aria-current={active === view ? "page" : undefined} onClick={() => onNavigate(view)}><NavigationIcon name={icon} />{label}</button>;
  }
  return <>
    <nav aria-label="Primary workspace navigation">
      {item("conversations", "Coworker", "chat")}
      <a href="/fly" className={"rukh-design-nav-link" + (active === "sandbox" ? " is-active" : "")} aria-current={active === "sandbox" ? "page" : undefined}><NavigationIcon name="terminal" />Fly</a>
      <a href={editorHref} className={"rukh-design-nav-link" + (active === "editor" ? " is-active" : "")} aria-current={active === "editor" ? "page" : undefined}><NavigationIcon name="layout" />Web Editor</a>
      <a href={writingHref} className={"rukh-design-nav-link" + (active === "writing" ? " is-active" : "")} aria-current={active === "writing" ? "page" : undefined}><NavigationIcon name="file-text" />Writing Assistant</a>
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
      <nav aria-label="Additional tools">{coworkerNavigation.filter(value => ["drafts", "agent", "browser", "transactions", "negotiations"].includes(value.view)).map(value => item(value.view as CoworkerView, value.label, value.icon))}</nav>
    </details>
  </>;
}
