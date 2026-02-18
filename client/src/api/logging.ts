import { apiClient } from '../lib/api';

export interface DiskIOSample {
  timestamp: number;
  readMbps: number;
  writeMbps: number;
  readIops: number;
  writeIops: number;
  avgResponseMs: number;
  activeTimePercent: number | null;
}

export interface DiskIOData {
  dev_mode: boolean;
  disks: Record<string, DiskIOSample[]>;
}

export interface FileAccessLog {
  timestamp: string;
  event_type: string;
  user: string;
  action: string;
  resource: string;
  success: boolean;
  details?: {
    size_bytes?: number;
    duration_ms?: number;
    [key: string]: unknown;
  };
  error?: string;
}

export interface FileAccessLogsResponse {
  dev_mode: boolean;
  total: number;
  logs: FileAccessLog[];
}

export interface LoggingStats {
  dev_mode: boolean;
  period_days: number;
  disk_io?: {
    avg_read_mbps: number;
    avg_write_mbps: number;
    peak_read_mbps: number;
    peak_write_mbps: number;
    total_read_gb: number;
    total_write_gb: number;
  };
  file_access: {
    total_operations: number;
    by_action: Record<string, number>;
    by_user: Record<string, number>;
    success_rate: number;
  };
}

export interface AuditLoggingStatus {
  enabled: boolean;
  can_toggle: boolean;
  dev_mode: boolean;
}

export const loggingApi = {
  async getDiskIOLogs(hours: number = 24): Promise<DiskIOData> {
    const { data } = await apiClient.get<DiskIOData>('/api/logging/disk-io', {
      params: { hours },
    });
    return data;
  },

  async getFileAccessLogs(params?: {
    limit?: number;
    days?: number;
    action?: string;
    user?: string;
  }): Promise<FileAccessLogsResponse> {
    const { data } = await apiClient.get<FileAccessLogsResponse>('/api/logging/file-access', {
      params,
    });
    return data;
  },

  async getLoggingStats(days: number = 7): Promise<LoggingStats> {
    const { data } = await apiClient.get<LoggingStats>('/api/logging/stats', {
      params: { days },
    });
    return data;
  },

  async getAuditLoggingStatus(): Promise<AuditLoggingStatus> {
    const { data } = await apiClient.get<AuditLoggingStatus>('/api/system/audit-logging');
    return data;
  },

  async toggleAuditLogging(enabled: boolean): Promise<AuditLoggingStatus> {
    const { data } = await apiClient.post<AuditLoggingStatus>('/api/system/audit-logging', { enabled });
    return data;
  },
};
