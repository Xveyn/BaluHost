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

// --- Mobile Devices API ---
export interface MobileRegistrationToken {
  token: string;
  server_url: string;
  expires_at: string;
  qr_code: string;
  vpn_config?: string;
  device_token_validity_days: number;
}

export interface MobileDevice {
  id: string;
  user_id: number;  // Changed from string to number
  username?: string; // Nur für Admin sichtbar
  device_name: string;
  device_type: string;
  device_model: string | null;
  os_version: string | null;
  app_version: string | null;
  is_active: boolean;
  last_sync: string | null;
  last_seen?: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export async function generateMobileToken(
  includeVpn: boolean = false, 
  deviceName: string = 'Mobile Device',
  tokenValidityDays: number = 90
): Promise<MobileRegistrationToken> {
  const res = await apiClient.post('/api/mobile/token/generate', null, {
    params: { 
      include_vpn: includeVpn, 
      device_name: deviceName,
      token_validity_days: tokenValidityDays
    }
  });
  return res.data;
}

export async function getMobileDevices(): Promise<MobileDevice[]> {
  // Add cache-busting timestamp to prevent stale data
  const res = await apiClient.get('/api/mobile/devices', {
    params: { _t: Date.now() }
  });
  return res.data;
}

export async function deleteMobileDevice(deviceId: string): Promise<void> {
  await apiClient.delete(`/api/mobile/devices/${deviceId}`);
}

export interface ExpirationNotification {
  id: string;
  notification_type: string;
  sent_at: string;
  success: boolean;
  error_message: string | null;
  device_expires_at: string | null;
}

export async function getDeviceNotifications(deviceId: string, limit: number = 10): Promise<ExpirationNotification[]> {
  const res = await apiClient.get(`/api/mobile/devices/${deviceId}/notifications`, {
    params: { limit }
  });
  return res.data;
}

// --- Duplicate Check API ---
export interface ExistingFileInfo {
  filename: string;
  size_bytes: number;
  modified_at: string;
  checksum: string | null;
}

export async function checkFilesExist(
  filenames: string[],
  targetPath: string,
): Promise<{ duplicates: ExistingFileInfo[] }> {
  const res = await apiClient.post('/api/files/check-exists', {
    filenames,
    target_path: targetPath,
  });
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
  return config;
});

// --- Admin DB API (read-only, admin-only) ---
export interface AdminTableSchemaField {
  name: string;
  type: string;
  nullable: boolean;
  default?: any;
}

export interface AdminTableSchemaResponse {
  table: string;
  columns: AdminTableSchemaField[];
}

export interface AdminTableRowsResponse {
  table: string;
  page: number;
  page_size: number;
  rows: Array<Record<string, any>>;
  total?: number | null;
  sort_by?: string | null;
  sort_order?: string | null;
}

export interface AdminTableCategoriesResponse {
  categories: Record<string, string[]>;
}

export interface ColumnFilter {
  op: 'contains' | 'eq' | 'gt' | 'lt' | 'gte' | 'lte' | 'between' | 'is_null' | 'is_true' | 'is_false';
  value?: string | number;
  from?: string | number;
  to?: string | number;
}

export type ColumnFilters = Record<string, ColumnFilter>;

export async function getAdminTables(): Promise<string[]> {
  const res = await apiClient.get('/api/admin/db/tables');
  return res.data.tables;
}

export async function getAdminTableCategories(): Promise<AdminTableCategoriesResponse> {
  const res = await apiClient.get('/api/admin/db/tables/categories');
  return res.data;
}

export async function getAdminTableSchema(table: string): Promise<AdminTableSchemaResponse> {
  const res = await apiClient.get(`/api/admin/db/table/${encodeURIComponent(table)}/schema`);
  return res.data;
}

export async function getAdminTableRows(
  table: string,
  page: number = 1,
  page_size: number = 50,
  fields?: string[],
  q?: string,
  sort_by?: string,
  sort_order?: string,
  filters?: ColumnFilters
): Promise<AdminTableRowsResponse> {
  const params: any = { page, page_size };
  if (fields && fields.length) params.fields = fields.join(',');
  if (q) params.q = q;
  if (sort_by) params.sort_by = sort_by;
  if (sort_order) params.sort_order = sort_order;
  if (filters && Object.keys(filters).length > 0) params.filters = JSON.stringify(filters);
  const res = await apiClient.get(`/api/admin/db/table/${encodeURIComponent(table)}`, { params });
  return res.data;
}

// --- Database Health & Info ---
export interface DatabaseHealthResponse {
  is_healthy: boolean;
  connection_status: string;
  database_type: string;
  integrity_check?: string;
  pool_size?: number;
  pool_checked_in?: number;
  pool_checked_out?: number;
  pool_overflow?: number;
}

export interface TableSizeInfo {
  table_name: string;
  row_count: number;
  estimated_size_bytes: number;
}

export interface DatabaseInfoResponse {
  database_type: string;
  total_size_bytes: number;
  tables: TableSizeInfo[];
}

export async function getDatabaseHealth(): Promise<DatabaseHealthResponse> {
  const res = await apiClient.get('/api/admin/db/health');
  return res.data;
}

export async function getDatabaseInfo(): Promise<DatabaseInfoResponse> {
  const res = await apiClient.get('/api/admin/db/info');
  return res.data;
}

export function extractErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((e: any) => e.msg ?? String(e)).join('; ');
  }
  return fallback;
}

