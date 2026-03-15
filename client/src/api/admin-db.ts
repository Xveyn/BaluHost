/**
 * API client for admin database inspection (read-only, admin-only)
 */

import { apiClient } from '../lib/api';

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
