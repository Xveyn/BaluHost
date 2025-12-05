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
// --- File Permissions API ---
export async function getFilePermissions(path: string) {
  // Memoized GET: Permissions werden für 60s gecached
  return memoizedApiRequest(`/api/files/permissions`, { path });
}

export async function setFilePermissions(data: {
  path: string;
  owner_id: number;
  rules: Array<{
    user_id: number;
    can_view: boolean;
    can_edit: boolean;
    can_delete: boolean;
  }>;
}) {
  const res = await apiClient.put(`/api/files/permissions`, data);
  return res.data;
}
import axios from 'axios';

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
  // Debug: Log the final request URL
  console.log('[API] Request:', config.method?.toUpperCase(), config.url, 'baseURL:', config.baseURL);
  return config;
});
