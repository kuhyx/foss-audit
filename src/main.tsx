import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@kuhyx/web-ui/tokens.css";

import { App } from "./app.tsx";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/controls.css";
import "./styles/summary.css";
import "./styles/table.css";
import "./styles/panel.css";

const root = document.querySelector("#root");
if (root !== null) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
