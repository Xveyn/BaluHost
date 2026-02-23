/**
 * Data Migration API Client (VCL HDD -> SSD)
 */

import { apiClient } from '../lib/api';

// ========== Directory Browse ==========

export interface DirectoryEntry {
  name: string;
  path: string;
  is_mountpoint: boolean;
}

export async function browseDirectory(path: string): Promise<DirectoryEntry[]> {
  const res = await apiClient.get('/api/ssd/migration/browse', { params: { path } });
  return res.data;
}

// ========== Types ==========

export interface MigrationJobResponse {
  id: number;
  job_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  source_path: string;
  dest_path: string;
  total_files: number;
  processed_files: number;
  skipped_files: number;
  failed_files: number;
  total_bytes: number;
  processed_bytes: number;
  current_file: string | null;
  progress_percent: number;
  error_message: string | null;
  dry_run: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
}

export interface VCLMigrationStartRequest {
  source_path: string;
  dest_path: string;
  dry_run: boolean;
}

export interface VCLVerifyRequest {
  dest_path: string;
}

export interface VCLCleanupRequest {
  source_path: string;
  dry_run: boolean;
}

// ========== API Functions ==========

export async function startVCLMigration(data: VCLMigrationStartRequest): Promise<MigrationJobResponse> {
  const res = await apiClient.post('/api/ssd/migration/vcl/start', data);
  return res.data;
}

export async function startVCLVerify(data: VCLVerifyRequest): Promise<MigrationJobResponse> {
  const res = await apiClient.post('/api/ssd/migration/vcl/verify', data);
  return res.data;
}

export async function startVCLCleanup(data: VCLCleanupRequest): Promise<MigrationJobResponse> {
  const res = await apiClient.post('/api/ssd/migration/vcl/cleanup', data);
  return res.data;
}

export async function getMigrationJobs(limit = 20): Promise<MigrationJobResponse[]> {
  const res = await apiClient.get('/api/ssd/migration/jobs', { params: { limit } });
  return res.data;
}

export async function getMigrationJob(id: number): Promise<MigrationJobResponse> {
  const res = await apiClient.get(`/api/ssd/migration/jobs/${id}`);
  return res.data;
}

export async function cancelMigrationJob(id: number): Promise<void> {
  await apiClient.post(`/api/ssd/migration/jobs/${id}/cancel`);
}
