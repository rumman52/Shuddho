import React from "react";
import { createRoot } from "react-dom/client";
import "@rukh/design-system/tokens.css";
import "../../web-editor/src/styles.css";
import "./styles.css";
import App from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("Rukh Editor root element is missing.");
createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
