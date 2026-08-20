/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_WS_URL?: string;
  readonly VITE_BOT_USERNAME?: string;
  readonly VITE_TONCONNECT_MANIFEST?: string;
  /** Signed initData fixture, so the app is usable in a plain browser tab. */
  readonly VITE_DEV_INIT_DATA?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
