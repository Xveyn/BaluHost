/**
 * API client for file sharing functionality
 */

import { apiClient, apiCache, memoizedApiRequest } from '../lib/api';

export interface FileShare {
  id: number;
  file_id: number;
  owner_id: number;
  shared_with_user_id: number;
  can_read: boolean;
  can_write: boolean;
  can_delete: boolean;
  can_share: boolean;
  expires_at: string | null;
  created_at: string;
  last_accessed_at: string | null;
  is_expired: boolean;
  is_accessible: boolean;
  owner_username: string | null;
  shared_with_username: string | null;
  file_name: string | null;
  file_path: string | null;
  file_size: number | null;
  is_directory: boolean;
}

export interface CreateFileShareRequest {
  file_id: number;
  shared_with_user_id: number;
  can_read?: boolean;
  can_write?: boolean;
  can_delete?: boolean;
  can_share?: boolean;
  expires_at?: string | null;
}

export interface UpdateFileShareRequest {
  can_read?: boolean;
  can_write?: boolean;
  can_delete?: boolean;
  can_share?: boolean;
  expires_at?: string | null;
}

export interface SharedWithMe {
  share_id: number;
  file_id: number;
  file_name: string;
  file_path: string;
  file_size: number;
  is_directory: boolean;
  owner_username: string;
  owner_id: number;
  can_read: boolean;
  can_write: boolean;
  can_delete: boolean;
  can_share: boolean;
  shared_at: string;
  expires_at: string | null;
  is_expired: boolean;
}

export interface ShareStatistics {
  total_file_shares: number;
  active_file_shares: number;
  files_shared_with_me: number;
}

// ===========================
// File Shares API
// ===========================

const SHARES_CACHE_KEY = '/api/shares/user-shares' + JSON.stringify({});

export const createFileShare = async (data: CreateFileShareRequest): Promise<FileShare> => {
  const response = await apiClient.post('/api/shares/user-shares', data);
  apiCache.delete(SHARES_CACHE_KEY);
  return response.data;
};

export const listFileShares = async (): Promise<FileShare[]> => {
  // Memoized: FileShares werden für 60s gecached
  return memoizedApiRequest<FileShare[]>('/api/shares/user-shares');
};

export const listFileSharesForFile = async (fileId: number): Promise<FileShare[]> => {
  const response = await apiClient.get(`/api/shares/user-shares/file/${fileId}`);
  return response.data;
};

export const listFilesSharedWithMe = async (): Promise<SharedWithMe[]> => {
  const response = await apiClient.get('/api/shares/shared-with-me');
  return response.data;
};

export const updateFileShare = async (
  shareId: number,
  data: UpdateFileShareRequest
): Promise<FileShare> => {
  const response = await apiClient.patch(`/api/shares/user-shares/${shareId}`, data);
  apiCache.delete(SHARES_CACHE_KEY);
  return response.data;
};

export const deleteFileShare = async (shareId: number): Promise<void> => {
  await apiClient.delete(`/api/shares/user-shares/${shareId}`);
  apiCache.delete(SHARES_CACHE_KEY);
};

export const getShareStatistics = async (): Promise<ShareStatistics> => {
  const response = await apiClient.get('/api/shares/statistics');
  return response.data;
};
