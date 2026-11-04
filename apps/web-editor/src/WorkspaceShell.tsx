import { lazy, Suspense } from "react";
import RukhHome from "./RukhHome";
import "./rukh-home.css";
import { getWorkspaceAppRoute } from "./appRoutes.mjs";
import "./coworker/workspace.css";
import "../../coworker/src/styles.css";
import "../../../packages/design-system/src/tokens.css";

const CoworkerPreview = lazy(() => import("./coworker/CoworkerPreview"));
const CoworkerStandalone = lazy(() => import("../../coworker/src/App"));
const EditorStandalone = lazy(() => import("../../editor/src/App"));

export default function WorkspaceShell() {
  const coworkerEnabled = import.meta.env.VITE_COWORKER_ENABLED === "true";
  const route = getWorkspaceAppRoute(
    typeof window === "undefined" ? "/" : window.location.pathname,
    coworkerEnabled,
  );

  if (route === "coworker-preview") {
    return <Suspense fallback={<p className="cw-loading" role="status">Opening your draft workspace…</p>}><CoworkerPreview /></Suspense>;
  }

  if (route === "coworker") {
    return (
      <Suspense fallback={<p className="cw-loading" role="status">Opening Rukh AI Coworker…</p>}>
        <CoworkerStandalone />
      </Suspense>
    );
  }

  if (route === "editor") {
    return (
      <Suspense fallback={<p className="cw-loading" role="status">Opening Rukh AI Web Editor…</p>}>
        <EditorStandalone />
      </Suspense>
    );
  }

  return <RukhHome coworkerEnabled={coworkerEnabled} />;
}
