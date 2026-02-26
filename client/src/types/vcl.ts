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

export type VCLMode = 'automatic' | 'manual';
export type TrackingAction = 'track' | 'exclude';

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
  vcl_mode: VCLMode;
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
  vcl_mode?: VCLMode;
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
  vcl_mode?: VCLMode;
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

// ========== Storage Info ==========

export interface VCLStorageInfo {
  storage_path: string;
  is_custom_path: boolean;
  blob_count: number;
  total_compressed_bytes: number;
  disk_total_bytes: number;
  disk_available_bytes: number;
  disk_used_percent: number;
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

// ========== Reconciliation ==========

export interface ReconciliationMismatch {
  file_id: number;
  file_path: string;
  version_id: number;
  version_number: number;
  current_version_user_id: number;
  current_version_username: string;
  current_file_owner_id: number;
  current_file_owner_username: string;
  compressed_size: number;
}

export interface AffectedUser {
  user_id: number;
  username: string;
  quota_delta: number;
  current_usage: number;
  max_size: number;
  would_exceed_quota: boolean;
}

export interface ReconciliationPreview {
  total_mismatches: number;
  mismatches: ReconciliationMismatch[];
  affected_users: AffectedUser[];
}

export interface ReconciliationRequest {
  user_id?: number;
  force_over_quota?: boolean;
  dry_run?: boolean;
}

export interface QuotaTransfer {
  from_user_id: number;
  from_username: string;
  to_user_id: number;
  to_username: string;
  bytes_transferred: number;
}

export interface ReconciliationResult {
  success: boolean;
  reconciled_versions: number;
  skipped_due_to_quota: number;
  quota_transfers: QuotaTransfer[];
  message: string;
}

// ========== Tracking ==========

export interface FileTrackingEntry {
  id: number;
  file_id: number | null;
  file_path: string | null;
  file_name: string | null;
  path_pattern: string | null;
  action: TrackingAction;
  is_directory: boolean;
  created_at: string;
}

export interface FileTrackingRequest {
  file_id?: number;
  path_pattern?: string;
  action: TrackingAction;
  is_directory?: boolean;
}

export interface FileTrackingListResponse {
  mode: VCLMode;
  rules: FileTrackingEntry[];
  total: number;
}

export interface FileTrackingCheckResponse {
  file_id: number;
  file_path: string;
  is_tracked: boolean;
  reason: string;
}
