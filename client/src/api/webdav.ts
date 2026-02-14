import { apiClient } from '../lib/api';

export interface WebdavStatus {
  is_running: boolean;
  port: number;
  ssl_enabled: boolean;
  started_at: string | null;
  worker_pid: number | null;
  last_heartbeat: string | null;
  error_message: string | null;
  connection_url: string | null;
}

export interface OsConnectionInfo {
  os: string;
  label: string;
  command: string;
  notes: string | null;
}

export interface WebdavConnectionInfo {
  is_running: boolean;
  port: number;
  ssl_enabled: boolean;
  username: string;
  connection_url: string;
  instructions: OsConnectionInfo[];
}

export async function getWebdavStatus(): Promise<WebdavStatus> {
  const { data } = await apiClient.get<WebdavStatus>('/api/webdav/status');
  return data;
}

export async function getWebdavConnectionInfo(): Promise<WebdavConnectionInfo> {
  const { data } = await apiClient.get<WebdavConnectionInfo>('/api/webdav/connection-info');
  return data;
}
