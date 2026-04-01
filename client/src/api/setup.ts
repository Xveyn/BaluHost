/**
 * API client for setup wizard
 */

import { apiClient } from '../lib/api';

export interface SetupStatus {
  setup_required: boolean;
  completed_steps: string[];
}

export interface SetupAdminRequest {
  username: string;
  password: string;
  email?: string;
  setup_secret?: string;
}

export interface SetupAdminResponse {
  success: boolean;
  setup_token: string;
  user_id: number;
  username: string;
}

export interface SetupUserRequest {
  username: string;
  password: string;
  email?: string;
}

export interface SetupUserResponse {
  success: boolean;
  user_id: number;
  username: string;
  email?: string;
}

export interface SambaConfig {
  enabled: boolean;
  workgroup?: string;
  public_browsing?: boolean;
}

export interface WebdavConfig {
  enabled: boolean;
  port?: number;
  ssl?: boolean;
}

export interface SetupFileAccessRequest {
  samba?: SambaConfig;
  webdav?: WebdavConfig;
}

export interface SetupFileAccessResponse {
  success: boolean;
  active_services: string[];
}

export interface SetupCompleteResponse {
  success: boolean;
  message: string;
}

/** Check if initial setup is required (no auth needed). */
export async function getSetupStatus(): Promise<SetupStatus> {
  const resp = await apiClient.get<SetupStatus>('/api/setup/status');
  return resp.data;
}

/** Create admin account (Step 1, no auth). */
export async function createSetupAdmin(data: SetupAdminRequest): Promise<SetupAdminResponse> {
  const resp = await apiClient.post<SetupAdminResponse>('/api/setup/admin', data);
  return resp.data;
}

/** Create regular user (Step 2, requires setup token). */
export async function createSetupUser(data: SetupUserRequest, token: string): Promise<SetupUserResponse> {
  const resp = await apiClient.post<SetupUserResponse>('/api/setup/users', data, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return resp.data;
}

/** Delete user created during setup. */
export async function deleteSetupUser(userId: number, token: string): Promise<void> {
  await apiClient.delete(`/api/setup/users/${userId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

/** Configure file access (Step 4, requires setup token). */
export async function configureFileAccess(data: SetupFileAccessRequest, token: string): Promise<SetupFileAccessResponse> {
  const resp = await apiClient.post<SetupFileAccessResponse>('/api/setup/file-access', data, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return resp.data;
}

/** Mark setup as complete. */
export async function completeSetup(token: string): Promise<SetupCompleteResponse> {
  const resp = await apiClient.post<SetupCompleteResponse>('/api/setup/complete', {}, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return resp.data;
}
