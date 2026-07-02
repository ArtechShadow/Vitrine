/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional sample splat URL for the viewer empty-state. */
  readonly VITE_DEMO_SPLAT_URL?: string;
  /** Public base path the built assets are served from (default /static/spa/). */
  readonly VITE_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
