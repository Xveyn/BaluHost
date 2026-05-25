/**
 * Ambient global injected by the Tauri Companion shell before the React
 * bundle loads. When present, it overrides the default API base URL so
 * HTTP requests flow through the Tauri Rust proxy on 127.0.0.1 instead
 * of the regular network path.
 *
 * Set by the Tauri shell via a <script> tag injected into index.html
 * before the bundle executes. Not set in the regular Web build, so
 * browsers fall back to the existing dev/prod resolution.
 */
declare global {
  interface Window {
    __BALU_API_BASE__?: string;
  }
}

export {};
