/**
 * API client for disk benchmarking
 *
 * Provides functions for:
 * - Getting available disks and benchmark profiles
 * - Starting and cancelling benchmarks
 * - Tracking benchmark progress
 * - Viewing benchmark history and results
 */

import { apiClient } from '../lib/api';
import { formatBytes as sharedFormatBytes, formatNumber } from '../lib/formatters';

// ===== Enums =====

export type BenchmarkProfile = 'quick' | 'standard' | 'comprehensive';
export type BenchmarkStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type BenchmarkTargetType = 'test_file' | 'raw_device';

// ===== Disk Info Types =====

export interface DiskInfo {
  name: string;
  model?: string;
  size_bytes: number;
  size_display: string;
  mount_point?: string;
  filesystem?: string;
  is_system_disk: boolean;
  is_raid_member: boolean;
  can_benchmark: boolean;
  warning?: string;
}

export interface AvailableDisksResponse {
  disks: DiskInfo[];
}

// ===== Profile Types =====

export interface BenchmarkTestConfig {
  name: string;
  block_size: string;
  queue_depth: number;
  num_jobs: number;
  runtime_seconds: number;
  operations: string[];
}

export interface BenchmarkProfileConfig {
  name: string;
  display_name: string;
  description: string;
  test_file_size_bytes: number;
  tests: BenchmarkTestConfig[];
  estimated_duration_seconds: number;
}

export interface ProfileListResponse {
  profiles: BenchmarkProfileConfig[];
}

// ===== Request Types =====

export interface BenchmarkStartRequest {
  disk_name: string;
  profile: BenchmarkProfile;
  target_type?: BenchmarkTargetType;
  test_directory?: string;
}

export interface BenchmarkPrepareRequest {
  disk_name: string;
  profile: BenchmarkProfile;
}

export interface BenchmarkConfirmRequest {
  confirmation_token: string;
  disk_name: string;
  profile: BenchmarkProfile;
}

// ===== Result Types =====

export interface TestResult {
  test_name: string;
  operation: string;
  block_size: string;
  queue_depth: number;
  num_jobs: number;
  throughput_mbps?: number;
  iops?: number;
  latency_avg_us?: number;
  latency_min_us?: number;
  latency_max_us?: number;
  latency_p99_us?: number;
  latency_p95_us?: number;
  latency_p50_us?: number;
  bandwidth_bytes?: number;
  runtime_ms?: number;
  completed_at?: string;
}

export interface BenchmarkSummaryResults {
  seq_read_mbps?: number;
  seq_write_mbps?: number;
  seq_read_q1_mbps?: number;
  seq_write_q1_mbps?: number;
  rand_read_iops?: number;
  rand_write_iops?: number;
  rand_read_q1_iops?: number;
  rand_write_q1_iops?: number;
}

// ===== Response Types =====

export interface BenchmarkResponse {
  id: number;
  disk_name: string;
  disk_model?: string;
  disk_size_bytes?: number;
  profile: BenchmarkProfile;
  target_type: BenchmarkTargetType;
  status: BenchmarkStatus;
  progress_percent: number;
  current_test?: string;
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  summary: BenchmarkSummaryResults;
  test_results: TestResult[];
}

export interface BenchmarkProgressResponse {
  id: number;
  status: BenchmarkStatus;
  progress_percent: number;
  current_test?: string;
  started_at?: string;
  estimated_remaining_seconds?: number;
}

export interface BenchmarkPrepareResponse {
  confirmation_token: string;
  expires_at: string;
  disk_name: string;
  disk_model?: string;
  disk_size_bytes: number;
  warning_message: string;
  profile: BenchmarkProfile;
}

export interface BenchmarkListResponse {
  items: BenchmarkResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ===== API Functions =====

/**
 * Get list of available disks for benchmarking
 */
export async function getAvailableDisks(): Promise<AvailableDisksResponse> {
  const response = await apiClient.get<AvailableDisksResponse>('/api/benchmark/disks');
  return response.data;
}

/**
 * Get available benchmark profiles
 */
export async function getBenchmarkProfiles(): Promise<ProfileListResponse> {
  const response = await apiClient.get<ProfileListResponse>('/api/benchmark/profiles');
  return response.data;
}

/**
 * Start a new benchmark (test file mode - safe)
 */
export async function startBenchmark(request: BenchmarkStartRequest): Promise<BenchmarkResponse> {
  const response = await apiClient.post<BenchmarkResponse>('/api/benchmark/start', request);
  return response.data;
}

/**
 * Prepare a raw device benchmark (admin only, requires confirmation)
 */
export async function prepareBenchmark(request: BenchmarkPrepareRequest): Promise<BenchmarkPrepareResponse> {
  const response = await apiClient.post<BenchmarkPrepareResponse>('/api/benchmark/prepare', request);
  return response.data;
}

/**
 * Start a raw device benchmark after confirmation (admin only)
 */
export async function startConfirmedBenchmark(request: BenchmarkConfirmRequest): Promise<BenchmarkResponse> {
  const response = await apiClient.post<BenchmarkResponse>('/api/benchmark/start-confirmed', request);
  return response.data;
}

/**
 * Get a benchmark by ID
 */
export async function getBenchmark(benchmarkId: number): Promise<BenchmarkResponse> {
  const response = await apiClient.get<BenchmarkResponse>(`/api/benchmark/${benchmarkId}`);
  return response.data;
}

/**
 * Get progress of a running benchmark (for polling)
 */
export async function getBenchmarkProgress(benchmarkId: number): Promise<BenchmarkProgressResponse> {
  const response = await apiClient.get<BenchmarkProgressResponse>(`/api/benchmark/${benchmarkId}/progress`);
  return response.data;
}

/**
 * Cancel a running benchmark
 */
export async function cancelBenchmark(benchmarkId: number): Promise<{ message: string; benchmark_id: number }> {
  const response = await apiClient.post<{ message: string; benchmark_id: number }>(
    `/api/benchmark/${benchmarkId}/cancel`
  );
  return response.data;
}

/**
 * Mark a stuck benchmark as failed (admin only)
 */
export async function markBenchmarkFailed(benchmarkId: number): Promise<{ message: string; benchmark_id: number }> {
  const response = await apiClient.post<{ message: string; benchmark_id: number }>(
    `/api/benchmark/${benchmarkId}/mark-failed`
  );
  return response.data;
}

/**
 * Get paginated list of benchmarks (history)
 */
export async function getBenchmarkHistory(
  page: number = 1,
  pageSize: number = 10,
  diskName?: string
): Promise<BenchmarkListResponse> {
  const params: Record<string, any> = { page, page_size: pageSize };
  if (diskName) params.disk_name = diskName;
  const response = await apiClient.get<BenchmarkListResponse>('/api/benchmark/', { params });
  return response.data;
}

// ===== Helper Functions =====

/**
 * Format bytes to human-readable string (re-export from shared formatters)
 */
export const formatBytes = sharedFormatBytes;

/**
 * Format throughput (MB/s)
 */
export function formatThroughput(mbps: number | undefined): string {
  if (mbps === undefined || mbps === null) return '-';
  if (mbps >= 1000) {
    return `${formatNumber(mbps / 1000, 2)} GB/s`;
  }
  return `${formatNumber(mbps, 1)} MB/s`;
}

/**
 * Format IOPS
 */
export function formatIops(iops: number | undefined): string {
  if (iops === undefined || iops === null) return '-';
  if (iops >= 1000000) {
    return `${formatNumber(iops / 1000000, 2)}M`;
  }
  if (iops >= 1000) {
    return `${formatNumber(iops / 1000, 1)}K`;
  }
  return formatNumber(iops, 0);
}

/**
 * Format duration in seconds to human-readable string
 */
export function formatDuration(seconds: number | undefined): string {
  if (seconds === undefined || seconds === null) return '-';
  if (seconds < 60) {
    return `${formatNumber(seconds, 0)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

/**
 * Format latency in microseconds
 */
export function formatLatency(us: number | undefined): string {
  if (us === undefined || us === null) return '-';
  if (us < 1000) {
    return `${formatNumber(us, 0)} µs`;
  }
  return `${formatNumber(us / 1000, 2)} ms`;
}
