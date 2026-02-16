/// <reference types="vite/client" />

declare const __BUILD_TYPE__: 'dev' | 'release';
declare const __GIT_BRANCH__: string;
declare const __GIT_COMMIT__: string;

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_BUILD_TYPE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
