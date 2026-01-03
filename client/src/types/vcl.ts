/**
 * VCL (Version Control Light) TypeScript Types
 * Matching backend Pydantic schemas
 */

// ========== Version Details ==========

export interface VersionDetail {
  id: number;
  version_number: number;
  file_size: number;
  compressed_size: number;
  compression_ratio: number;
  checksum: string;
  created_at: string;
  is_high_priority: boolean;
  change_type: string | null;
  comment: string | null;
  was_cached: boolean;
  storage_type: 'stored' | 'reference';
}

export interface VersionListResponse {
  versions: VersionDetail[];
  total: number;
  file_id: number;
}

// ========== Restore ==========

export interface RestoreRequest {
  version_id: number;
  comment?: string;
}

export interface RestoreResponse {
  success: boolean;
  message: string;
  file_id: number;
  file_path: string;
  restored_version: number;
  file_size: number;
}

// ========== Quota ==========

export interface QuotaInfo {
  max_size_bytes: number;
  current_usage_bytes: number;
  available_bytes: number;
  usage_percent: number;
  is_enabled: boolean;
  depth: number;
  compression_enabled: boolean;
  dedupe_enabled: boolean;
  cleanup_needed: boolean;
}

// ========== Settings ==========

export interface VCLSettingsResponse {
  user_id: number | null;
  max_size_bytes: number;
  current_usage_bytes: number;
  depth: number;
  headroom_percent: number;
  is_enabled: boolean;
  compression_enabled: boolean;
  dedupe_enabled: boolean;
  debounce_window_seconds: number;
  max_batch_window_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface VCLSettingsUpdate {
  max_size_bytes?: number;
  depth?: number;
  headroom_percent?: number;
  is_enabled?: boolean;
  compression_enabled?: boolean;
  dedupe_enabled?: boolean;
  debounce_window_seconds?: number;
  max_batch_window_seconds?: number;
}

// ========== Admin ==========

export interface AdminVCLOverview {
  total_versions: number;
  total_size_bytes: number;
  total_compressed_bytes: number;
  total_blobs: number;
  unique_blobs: number;
  deduplication_savings_bytes: number;
  compression_savings_bytes: number;
  total_savings_bytes: number;
  compression_ratio: number;
  priority_count: number;
  cached_versions_count: number;
  total_users: number;
  last_cleanup_at: string | null;
  last_priority_mode_at: string | null;
  updated_at: string | null;
}

export interface UserVCLStats {
  user_id: number;
  username: string;
  max_size_bytes: number;
  current_usage_bytes: number;
  usage_percent: number;
  total_versions: number;
  is_enabled: boolean;
}

export interface AdminUsersResponse {
  users: UserVCLStats[];
  total: number;
}

export interface AdminStatsResponse {
  overview: AdminVCLOverview;
  top_users: UserVCLStats[];
  recent_activity: {
    date: string;
    versions_created: number;
    bytes_saved: number;
  }[];
}

export interface CleanupRequest {
  user_id?: number;
  dry_run?: boolean;
  force_high_priority?: boolean;
}

export interface CleanupResponse {
  needed_cleanup: boolean;
  target_bytes: number;
  deleted_versions: number;
  freed_bytes: number;
  deleted_blobs: number;
  dry_run?: boolean;
  versions_deleted?: Array<{
    id: number;
    file_id: number;
    version_number: number;
    size: number;
    is_high_priority: boolean;
    created_at: string;
  }>;
}

export interface DiffLine {
  line_number_old: number | null;
  line_number_new: number | null;
  content: string;
  type: 'added' | 'removed' | 'unchanged' | 'modified';
}

export interface VersionDiffResponse {
  version_id_old: number;
  version_id_new: number;
  file_name: string;
  is_binary: boolean;
  old_size: number;
  new_size: number;
  diff_lines?: DiffLine[];
  message?: string;
}
