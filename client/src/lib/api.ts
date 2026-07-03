import axios from 'axios';

export const API_VERSION = '1';

// For local development, we DON'T set a baseURL so axios uses relative URLs
// which trigger the Vite proxy. Only set baseURL for production builds.
const isDevelopment = import.meta.env.DEV;

// Tauri Companion shell injects window.__BALU_API_BASE__ before the bundle
// loads, pointing at its local HTTP-to-UDS proxy (e.g.,
// "http://127.0.0.1:<port>/api"). When present it overrides dev/prod
// resolution so all requests flow through the Tauri Rust proxy. Read
// synchronously at module load — not set in regular Web builds.
const tauriApiBase =
  typeof window !== 'undefined' && window.__BALU_API_BASE__
    ? window.__BALU_API_BASE__
    : undefined;

/** True when running inside the Tauri Companion shell (local channel). Read
 *  synchronously at module load; safe to use pre-auth on the Login screen. */
export const isTauri = Boolean(tauriApiBase);

export const API_BASE_URL =
  tauriApiBase ?? (isDevelopment ? '' : (import.meta.env.VITE_API_BASE_URL || ''));

export const buildApiUrl = (path: string): string => {
  if (!API_BASE_URL) {
    return path.startsWith('/') ? path : `/${path}`;
  }
  if (!path.startsWith('/')) {
    return `${API_BASE_URL}/${path}`
  }
  return `${API_BASE_URL}${path}`
}

// Create axios instance with default config
// In Tauri: uses window.__BALU_API_BASE__ injected by the Rust shell
// In development: NO baseURL -> uses relative URLs -> triggers Vite proxy
// In production: uses VITE_API_BASE_URL from environment
export const apiClient = axios.create({
  baseURL: tauriApiBase ?? (isDevelopment ? undefined : API_BASE_URL),
  headers: {
    'Content-Type': 'application/json'
  }
});

// Add auth token interceptor
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/** Dispatch auth:expired event — AuthContext listens and logs out */
export function fireAuthExpired(): void {
  localStorage.removeItem('token');
  window.dispatchEvent(new CustomEvent('auth:expired'));
}

// Handle 401 responses — signal auth expiration
// Check server API version compatibility via X-API-Min-Version header
apiClient.interceptors.response.use(
  (response) => {
    const minVersion = response.headers?.['x-api-min-version'];
    if (minVersion && parseInt(minVersion, 10) > parseInt(API_VERSION, 10)) {
      window.dispatchEvent(new CustomEvent('api:upgrade-required', {
        detail: { serverMin: minVersion, clientVersion: API_VERSION },
      }));
    }
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      fireAuthExpired();
    }
    return Promise.reject(error);
  }
);

export function extractErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((e: any) => e.msg ?? String(e)).join('; ');
  }
  return fallback;
}
