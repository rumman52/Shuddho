import React from "react";
import { createRoot } from "react-dom/client";
import "@rukh/design-system/tokens.css";
import "../../web-editor/src/coworker/workspace.css";
import "./styles.css";
import App from "./App";
import { initializeRukhTheme } from "../../web-editor/src/lib/theme";

initializeRukhTheme();

const root = document.getElementById("root");
if (!root) throw new Error("Rukh AI Coworker root element is missing.");
createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
