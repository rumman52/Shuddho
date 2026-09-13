import { lazy, Suspense, useState } from "react";
import App from "./App";
import "./coworker/workspace.css";

const Coworker = lazy(() => import("./coworker/CoworkerGate"));

export default function WorkspaceShell() {
  const [active, setActive] = useState<"writing" | "coworker">(() => {
    if (typeof window === "undefined") return "writing";
    if (window.location.hash.includes("type=recovery") || new URLSearchParams(window.location.search).has("code")) return "coworker";
    try { return sessionStorage.getItem("shuddho:workspace:tab") === "coworker" ? "coworker" : "writing"; } catch { return "writing"; }
  });
  const [opened, setOpened] = useState(active === "coworker");
  const select = (tab: "writing" | "coworker") => {
    setActive(tab);
    if (tab === "coworker") setOpened(true);
    try { sessionStorage.setItem("shuddho:workspace:tab", tab); } catch { /* Navigation works without storage. */ }
  };
  if (import.meta.env.VITE_COWORKER_ENABLED !== "true") return <App />;
  return <div className="workspace-shell">
    <nav className="workspace-nav" aria-label="Shuddho workspace">
      <span className="workspace-wordmark">shuddho<span> / workspace</span></span>
      <div className="workspace-tabs">
        <button type="button" aria-pressed={active === "writing"} onClick={() => select("writing")}>Writing assistant <small>Free</small></button>
        <button type="button" aria-pressed={active === "coworker"} onClick={() => select("coworker")}>AI coworker</button>
      </div>
    </nav>
    <div className="workspace-writing" hidden={active !== "writing"}><App /></div>
    {opened && <div className="workspace-coworker" hidden={active !== "coworker"}>
      <Suspense fallback={<p className="cw-loading" role="status">Opening your coworker…</p>}><Coworker /></Suspense>
    </div>}
  </div>;
}
