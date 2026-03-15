import axios from 'axios';

export const API_VERSION = '1';

// For local development, we DON'T set a baseURL so axios uses relative URLs
// which trigger the Vite proxy. Only set baseURL for production builds.
const isDevelopment = import.meta.env.DEV;

export const API_BASE_URL = isDevelopment ? '' : (import.meta.env.VITE_API_BASE_URL || '');

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
// In development: NO baseURL -> uses relative URLs -> triggers Vite proxy
// In production: uses VITE_API_BASE_URL from environment
export const apiClient = axios.create({
  baseURL: isDevelopment ? undefined : API_BASE_URL,
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

// --- Memoized API Request Utility ---
type CacheEntry = { data: any; expires: number };
export const apiCache = new Map<string, CacheEntry>();
const DEFAULT_TTL = 60 * 1000; // 60 Sekunden

export async function memoizedApiRequest<T = any>(url: string, params?: any, ttl: number = DEFAULT_TTL): Promise<T> {
  const key = url + JSON.stringify(params || {});
  const now = Date.now();
  const cached = apiCache.get(key);
  if (cached && cached.expires > now) {
    return cached.data;
  }
  const res = await apiClient.get(url, { params });
  apiCache.set(key, { data: res.data, expires: now + ttl });
  return res.data;
}

export function extractErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((e: any) => e.msg ?? String(e)).join('; ');
  }
  return fallback;
}
