/**
 * API client for system monitoring
 *
 * Provides functions for:
 * - CPU, Memory, Network, Disk I/O current values and history
 * - Process tracking
 * - Retention configuration (admin only)
 */

import { apiClient } from '../lib/api';

// ===== Time Range Types =====

export type TimeRange = '10m' | '1h' | '24h' | '7d';
export type DataSource = 'auto' | 'memory' | 'database';

// ===== Sample Types =====

export interface CpuSample {
  timestamp: string;
  usage_percent: number;
  frequency_mhz?: number;
  temperature_celsius?: number;
  core_count?: number;
  thread_count?: number;
  p_core_count?: number;  // Intel Performance cores
  e_core_count?: number;  // Intel Efficiency cores
  thread_usages?: number[];  // Per-thread CPU usage percentages
}

export interface MemorySample {
  timestamp: string;
  used_bytes: number;
  total_bytes: number;
  percent: number;
  available_bytes?: number;
  baluhost_memory_bytes?: number;  // Memory used by BaluHost processes
}

export interface NetworkSample {
  timestamp: string;
  download_mbps: number;
  upload_mbps: number;
  bytes_sent?: number;
  bytes_received?: number;
}

export interface DiskIoSample {
  timestamp: string;
  disk_name: string;
  read_mbps: number;
  write_mbps: number;
  read_iops: number;
  write_iops: number;
  avg_response_ms?: number;
  active_time_percent?: number;
}

export interface ProcessSample {
  timestamp: string;
  process_name: string;
  pid: number;
  cpu_percent: number;
  memory_mb: number;
  status: string;
  is_alive: boolean;
}

// ===== Current Response Types =====

export interface CurrentCpuResponse {
  timestamp: string;
  usage_percent: number;
  frequency_mhz?: number;
  temperature_celsius?: number;
  core_count?: number;
  thread_count?: number;
  p_core_count?: number;  // Intel Performance cores
  e_core_count?: number;  // Intel Efficiency cores
  thread_usages?: number[];  // Per-thread CPU usage percentages
}

export interface CurrentMemoryResponse {
  timestamp: string;
  used_bytes: number;
  total_bytes: number;
  percent: number;
  available_bytes?: number;
  baluhost_memory_bytes?: number;  // Memory used by BaluHost processes
}

export type InterfaceType = 'wifi' | 'ethernet' | 'unknown';

export interface CurrentNetworkResponse {
  timestamp: string;
  download_mbps: number;
  upload_mbps: number;
  interface_type?: InterfaceType;
}

export interface CurrentDiskIoResponse {
  disks: Record<string, DiskIoSample | null>;
}

export interface CurrentProcessResponse {
  processes: Record<string, ProcessSample | null>;
}

// ===== History Response Types =====

export interface CpuHistoryResponse {
  samples: CpuSample[];
  sample_count: number;
  source: string;
}

export interface MemoryHistoryResponse {
  samples: MemorySample[];
  sample_count: number;
  source: string;
}

export interface NetworkHistoryResponse {
  samples: NetworkSample[];
  sample_count: number;
  source: string;
}

export interface DiskIoHistoryResponse {
  disks: Record<string, DiskIoSample[]>;
  available_disks: string[];
  sample_count: number;
  source: string;
}

export interface ProcessHistoryResponse {
  processes: Record<string, ProcessSample[]>;
  sample_count: number;
  source: string;
  crashes_detected: number;
}

// ===== Retention Config Types =====

export interface RetentionConfig {
  metric_type: string;
  retention_hours: number;
  db_persist_interval: number;
  is_enabled: boolean;
  last_cleanup?: string;
  samples_cleaned: number;
}

export interface RetentionConfigListResponse {
  configs: RetentionConfig[];
}

// ===== Database Stats Types =====

export interface MetricDatabaseStats {
  metric_type: string;
  count: number;
  oldest?: string;
  newest?: string;
  retention_hours: number;
  last_cleanup?: string;
  total_cleaned: number;
  estimated_size_bytes: number;
}

export interface DatabaseStatsResponse {
  metrics: Record<string, MetricDatabaseStats>;
  total_samples: number;
  total_size_bytes: number;
}

// ===== Monitoring Status Type =====

export interface MonitoringStatusResponse {
  is_running: boolean;
  sample_count: number;
  sample_interval: number;
  buffer_size: number;
  persist_interval: number;
  last_cleanup?: string;
  collectors: Record<string, boolean>;
}

// ===== API Functions =====

// CPU
export async function getCpuCurrent(): Promise<CurrentCpuResponse> {
  const response = await apiClient.get<CurrentCpuResponse>('/api/monitoring/cpu/current');
  return response.data;
}

export async function getCpuHistory(
  timeRange: TimeRange = '1h',
  source: DataSource = 'auto',
  limit: number = 1000
): Promise<CpuHistoryResponse> {
  const response = await apiClient.get<CpuHistoryResponse>('/api/monitoring/cpu/history', {
    params: { time_range: timeRange, source, limit },
  });
  return response.data;
}

// Memory
export async function getMemoryCurrent(): Promise<CurrentMemoryResponse> {
  const response = await apiClient.get<CurrentMemoryResponse>('/api/monitoring/memory/current');
  return response.data;
}

export async function getMemoryHistory(
  timeRange: TimeRange = '1h',
  source: DataSource = 'auto',
  limit: number = 1000
): Promise<MemoryHistoryResponse> {
  const response = await apiClient.get<MemoryHistoryResponse>('/api/monitoring/memory/history', {
    params: { time_range: timeRange, source, limit },
  });
  return response.data;
}

// Network
export async function getNetworkCurrent(): Promise<CurrentNetworkResponse> {
  const response = await apiClient.get<CurrentNetworkResponse>('/api/monitoring/network/current');
  return response.data;
}

export async function getNetworkHistory(
  timeRange: TimeRange = '1h',
  source: DataSource = 'auto',
  limit: number = 1000
): Promise<NetworkHistoryResponse> {
  const response = await apiClient.get<NetworkHistoryResponse>('/api/monitoring/network/history', {
    params: { time_range: timeRange, source, limit },
  });
  return response.data;
}

// Disk I/O
export async function getDiskIoCurrent(): Promise<CurrentDiskIoResponse> {
  const response = await apiClient.get<CurrentDiskIoResponse>('/api/monitoring/disk-io/current');
  return response.data;
}

export async function getDiskIoHistory(
  timeRange: TimeRange = '1h',
  source: DataSource = 'auto',
  diskName?: string,
  limit: number = 1000
): Promise<DiskIoHistoryResponse> {
  const params: Record<string, any> = { time_range: timeRange, source, limit };
  if (diskName) params.disk_name = diskName;
  const response = await apiClient.get<DiskIoHistoryResponse>('/api/monitoring/disk-io/history', {
    params,
  });
  return response.data;
}

// Processes
export async function getProcessesCurrent(): Promise<CurrentProcessResponse> {
  const response = await apiClient.get<CurrentProcessResponse>('/api/monitoring/processes/current');
  return response.data;
}

export async function getProcessesHistory(
  timeRange: TimeRange = '1h',
  source: DataSource = 'auto',
  processName?: string
): Promise<ProcessHistoryResponse> {
  const params: Record<string, any> = { time_range: timeRange, source };
  if (processName) params.process_name = processName;
  const response = await apiClient.get<ProcessHistoryResponse>('/api/monitoring/processes/history', {
    params,
  });
  return response.data;
}

// Retention Configuration (Admin only)
export async function getRetentionConfig(): Promise<RetentionConfigListResponse> {
  const response = await apiClient.get<RetentionConfigListResponse>('/api/monitoring/config/retention');
  return response.data;
}

export async function updateRetentionConfig(
  metricType: string,
  retentionHours: number
): Promise<RetentionConfig> {
  const response = await apiClient.put<RetentionConfig>(
    `/api/monitoring/config/retention/${metricType}`,
    { retention_hours: retentionHours }
  );
  return response.data;
}

// Database Stats (Admin only)
export async function getDatabaseStats(): Promise<DatabaseStatsResponse> {
  const response = await apiClient.get<DatabaseStatsResponse>('/api/monitoring/stats/database');
  return response.data;
}

// Monitoring Status
export async function getMonitoringStatus(): Promise<MonitoringStatusResponse> {
  const response = await apiClient.get<MonitoringStatusResponse>('/api/monitoring/status');
  return response.data;
}

// Manual Cleanup (Admin only)
export async function triggerCleanup(): Promise<{ message: string; deleted: Record<string, number>; total: number }> {
  const response = await apiClient.post<{ message: string; deleted: Record<string, number>; total: number }>(
    '/api/monitoring/cleanup'
  );
  return response.data;
}
