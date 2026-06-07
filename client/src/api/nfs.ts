import { apiClient } from '../lib/api';

export interface NfsExport {
  id: number;
  path: string;
  clients: string;
  read_only: boolean;
  root_squash: boolean;
  enabled: boolean;
  comment: string | null;
  mount_target: string;
}

export interface NfsStatus {
  is_running: boolean;
  version: string | null;
  exports_count: number;
}

export interface NfsExportInput {
  path: string;
  clients: string;
  read_only: boolean;
  root_squash: boolean;
  enabled: boolean;
  comment?: string | null;
}

export async function getNfsStatus(): Promise<NfsStatus> {
  const { data } = await apiClient.get<NfsStatus>('/api/nfs/status');
  return data;
}

export async function listNfsExports(): Promise<NfsExport[]> {
  const { data } = await apiClient.get<{ exports: NfsExport[] }>('/api/nfs/exports');
  return data.exports;
}

export async function createNfsExport(input: NfsExportInput): Promise<NfsExport> {
  const { data } = await apiClient.post<NfsExport>('/api/nfs/exports', input);
  return data;
}

export async function updateNfsExport(id: number, input: NfsExportInput): Promise<NfsExport> {
  const { data } = await apiClient.put<NfsExport>(`/api/nfs/exports/${id}`, input);
  return data;
}

export async function deleteNfsExport(id: number): Promise<void> {
  await apiClient.delete(`/api/nfs/exports/${id}`);
}
