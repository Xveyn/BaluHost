/**
 * VCL (Version Control Light) API Client
 */

import { apiClient } from '../lib/api';
import type {
  VersionListResponse,
  RestoreRequest,
  RestoreResponse,
  QuotaInfo,
  VCLSettingsResponse,
  VCLSettingsUpdate,
  AdminVCLOverview,
  AdminUsersResponse,
  AdminStatsResponse,
  CleanupRequest,
  CleanupResponse,
  VersionDiffResponse,
} from '../types/vcl';

// ========== User Endpoints ==========

/**
 * Get all versions of a file
 */
export const getFileVersions = async (
  fileId: number,
  limit = 50,
  offset = 0
): Promise<VersionListResponse> => {
  const response = await apiClient.get(`/api/vcl/versions/${fileId}`, {
    params: { limit, offset },
  });
  return response.data;
};

/**
 * Restore a specific version
 */
export const restoreVersion = async (
  data: RestoreRequest
): Promise<RestoreResponse> => {
  const response = await apiClient.post('/api/vcl/restore', data);
  return response.data;
};

/**
 * Delete a specific version
 */
export const deleteVersion = async (versionId: number): Promise<{ success: boolean; message: string }> => {
  const response = await apiClient.delete(`/api/vcl/versions/${versionId}`);
  return response.data;
};

/**
 * Toggle high priority for a version
 */
export const toggleVersionPriority = async (
  versionId: number,
  isHighPriority: boolean
): Promise<{ success: boolean; message: string }> => {
  const response = await apiClient.patch(`/api/vcl/versions/${versionId}/priority`, {
    is_high_priority: isHighPriority,
  });
  return response.data;
};

/**
 * Get diff between two versions
 */
export const getVersionDiff = async (
  versionIdOld: number,
  versionIdNew: number
): Promise<VersionDiffResponse> => {
  const response = await apiClient.get('/api/vcl/versions/diff', {
    params: {
      version_id_old: versionIdOld,
      version_id_new: versionIdNew,
    },
  });
  return response.data;
};

/**
 * Get current user's VCL quota information
 */
export const getUserQuota = async (): Promise<QuotaInfo> => {
  const response = await apiClient.get('/api/vcl/quota');
  return response.data;
};

/**
 * Get current user's VCL settings
 */
export const getUserSettings = async (): Promise<VCLSettingsResponse> => {
  const response = await apiClient.get('/api/vcl/settings');
  return response.data;
};

/**
 * Update current user's VCL settings
 */
export const updateUserSettings = async (
  data: VCLSettingsUpdate
): Promise<VCLSettingsResponse> => {
  const response = await apiClient.put('/api/vcl/settings', data);
  return response.data;
};

// ========== Admin Endpoints ==========

/**
 * Get global VCL overview (Admin only)
 */
export const getAdminOverview = async (): Promise<AdminVCLOverview> => {
  const response = await apiClient.get('/api/vcl/admin/overview');
  return response.data;
};

/**
 * Get all users with VCL stats (Admin only)
 */
export const getAdminUsers = async (
  limit = 50,
  offset = 0
): Promise<AdminUsersResponse> => {
  const response = await apiClient.get('/api/vcl/admin/users', {
    params: { limit, offset },
  });
  // Backend returns array directly, wrap it in expected format
  const users = Array.isArray(response.data) ? response.data : [];
  return {
    users,
    total: users.length,
  };
};

/**
 * Get detailed VCL stats (Admin only)
 */
export const getAdminStats = async (): Promise<AdminStatsResponse> => {
  const response = await apiClient.get('/api/vcl/admin/stats');
  return response.data;
};

/**
 * Update VCL settings for a specific user (Admin only)
 */
export const updateUserSettingsAdmin = async (
  userId: number,
  data: VCLSettingsUpdate
): Promise<VCLSettingsResponse> => {
  const response = await apiClient.put(`/api/vcl/admin/settings/${userId}`, data);
  return response.data;
};

/**
 * Trigger manual cleanup (Admin only)
 */
export const triggerCleanup = async (
  data: CleanupRequest = {}
): Promise<CleanupResponse> => {
  const response = await apiClient.post('/api/vcl/admin/cleanup', data);
  return response.data;
};

/**
 * Download version content
 */
export const downloadVersion = async (versionId: number): Promise<Blob> => {
  const response = await apiClient.get(`/api/vcl/versions/${versionId}/download`, {
    responseType: 'blob',
  });
  return response.data;
};

/**
 * Format bytes to human-readable string
 */
export const formatBytes = (bytes: number, decimals = 2): string => {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];

  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
};

/**
 * Calculate compression ratio display
 */
export const formatCompressionRatio = (ratio: number): string => {
  return `${ratio.toFixed(2)}x`;
};

/**
 * Calculate savings percentage
 */
export const calculateSavingsPercent = (
  originalSize: number,
  compressedSize: number
): number => {
  if (originalSize === 0) return 0;
  return ((originalSize - compressedSize) / originalSize) * 100;
};

/**
 * VCL API object for easy import
 */
export const vclApi = {
  getFileVersions,
  restoreVersion,
  deleteVersion,
  toggleVersionPriority,
  getVersionDiff,
  downloadVersion,
  getUserQuota,
  getUserSettings,
  updateUserSettings,
  getAdminOverview,
  getAdminUsers,
  getAdminStats,
  updateUserSettingsAdmin,
  triggerCleanup,
  formatBytes,
  formatCompressionRatio,
  calculateSavingsPercent,
};
