import { lazy, Suspense, useState } from "react";
import App from "./App";
import { getStandaloneAppRoute } from "./appRoutes.mjs";
import "./coworker/workspace.css";
import "../../coworker/src/styles.css";
import "../../../packages/design-system/src/tokens.css";
import { hasPendingGoogleCallback } from "./coworker/googleCallback";
import { hasPendingMicrosoftCallback } from "./coworker/microsoftCallback";
import { hasPendingLinkedInCallback } from "./coworker/linkedinCallback";
import { requestedNotificationView } from "./coworker/pushNavigation";

const Coworker = lazy(() => import("./coworker/CoworkerGate"));
const CoworkerStandalone = lazy(() => import("../../coworker/src/App"));
const EditorStandalone = lazy(() => import("../../editor/src/App"));

export default function WorkspaceShell() {
  const route = typeof window === "undefined" ? "default" : getStandaloneAppRoute(window.location.pathname);
  const [active, setActive] = useState<"writing" | "coworker">(() => {
    if (typeof window === "undefined") return "writing";
    if (requestedNotificationView(window.location.search) || hasPendingGoogleCallback() || hasPendingMicrosoftCallback() || hasPendingLinkedInCallback() || window.location.hash.includes("type=recovery") || new URLSearchParams(window.location.search).has("code")) return "coworker";
    try { return sessionStorage.getItem("shuddho:workspace:tab") === "coworker" ? "coworker" : "writing"; } catch { return "writing"; }
  });
  const [opened, setOpened] = useState(active === "coworker");
  const select = (tab: "writing" | "coworker") => {
    setActive(tab);
    if (tab === "coworker") setOpened(true);
    try { sessionStorage.setItem("shuddho:workspace:tab", tab); } catch { /* Navigation works without storage. */ }
  };

  if (route === "coworker") return <Suspense fallback={<p className="cw-loading" role="status">Opening Rukh AI Coworker…</p>}><CoworkerStandalone /></Suspense>;
  if (route === "editor" || import.meta.env.VITE_COWORKER_ENABLED !== "true") return <Suspense fallback={<p className="cw-loading" role="status">Opening Rukh Editor…</p>}><EditorStandalone /></Suspense>;

  return <div className="workspace-shell">
    <nav className="workspace-nav" aria-label="Rukh AI workspace">
      <span className="workspace-wordmark">rukh<span> / workspace</span></span>
      <div className="workspace-tabs">
        <button type="button" aria-pressed={active === "writing"} onClick={() => select("writing")}>Editor <small>Writing</small></button>
        <button type="button" aria-pressed={active === "coworker"} onClick={() => select("coworker")}>Coworker</button>
      </div>
    </nav>
    <div className="workspace-writing" hidden={active !== "writing"}><App /></div>
    {opened && <div className="workspace-coworker" hidden={active !== "coworker"}>
      <Suspense fallback={<p className="cw-loading" role="status">Opening your coworker…</p>}><Coworker /></Suspense>
    </div>}
  </div>;
}
