/**
 * API client for backup functionality
 */

import { apiClient, memoizedApiRequest } from '../lib/api';

export interface Backup {
  id: number;
  filename: string;
  filepath: string;
  size_bytes: number;
  size_mb: number;
  backup_type: 'full' | 'incremental' | 'database_only' | 'files_only';
  status: 'in_progress' | 'completed' | 'failed';
  created_at: string;
  completed_at: string | null;
  creator_id: number;
  error_message: string | null;
  includes_database: boolean;
  includes_files: boolean;
  includes_config: boolean;
}

export interface CreateBackupRequest {
  backup_type?: 'full' | 'incremental' | 'database_only' | 'files_only';
  includes_database?: boolean;
  includes_files?: boolean;
  includes_config?: boolean;
  backup_path?: string;
}

export interface BackupListResponse {
  backups: Backup[];
  total_size_bytes: number;
  total_size_mb: number;
}

export interface RestoreBackupRequest {
  backup_id: number;
  restore_database?: boolean;
  restore_files?: boolean;
  restore_config?: boolean;
  confirm: boolean;
}

export interface RestoreBackupResponse {
  success: boolean;
  message: string;
  backup_id: number;
  restored_at: string;
}

/**
 * Create a new system backup
 */
export async function createBackup(request: CreateBackupRequest = {}): Promise<Backup> {
  const response = await apiClient.post<Backup>('/api/backups/', request);
  return response.data;
}

/**
 * List all backups
 */
export async function listBackups(): Promise<BackupListResponse> {
  // Memoized: Backups werden für 60s gecached
  return memoizedApiRequest<BackupListResponse>('/api/backups/');
}

/**
 * Get backup details by ID
 */
export async function getBackup(backupId: number): Promise<Backup> {
  // Memoized: Backup-Details werden für 60s gecached
  return memoizedApiRequest<Backup>(`/api/backups/${backupId}/`);
}

/**
 * Delete a backup
 */
export async function deleteBackup(backupId: number): Promise<void> {
  await apiClient.delete(`/api/backups/${backupId}`);
}

/**
 * Restore system from backup
 */
export async function restoreBackup(request: RestoreBackupRequest): Promise<RestoreBackupResponse> {
  const token = localStorage.getItem('token');
  const response = await apiClient.post<RestoreBackupResponse>(
    `/api/backups/${request.backup_id}/restore`,
    request,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    }
  );
  return response.data;
}

/**
 * Download backup file
 */
export function getBackupDownloadUrl(backupId: number): string {
  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const token = localStorage.getItem('token');
  return `${baseUrl}/api/backups/${backupId}/download?token=${token}`;
}

/**
 * Download backup file (triggers browser download)
 */
export async function downloadBackup(backupId: number, filename: string): Promise<void> {
  const url = getBackupDownloadUrl(backupId);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
