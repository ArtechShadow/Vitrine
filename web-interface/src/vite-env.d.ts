/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PREVIEW_MODE?: string;
  readonly VITE_DEMO_SPLAT_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}