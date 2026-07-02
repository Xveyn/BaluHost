/**
 * API client for system information endpoints
 */

import { apiClient } from '../lib/api';

export interface CpuInfo {
  usage: number;
  cores: number;
  frequency_mhz?: number | null;
  model?: string | null;
  temperature_celsius?: number | null;
}

export interface MemoryInfo {
  total: number;
  used: number;
  free: number;
  speed_mts?: number | null;
  type?: string | null;
}

export interface DiskInfo {
  total: number;
  used: number;
  free: number;
}

export interface SystemInfoResponse {
  cpu: CpuInfo;
  memory: MemoryInfo;
  disk: DiskInfo;
  uptime: number;
  system_uptime?: number;
  dev_mode: boolean;
}

export interface StorageInfoResponse {
  filesystem: string;
  total: number;
  used: number;
  available: number;
  use_percent: string;
  mount_point: string;
}

/**
 * Get system information (CPU, memory, disk, uptime, dev_mode).
 */
export async function getSystemInfo(): Promise<SystemInfoResponse> {
  const { data } = await apiClient.get<SystemInfoResponse>('/api/system/info');
  return data;
}

/**
 * Get system mode (dev/prod). Public endpoint, no auth required.
 */
export async function getSystemMode(): Promise<{
  dev_mode: boolean;
  dev_credentials?: { username: string; password: string };
}> {
  const { data } = await apiClient.get<{
    dev_mode: boolean;
    dev_credentials?: { username: string; password: string };
  }>('/api/system/mode');
  return data;
}

/**
 * Get storage information.
 */
export async function getStorageInfo(): Promise<StorageInfoResponse> {
  const { data } = await apiClient.get<StorageInfoResponse>('/api/system/storage');
  return data;
}

export interface StorageDeviceEntry {
  name: string;
  label: string;
  level: string | null;
  disk_type: string;
  capacity_bytes: number;
  used_bytes: number;
  available_bytes: number;
  use_percent: number;
  device_count: number;
}

export interface StorageBreakdownResponse {
  entries: StorageDeviceEntry[];
  total_capacity: number;
  total_raw_capacity: number;
  total_used: number;
  total_available: number;
  total_use_percent: number;
}

/**
 * Get per-array/device storage breakdown.
 */
export async function getStorageBreakdown(): Promise<StorageBreakdownResponse> {
  const { data } = await apiClient.get<StorageBreakdownResponse>(
    '/api/system/storage/breakdown'
  );
  return data;
}

/** Storage shape returned by /api/system/storage/aggregated (telemetry). */
export interface AggregatedStorageInfo {
  filesystem?: string;
  total: number;
  used: number;
  available: number;
  usePercent?: string | number;
  mountPoint?: string;
}

export interface CpuHistoryPoint {
  timestamp: number;
  usage: number;
}

export interface MemoryHistoryPoint {
  timestamp: number;
  used: number;
  total: number;
  percent: number;
}

export interface NetworkHistoryPoint {
  timestamp: number;
  downloadMbps: number;
  uploadMbps: number;
}

export interface TelemetryHistory {
  cpu: CpuHistoryPoint[];
  memory: MemoryHistoryPoint[];
  network: NetworkHistoryPoint[];
}

/** Get aggregated storage totals across all mountpoints (dashboard telemetry). */
export async function getAggregatedStorage(): Promise<AggregatedStorageInfo> {
  const { data } = await apiClient.get<AggregatedStorageInfo>(
    '/api/system/storage/aggregated'
  );
  return data;
}

/** Get rolling CPU/memory/network telemetry history (dashboard charts). */
export async function getTelemetryHistory(): Promise<TelemetryHistory> {
  const { data } = await apiClient.get<TelemetryHistory>(
    '/api/system/telemetry/history'
  );
  return data;
}
