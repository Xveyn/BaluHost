/**
 * SSD File Cache API Client (per-array)
 */

import { apiClient } from '../lib/api';

// ========== Types ==========

export interface SSDCacheStats {
  array_name: string;
  is_enabled: boolean;
  cache_path: string;
  max_size_bytes: number;
  current_size_bytes: number;
  usage_percent: number;
  total_entries: number;
  valid_entries: number;
  total_hits: number;
  total_misses: number;
  hit_rate_percent: number;
  total_bytes_served: number;
  ssd_available_bytes: number;
  ssd_total_bytes: number;
}

export interface SSDCacheConfigResponse {
  array_name: string;
  is_enabled: boolean;
  cache_path: string;
  max_size_bytes: number;
  current_size_bytes: number;
  eviction_policy: string;
  min_file_size_bytes: number;
  max_file_size_bytes: number;
  sequential_cutoff_bytes: number;
  total_hits: number;
  total_misses: number;
  total_bytes_served_from_cache: number;
  updated_at: string | null;
}

export interface SSDCacheConfigUpdate {
  is_enabled?: boolean;
  cache_path?: string;
  max_size_bytes?: number;
  eviction_policy?: 'lfru' | 'lru' | 'lfu';
  min_file_size_bytes?: number;
  max_file_size_bytes?: number;
  sequential_cutoff_bytes?: number;
}

export interface SSDCacheEntryResponse {
  id: number;
  array_name: string;
  source_path: string;
  file_size_bytes: number;
  access_count: number;
  last_accessed: string;
  first_cached: string;
  is_valid: boolean;
}

export interface SSDCacheEntriesResponse {
  entries: SSDCacheEntryResponse[];
  total: number;
}

export interface EvictionResult {
  freed_bytes: number;
  deleted_count: number;
}

export interface CacheHealthResponse {
  array_name: string;
  is_mounted: boolean;
  ssd_total_bytes: number;
  ssd_available_bytes: number;
  ssd_used_percent: number;
  cache_dir_exists: boolean;
}

// ========== Overview (all arrays) ==========

export async function getCacheOverview(): Promise<SSDCacheStats[]> {
  const res = await apiClient.get('/api/ssd/cache/overview');
  return res.data;
}

// ========== Per-Array API Functions ==========

export async function getCacheStats(arrayName: string): Promise<SSDCacheStats> {
  const res = await apiClient.get(`/api/ssd/cache/${encodeURIComponent(arrayName)}/stats`);
  return res.data;
}

export async function getCacheConfig(arrayName: string): Promise<SSDCacheConfigResponse> {
  const res = await apiClient.get(`/api/ssd/cache/${encodeURIComponent(arrayName)}/config`);
  return res.data;
}

export async function updateCacheConfig(
  arrayName: string,
  data: SSDCacheConfigUpdate
): Promise<SSDCacheConfigResponse> {
  const res = await apiClient.put(`/api/ssd/cache/${encodeURIComponent(arrayName)}/config`, data);
  return res.data;
}

export async function getCacheEntries(
  arrayName: string,
  limit = 50,
  offset = 0,
  validOnly = false
): Promise<SSDCacheEntriesResponse> {
  const res = await apiClient.get(`/api/ssd/cache/${encodeURIComponent(arrayName)}/entries`, {
    params: { limit, offset, valid_only: validOnly },
  });
  return res.data;
}

export async function evictEntry(arrayName: string, entryId: number): Promise<{ freed_bytes: number; source_path: string }> {
  const res = await apiClient.delete(`/api/ssd/cache/${encodeURIComponent(arrayName)}/entries/${entryId}`);
  return res.data;
}

export async function triggerEviction(arrayName: string): Promise<EvictionResult> {
  const res = await apiClient.post(`/api/ssd/cache/${encodeURIComponent(arrayName)}/evict`);
  return res.data;
}

export async function clearCache(arrayName: string): Promise<EvictionResult> {
  const res = await apiClient.post(`/api/ssd/cache/${encodeURIComponent(arrayName)}/clear`);
  return res.data;
}

export async function getCacheHealth(arrayName: string): Promise<CacheHealthResponse> {
  const res = await apiClient.get(`/api/ssd/cache/${encodeURIComponent(arrayName)}/health`);
  return res.data;
}
