import { apiClient } from '../lib/api';

export interface SambaConnection {
  pid: string;
  username: string;
  machine: string;
}

export interface SambaStatus {
  is_running: boolean;
  version: string | null;
  active_connections: SambaConnection[];
  smb_users_count: number;
}

export interface SambaUserStatus {
  user_id: number;
  username: string;
  role: string;
  smb_enabled: boolean;
  is_active: boolean;
}

export interface SambaUsersResponse {
  users: SambaUserStatus[];
}

export interface OsConnectionInfo {
  os: string;
  label: string;
  command: string;
  notes: string | null;
}

export interface SambaConnectionInfo {
  is_running: boolean;
  share_name: string;
  smb_path: string;
  username: string;
  instructions: OsConnectionInfo[];
}

export async function getSambaStatus(): Promise<SambaStatus> {
  const { data } = await apiClient.get<SambaStatus>('/api/samba/status');
  return data;
}

export async function getSambaUsers(): Promise<SambaUsersResponse> {
  const { data } = await apiClient.get<SambaUsersResponse>('/api/samba/users');
  return data;
}

export async function toggleSmbUser(
  userId: number,
  enabled: boolean,
  password?: string,
): Promise<{ user_id: number; username: string; smb_enabled: boolean }> {
  const { data } = await apiClient.post(`/api/samba/users/${userId}/toggle`, {
    enabled,
    password: password || undefined,
  });
  return data;
}

export async function getSambaConnectionInfo(): Promise<SambaConnectionInfo> {
  const { data } = await apiClient.get<SambaConnectionInfo>('/api/samba/connection-info');
  return data;
}
