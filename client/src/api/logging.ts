import { buildApiUrl } from '../lib/api';

const fetchWithAuth = async (url: string, options?: RequestInit): Promise<any> => {
  const token = localStorage.getItem('token');
  const response = await fetch(buildApiUrl(url), {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.json();
};

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
    [key: string]: any;
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
    return fetchWithAuth(`/api/logging/disk-io?hours=${hours}`);
  },

  async getFileAccessLogs(params?: {
    limit?: number;
    days?: number;
    action?: string;
    user?: string;
  }): Promise<FileAccessLogsResponse> {
    const queryParams = new URLSearchParams();
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.days) queryParams.append('days', params.days.toString());
    if (params?.action) queryParams.append('action', params.action);
    if (params?.user) queryParams.append('user', params.user);

    return fetchWithAuth(`/api/logging/file-access?${queryParams.toString()}`);
  },

  async getLoggingStats(days: number = 7): Promise<LoggingStats> {
    return fetchWithAuth(`/api/logging/stats?days=${days}`);
  },

  async getAuditLoggingStatus(): Promise<AuditLoggingStatus> {
    return fetchWithAuth('/api/system/audit-logging');
  },

  async toggleAuditLogging(enabled: boolean): Promise<AuditLoggingStatus> {
    return fetchWithAuth('/api/system/audit-logging', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    });
  },
};
