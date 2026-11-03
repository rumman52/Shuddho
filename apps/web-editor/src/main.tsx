import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";
import "../../editor/src/styles.css";
import WorkspaceShell from "./WorkspaceShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { initializeRukhTheme } from "./lib/theme";

initializeRukhTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <WorkspaceShell />
    </ErrorBoundary>
  </React.StrictMode>
);
