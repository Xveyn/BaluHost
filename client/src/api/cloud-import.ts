/**
 * API client for Cloud Import
 *
 * Manages cloud provider connections (Google Drive, OneDrive, iCloud)
 * and import/sync jobs.
 */

import { apiClient } from '../lib/api';
import type { AxiosError } from 'axios';

// Provider types
export type CloudProvider = 'google_drive' | 'onedrive' | 'icloud';

export const PROVIDER_LABELS: Record<CloudProvider, string> = {
  google_drive: 'Google Drive',
  onedrive: 'OneDrive',
  icloud: 'iCloud',
};

// Provider status from backend
export interface ProviderInfo {
  configured: boolean;
  label: string;
  auth_type: 'oauth' | 'credentials';
}

export interface ProvidersStatus {
  is_dev_mode: boolean;
  providers: Record<CloudProvider, ProviderInfo>;
}

/** Extract a user-friendly error message from an Axios error or generic error. */
export function extractErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const axErr = err as AxiosError<{ detail?: string }>;
    if (axErr.response?.data?.detail) {
      return axErr.response.data.detail;
    }
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

// Response types
export interface CloudConnection {
  id: number;
  provider: CloudProvider;
  display_name: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface CloudFile {
  name: string;
  path: string;
  is_directory: boolean;
  size_bytes: number | null;
  modified_at: string | null;
}

export interface CloudImportJob {
  id: number;
  connection_id: number;
  source_path: string;
  destination_path: string;
  job_type: 'import' | 'sync';
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress_bytes: number;
  total_bytes: number | null;
  files_transferred: number;
  files_total: number | null;
  current_file: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// ─── Provider Status ────────────────────────────────────────────

export async function getProviders(): Promise<ProvidersStatus> {
  const res = await apiClient.get('/api/cloud/providers');
  return res.data;
}

// ─── Connections ────────────────────────────────────────────────

export async function getConnections(): Promise<CloudConnection[]> {
  const res = await apiClient.get('/api/cloud/connections');
  return res.data;
}

export async function deleteConnection(id: number): Promise<void> {
  await apiClient.delete(`/api/cloud/connections/${id}`);
}

// ─── OAuth Flow ─────────────────────────────────────────────────

export async function getOAuthUrl(provider: CloudProvider): Promise<string> {
  const res = await apiClient.get(`/api/cloud/oauth/${provider}/start`);
  return res.data.oauth_url;
}

export async function submitOAuthCallback(code: string, state: string): Promise<CloudConnection> {
  const res = await apiClient.post('/api/cloud/oauth/callback', { code, state });
  return res.data;
}

// ─── iCloud ─────────────────────────────────────────────────────

export async function connectICloud(
  appleId: string,
  password: string
): Promise<{ connection: CloudConnection; requires_2fa: boolean }> {
  const res = await apiClient.post('/api/cloud/icloud/connect', {
    apple_id: appleId,
    password,
  });
  return res.data;
}

export async function submitICloud2FA(
  connectionId: number,
  code: string
): Promise<{ success: boolean }> {
  const res = await apiClient.post('/api/cloud/icloud/2fa', {
    connection_id: connectionId,
    code,
  });
  return res.data;
}

// ─── Dev Mode ───────────────────────────────────────────────────

export async function createDevConnection(provider: CloudProvider): Promise<CloudConnection> {
  const res = await apiClient.post('/api/cloud/dev/connect', { provider });
  return res.data;
}

// ─── File Browser ───────────────────────────────────────────────

export async function browseFiles(
  connectionId: number,
  path: string = '/'
): Promise<CloudFile[]> {
  const res = await apiClient.get(`/api/cloud/browse/${connectionId}`, {
    params: { path },
  });
  return res.data;
}

// ─── Import Jobs ────────────────────────────────────────────────

export async function startImport(params: {
  connection_id: number;
  source_path: string;
  destination_path: string;
  job_type?: 'import' | 'sync';
}): Promise<CloudImportJob> {
  const res = await apiClient.post('/api/cloud/import', {
    ...params,
    job_type: params.job_type || 'import',
  });
  return res.data;
}

export async function getJobs(limit: number = 50): Promise<CloudImportJob[]> {
  const res = await apiClient.get('/api/cloud/jobs', {
    params: { limit },
  });
  return res.data;
}

export async function getJob(jobId: number): Promise<CloudImportJob> {
  const res = await apiClient.get(`/api/cloud/jobs/${jobId}`);
  return res.data;
}

export async function cancelJob(jobId: number): Promise<void> {
  await apiClient.post(`/api/cloud/jobs/${jobId}/cancel`);
}

// ─── OAuth Config ────────────────────────────────────────────────

export async function setOAuthConfig(
  provider: CloudProvider,
  clientId: string,
  clientSecret: string
): Promise<void> {
  await apiClient.put('/api/cloud/oauth-config', {
    provider,
    client_id: clientId,
    client_secret: clientSecret,
  });
}

export async function deleteOAuthConfig(provider: CloudProvider): Promise<void> {
  await apiClient.delete(`/api/cloud/oauth-config/${provider}`);
}
