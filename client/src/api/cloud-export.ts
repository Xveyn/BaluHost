/**
 * API client for cloud export functionality
 */

import { apiClient } from '../lib/api';

// ─── Types ──────────────────────────────────────────────────

export interface CloudExportRequest {
  connection_id: number;
  source_path: string;
  cloud_folder?: string;
  link_type?: 'view' | 'edit';
  expires_at?: string | null;
}

export interface CloudExportJob {
  id: number;
  user_id: number;
  connection_id: number;
  source_path: string;
  file_name: string;
  is_directory: boolean;
  file_size_bytes: number | null;
  cloud_folder: string;
  cloud_path: string | null;
  share_link: string | null;
  link_type: string;
  status: 'pending' | 'uploading' | 'creating_link' | 'ready' | 'failed' | 'revoked';
  progress_bytes: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  expires_at: string | null;
}

export interface CloudExportStatistics {
  total_exports: number;
  active_exports: number;
  failed_exports: number;
  total_upload_bytes: number;
}

export interface CheckScopeResponse {
  has_export_scope: boolean;
  provider: string;
}

// ─── API Functions ──────────────────────────────────────────

export async function startCloudExport(data: CloudExportRequest): Promise<CloudExportJob> {
  const resp = await apiClient.post('/api/cloud-export/', data);
  return resp.data;
}

export async function listCloudExports(limit = 50): Promise<CloudExportJob[]> {
  const resp = await apiClient.get('/api/cloud-export/jobs', { params: { limit } });
  return resp.data;
}

export async function getCloudExportStatus(jobId: number): Promise<CloudExportJob> {
  const resp = await apiClient.get(`/api/cloud-export/jobs/${jobId}`);
  return resp.data;
}

export async function revokeCloudExport(jobId: number): Promise<void> {
  await apiClient.post(`/api/cloud-export/jobs/${jobId}/revoke`);
}

export async function retryCloudExport(jobId: number): Promise<CloudExportJob> {
  const resp = await apiClient.post(`/api/cloud-export/jobs/${jobId}/retry`);
  return resp.data;
}

export async function getCloudExportStatistics(): Promise<CloudExportStatistics> {
  const resp = await apiClient.get('/api/cloud-export/statistics');
  return resp.data;
}

export async function checkConnectionScope(connectionId: number): Promise<CheckScopeResponse> {
  const resp = await apiClient.post('/api/cloud-export/check-scope', {
    connection_id: connectionId,
  });
  return resp.data;
}
