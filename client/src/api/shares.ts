/**
 * API client for file sharing functionality
 */

import { apiClient, memoizedApiRequest } from '../lib/api';

export interface ShareLink {
  id: number;
  token: string;
  file_id: number;
  owner_id: number;
  has_password: boolean;
  allow_download: boolean;
  allow_preview: boolean;
  max_downloads: number | null;
  download_count: number;
  expires_at: string | null;
  description: string | null;
  created_at: string;
  last_accessed_at: string | null;
  is_expired: boolean;
  is_accessible: boolean;
  file_name: string | null;
  file_path: string | null;
  file_size: number | null;
}

export interface CreateShareLinkRequest {
  file_id: number;
  password?: string;
  allow_download?: boolean;
  allow_preview?: boolean;
  max_downloads?: number | null;
  expires_at?: string | null;
  description?: string;
}

export interface UpdateShareLinkRequest {
  password?: string;
  allow_download?: boolean;
  allow_preview?: boolean;
  max_downloads?: number | null;
  expires_at?: string | null;
  description?: string;
}

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
  total_share_links: number;
  active_share_links: number;
  expired_share_links: number;
  total_downloads: number;
  total_file_shares: number;
  active_file_shares: number;
  files_shared_with_me: number;
}

export interface ShareLinkInfo {
  has_password: boolean;
  is_accessible: boolean;
  is_expired: boolean;
  file_name: string | null;
  file_size: number | null;
  is_directory: boolean;
  description: string | null;
  expires_at: string | null;
  allow_preview: boolean;
}

export interface ShareLinkAccessRequest {
  password?: string;
}

export interface ShareLinkAccessResponse {
  file_id: number;
  file_name: string | null;
  file_path: string | null;
  file_size: number | null;
  is_directory: boolean;
  allow_download: boolean;
  allow_preview: boolean;
  description: string | null;
}

// ===========================
// Share Links API
// ===========================

export const createShareLink = async (data: CreateShareLinkRequest): Promise<ShareLink> => {
  const response = await apiClient.post('/shares/links', data);
  return response.data;
};

export const listShareLinks = async (includeExpired = false): Promise<ShareLink[]> => {
  // Memoized: Share-Links werden für 60s gecached
  return memoizedApiRequest<ShareLink[]>('/shares/links', { include_expired: includeExpired });
};

export const getShareLink = async (linkId: number): Promise<ShareLink> => {
  const response = await apiClient.get(`/shares/links/${linkId}`);
  return response.data;
};

export const updateShareLink = async (
  linkId: number,
  data: UpdateShareLinkRequest
): Promise<ShareLink> => {
  const response = await apiClient.patch(`/shares/links/${linkId}`, data);
  return response.data;
};

export const deleteShareLink = async (linkId: number): Promise<void> => {
  await apiClient.delete(`/shares/links/${linkId}`);
};

// ===========================
// Public Share Link Access
// ===========================

export const getShareLinkInfo = async (token: string): Promise<ShareLinkInfo> => {
  const response = await apiClient.get(`/shares/public/${token}/info`);
  return response.data;
};

export const accessShareLink = async (
  token: string,
  data: ShareLinkAccessRequest
): Promise<ShareLinkAccessResponse> => {
  const response = await apiClient.post(`/shares/public/${token}/access`, data);
  return response.data;
};

// ===========================
// File Shares API
// ===========================

export const createFileShare = async (data: CreateFileShareRequest): Promise<FileShare> => {
  const response = await apiClient.post('/shares/user-shares', data);
  return response.data;
};

export const listFileShares = async (): Promise<FileShare[]> => {
  // Memoized: FileShares werden für 60s gecached
  return memoizedApiRequest<FileShare[]>('/shares/user-shares');
};

export const listFileSharesForFile = async (fileId: number): Promise<FileShare[]> => {
  const response = await apiClient.get(`/shares/user-shares/file/${fileId}`);
  return response.data;
};

export const listFilesSharedWithMe = async (): Promise<SharedWithMe[]> => {
  const response = await apiClient.get('/shares/shared-with-me');
  return response.data;
};

export const updateFileShare = async (
  shareId: number,
  data: UpdateFileShareRequest
): Promise<FileShare> => {
  const response = await apiClient.patch(`/shares/user-shares/${shareId}`, data);
  return response.data;
};

export const deleteFileShare = async (shareId: number): Promise<void> => {
  await apiClient.delete(`/shares/user-shares/${shareId}`);
};

export const getShareStatistics = async (): Promise<ShareStatistics> => {
  const response = await apiClient.get('/shares/statistics');
  return response.data;
};
