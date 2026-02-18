/**
 * API client for user management operations
 */

import { apiClient } from '../lib/api';

export interface UserPublic {
  id: number;
  username: string;
  email: string | null;
  role: string;
  is_active: boolean;
  smb_enabled?: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface UsersResponse {
  users: UserPublic[];
  total: number;
  active: number;
  inactive: number;
  admins: number;
}

export interface UserListParams {
  search?: string;
  role?: string;
  is_active?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface CreateUserPayload {
  username: string;
  password: string;
  email?: string;
  role?: string;
}

export interface UpdateUserPayload {
  username?: string;
  email?: string | null;
  password?: string;
  role?: string;
  is_active?: boolean;
}

/**
 * List all users with optional filtering and sorting.
 */
export async function listUsers(params?: UserListParams): Promise<UsersResponse> {
  const { data } = await apiClient.get<UsersResponse>('/api/users/', { params });
  return data;
}

/**
 * Create a new user (admin only).
 */
export async function createUser(payload: CreateUserPayload): Promise<UserPublic> {
  const { data } = await apiClient.post<UserPublic>('/api/users/', payload);
  return data;
}

/**
 * Update an existing user (admin only).
 */
export async function updateUser(userId: number, payload: UpdateUserPayload): Promise<UserPublic> {
  const { data } = await apiClient.put<UserPublic>(`/api/users/${userId}`, payload);
  return data;
}

/**
 * Delete a user (admin only).
 */
export async function deleteUser(userId: number): Promise<void> {
  await apiClient.delete(`/api/users/${userId}`);
}

/**
 * Bulk delete users (admin only).
 */
export async function bulkDeleteUsers(userIds: number[]): Promise<{ deleted: number }> {
  const { data } = await apiClient.post<{ deleted: number }>('/api/users/bulk-delete', userIds);
  return data;
}

/**
 * Toggle user active status (admin only).
 */
export async function toggleUserActive(userId: number): Promise<UserPublic> {
  const { data } = await apiClient.patch<UserPublic>(`/api/users/${userId}/toggle-active`);
  return data;
}

/**
 * Upload user avatar.
 */
export async function uploadUserAvatar(userId: number, avatarFile: File): Promise<{ avatar_url: string }> {
  const formData = new FormData();
  formData.append('avatar', avatarFile);
  const { data } = await apiClient.post<{ avatar_url: string }>(`/api/users/${userId}/avatar`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

/**
 * Update user email.
 */
export async function updateUserEmail(userId: number, email: string): Promise<UserPublic> {
  const { data } = await apiClient.patch<UserPublic>(`/api/users/${userId}`, { email });
  return data;
}

/**
 * Alias for listUsers() - backward compatible with existing call sites.
 */
export const getUsers = listUsers;
