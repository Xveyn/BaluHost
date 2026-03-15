/**
 * API client for file operations (permissions, duplicates, ownership transfer, residency)
 */

import { apiClient, memoizedApiRequest } from '../lib/api';

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

// --- Ownership Transfer API ---

export interface ConflictInfo {
  original_path: string;
  resolved_path: string | null;
  action: string;
}

export interface OwnershipTransferRequest {
  path: string;
  new_owner_id: number;
  recursive?: boolean;
  conflict_strategy?: 'rename' | 'skip' | 'overwrite';
}

export interface OwnershipTransferResponse {
  success: boolean;
  message: string;
  transferred_count: number;
  skipped_count: number;
  new_path: string | null;
  conflicts: ConflictInfo[];
  error: string | null;
}

export async function transferOwnership(
  request: OwnershipTransferRequest
): Promise<OwnershipTransferResponse> {
  const res = await apiClient.post('/api/files/transfer-ownership', request);
  return res.data;
}

// --- Residency Enforcement API ---

export interface ResidencyViolation {
  path: string;
  current_owner_id: number;
  current_owner_username: string;
  expected_directory: string;
  actual_directory: string;
}

export interface EnforceResidencyRequest {
  dry_run?: boolean;
  scope?: string | null;
}

export interface EnforceResidencyResponse {
  violations: ResidencyViolation[];
  fixed_count: number;
}

export async function enforceResidency(
  request: EnforceResidencyRequest
): Promise<EnforceResidencyResponse> {
  const res = await apiClient.post('/api/files/enforce-residency', request);
  return res.data;
}
