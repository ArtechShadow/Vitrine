import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The built bundle is baked into src/web/static/spa/ at image-build time and
// served same-origin by the loopback Flask app. Assets therefore live under
// Flask's static mount (/static/spa/), while client routes (/, /library,
// /create, /scenes/:id, /viewer, /pipeline) are handled by the SPA catch-all.
// Override with VITE_BASE only if the static mount path changes.
const DEFAULT_BASE = "/static/spa/";

// Loopback-only backend. The dev server proxies API + SSE traffic to the
// Flask app bound on 127.0.0.1:7860 (NEVER 0.0.0.0). Reached externally only
// via `ssh -N -L 7860:localhost:7860`.
const DEFAULT_BACKEND = "http://127.0.0.1:7860";

export default defineConfig(({ mode }) => {
  // envDir "." resolves to the config directory; avoids a hard @types/node dep.
  const env = loadEnv(mode, ".", "VITE_");
  const backend = env.VITE_DEV_BACKEND || DEFAULT_BACKEND;

  return {
    base: env.VITE_BASE || DEFAULT_BASE,
    plugins: [react()],
    build: {
      // Deterministic, offline-signable output; no runtime CDN fetches.
      target: "es2022",
      sourcemap: false,
      chunkSizeWarningLimit: 2200, // gaussian-splats-3d + three are large by nature
    },
    server: {
      // Dev server is a developer convenience only. Bind loopback to mirror the
      // production posture and keep the API surface off the network.
      host: "127.0.0.1",
      port: 5173,
      strictPort: false,
      proxy: {
        "/api": { target: backend, changeOrigin: true },
        // Canonical progress channel is Server-Sent Events; disable buffering
        // so the proxy streams events through immediately.
        "/stream": { target: backend, changeOrigin: true, ws: false },
      },
    },
  };
});
