import React from "react";
import ReactDOM from "react-dom/client";
import WorkspaceShell from "./WorkspaceShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "./styles.css";
import { initializeRukhTheme } from "./lib/theme";

initializeRukhTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <WorkspaceShell />
    </ErrorBoundary>
  </React.StrictMode>
);
