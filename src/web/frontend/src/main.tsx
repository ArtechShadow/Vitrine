import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Root element #root not found");

createRoot(rootEl).render(
  <StrictMode>
    {/* Served same-origin at the site root by the loopback Flask app; assets
        live under the static mount (vite `base`). basename stays "/". */}
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
