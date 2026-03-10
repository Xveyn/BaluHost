/**
 * API client for backend application log streaming.
 */

import { apiClient } from '../lib/api';

export interface LogEntry {
  id: number;
  timestamp: string;
  level: string;
  logger_name: string;
  message: string;
  exc_info: string | null;
}

export interface BackendLogsResponse {
  entries: LogEntry[];
  latest_id: number;
  total_buffered: number;
}

export interface BackendLogsParams {
  since_id?: number;
  level?: string;
  search?: string;
  limit?: number;
}

export const backendLogsApi = {
  async getLogs(params?: BackendLogsParams): Promise<BackendLogsResponse> {
    const { data } = await apiClient.get<BackendLogsResponse>('/api/admin/backend-logs', { params });
    return data;
  },

  async clearLogs(): Promise<{ cleared: number }> {
    const { data } = await apiClient.delete<{ cleared: number }>('/api/admin/backend-logs');
    return data;
  },

  getStreamUrl(token: string, level?: string): string {
    const base = '/api/admin/backend-logs/stream';
    const params = new URLSearchParams({ token });
    if (level) params.set('level', level);
    return `${base}?${params.toString()}`;
  },
};

/** Map log level to Tailwind color classes for badges. */
export function getLevelColor(level: string): string {
  switch (level) {
    case 'DEBUG':
      return 'border-slate-500/40 bg-slate-500/15 text-slate-300';
    case 'INFO':
      return 'border-blue-500/40 bg-blue-500/15 text-blue-300';
    case 'WARNING':
      return 'border-amber-500/40 bg-amber-500/15 text-amber-300';
    case 'ERROR':
      return 'border-red-500/40 bg-red-500/15 text-red-300';
    case 'CRITICAL':
      return 'border-rose-500/40 bg-rose-600/20 text-rose-300';
    default:
      return 'border-slate-700/70 bg-slate-900/70 text-slate-300';
  }
}
