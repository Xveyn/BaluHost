/**
 * Update Service API client for BaluHost
 */
import { apiClient } from '../lib/api';

// Update status types
export type UpdateStatus =
  | 'pending'
  | 'checking'
  | 'downloading'
  | 'backing_up'
  | 'installing'
  | 'migrating'
  | 'restarting'
  | 'health_check'
  | 'completed'
  | 'failed'
  | 'rolled_back'
  | 'cancelled';

export type UpdateChannel = 'stable' | 'unstable';

// Version information
export interface VersionInfo {
  version: string;
  commit: string;
  commit_short: string;
  tag: string | null;
  date: string | null;
  is_dev_build: boolean;
}

// Changelog entry
export interface ChangelogEntry {
  version: string;
  date: string | null;
  changes: string[];
  breaking_changes: string[];
  is_prerelease: boolean;
}

// Check response
export interface UpdateCheckResponse {
  update_available: boolean;
  current_version: VersionInfo;
  latest_version: VersionInfo | null;
  changelog: ChangelogEntry[];
  channel: UpdateChannel;
  last_checked: string | null;
  blockers: string[];
  can_update: boolean;
  dev_version_available: boolean;
  dev_version: VersionInfo | null;
  dev_commits_ahead: number | null;
  dev_commits: CommitInfo[];
}

// Start request/response
export interface UpdateStartRequest {
  target_version?: string | null;
  skip_backup?: boolean;
  force?: boolean;
}

export interface UpdateStartResponse {
  success: boolean;
  update_id: number | null;
  message: string;
  blockers: string[];
}

// Progress response
export interface UpdateProgressResponse {
  update_id: number;
  status: UpdateStatus;
  progress_percent: number;
  current_step: string | null;
  started_at: string;
  estimated_remaining: number | null;
  from_version: string;
  to_version: string;
  error_message: string | null;
  can_rollback: boolean;
}

// History entry
export interface UpdateHistoryEntry {
  id: number;
  from_version: string;
  to_version: string;
  channel: UpdateChannel;
  from_commit: string;
  to_commit: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  status: UpdateStatus;
  error_message: string | null;
  rollback_commit: string | null;
  user_id: number | null;
  can_rollback: boolean;
}

export interface UpdateHistoryResponse {
  updates: UpdateHistoryEntry[];
  total: number;
  page: number;
  page_size: number;
}

// Rollback request/response
export interface RollbackRequest {
  target_update_id?: number | null;
  target_commit?: string | null;
  restore_backup?: boolean;
}

export interface RollbackResponse {
  success: boolean;
  message: string;
  update_id: number | null;
  rolled_back_to: string | null;
}

// Config
export interface UpdateConfig {
  id: number;
  auto_check_enabled: boolean;
  check_interval_hours: number;
  channel: UpdateChannel;
  auto_backup_before_update: boolean;
  require_healthy_services: boolean;
  auto_update_enabled: boolean;
  auto_update_window_start: string | null;
  auto_update_window_end: string | null;
  last_check_at: string | null;
  last_available_version: string | null;
  updated_at: string;
  updated_by: number | null;
}

export interface UpdateConfigUpdate {
  auto_check_enabled?: boolean;
  check_interval_hours?: number;
  channel?: UpdateChannel;
  auto_backup_before_update?: boolean;
  require_healthy_services?: boolean;
  auto_update_enabled?: boolean;
  auto_update_window_start?: string | null;
  auto_update_window_end?: string | null;
}

// Release notes
export interface ReleaseNoteCategory {
  name: string;
  icon: string;
  changes: string[];
}

export interface ReleaseNotesResponse {
  version: string;
  previous_version: string | null;
  date: string | null;
  categories: ReleaseNoteCategory[];
}

// Commit history types (Versions tab)
export interface CommitInfo {
  hash: string;
  hash_short: string;
  message: string;
  date: string;
  author: string;
  type: string | null;
  scope: string | null;
}

export interface VersionGroup {
  tag: string | null;
  version: string;
  date: string | null;
  commit_count: number;
  commits: CommitInfo[];
}

export interface CommitHistoryResponse {
  total_commits: number;
  groups: VersionGroup[];
}

export interface DiffFile {
  path: string;
  status: string;
  additions: number;
  deletions: number;
}

export interface CommitDiffResponse {
  hash: string;
  hash_short: string;
  message: string;
  date: string;
  author: string;
  stats: string;
  files: DiffFile[];
  diff: string;
}

// Release list types
export interface ReleaseInfo {
  tag: string;
  version: string;
  date: string | null;
  is_prerelease: boolean;
  commit_short: string;
}

export interface ReleaseListResponse {
  releases: ReleaseInfo[];
  total: number;
}

// Version history types (Version Tracker)
export interface VersionHistoryEntry {
  id: number;
  version: string;
  git_commit: string;
  git_commit_short: string;
  git_branch: string | null;
  python_version: string | null;
  first_seen: string;
  last_seen: string;
  times_started: number;
}

export interface VersionHistoryResponse {
  versions: VersionHistoryEntry[];
  total: number;
  current_version: string;
  current_commit: string;
}

// API Functions

/**
 * Get current version (public endpoint, no auth required)
 */
export async function getPublicVersion(): Promise<VersionInfo> {
  const response = await apiClient.get<VersionInfo>('/api/updates/version');
  return response.data;
}

/**
 * Get release notes for the current version (public endpoint, no auth required)
 */
export async function getReleaseNotes(): Promise<ReleaseNotesResponse> {
  const response = await apiClient.get<ReleaseNotesResponse>('/api/updates/release-notes');
  return response.data;
}

/**
 * Check for available updates
 */
export async function checkForUpdates(): Promise<UpdateCheckResponse> {
  const response = await apiClient.get<UpdateCheckResponse>('/api/updates/check');
  return response.data;
}

/**
 * Start an update
 */
export async function startUpdate(request?: UpdateStartRequest): Promise<UpdateStartResponse> {
  const response = await apiClient.post<UpdateStartResponse>('/api/updates/start', request ?? {});
  return response.data;
}

/**
 * Get update progress by ID
 */
export async function getUpdateProgress(updateId: number): Promise<UpdateProgressResponse> {
  const response = await apiClient.get<UpdateProgressResponse>(`/api/updates/progress/${updateId}`);
  return response.data;
}

/**
 * Get the currently running update (if any)
 */
export async function getCurrentUpdate(): Promise<UpdateProgressResponse | null> {
  const response = await apiClient.get<UpdateProgressResponse | null>('/api/updates/current');
  return response.data;
}

/**
 * Rollback to a previous version
 */
export async function rollbackUpdate(request?: RollbackRequest): Promise<RollbackResponse> {
  const response = await apiClient.post<RollbackResponse>('/api/updates/rollback', request ?? {});
  return response.data;
}

/**
 * Get update history
 */
export async function getUpdateHistory(
  options: { page?: number; page_size?: number } = {}
): Promise<UpdateHistoryResponse> {
  const response = await apiClient.get<UpdateHistoryResponse>('/api/updates/history', {
    params: {
      page: options.page ?? 1,
      page_size: options.page_size ?? 20,
    },
  });
  return response.data;
}

/**
 * Get update configuration
 */
export async function getUpdateConfig(): Promise<UpdateConfig> {
  const response = await apiClient.get<UpdateConfig>('/api/updates/config');
  return response.data;
}

/**
 * Update configuration
 */
export async function updateConfig(config: UpdateConfigUpdate): Promise<UpdateConfig> {
  const response = await apiClient.put<UpdateConfig>('/api/updates/config', config);
  return response.data;
}

/**
 * Get full commit history grouped by version tags
 */
export async function getCommitHistory(): Promise<CommitHistoryResponse> {
  const response = await apiClient.get<CommitHistoryResponse>('/api/updates/commits');
  return response.data;
}

/**
 * Get diff details for a specific commit
 */
export async function getCommitDiff(commitHash: string): Promise<CommitDiffResponse> {
  const response = await apiClient.get<CommitDiffResponse>(`/api/updates/commits/${commitHash}/diff`);
  return response.data;
}

/**
 * Get list of all releases (git tags)
 */
export async function getAllReleases(): Promise<ReleaseListResponse> {
  const response = await apiClient.get<ReleaseListResponse>('/api/updates/releases');
  return response.data;
}

/**
 * Get version history (all versions that have ever run on this system)
 */
export async function getVersionHistory(): Promise<VersionHistoryResponse> {
  const response = await apiClient.get<VersionHistoryResponse>('/api/updates/version-history');
  return response.data;
}

// Helper functions

/**
 * Get status display info (color, icon, label)
 */
export function getStatusInfo(status: UpdateStatus): {
  color: string;
  bgColor: string;
  icon: string;
  label: string;
} {
  switch (status) {
    case 'pending':
      return {
        color: 'text-slate-400',
        bgColor: 'bg-slate-500/20',
        icon: '⏳',
        label: 'Pending',
      };
    case 'checking':
      return {
        color: 'text-sky-400',
        bgColor: 'bg-sky-500/20',
        icon: '🔍',
        label: 'Checking',
      };
    case 'downloading':
      return {
        color: 'text-sky-400',
        bgColor: 'bg-sky-500/20',
        icon: '⬇️',
        label: 'Downloading',
      };
    case 'backing_up':
      return {
        color: 'text-amber-400',
        bgColor: 'bg-amber-500/20',
        icon: '💾',
        label: 'Creating Backup',
      };
    case 'installing':
      return {
        color: 'text-sky-400',
        bgColor: 'bg-sky-500/20',
        icon: '📦',
        label: 'Installing',
      };
    case 'migrating':
      return {
        color: 'text-purple-400',
        bgColor: 'bg-purple-500/20',
        icon: '🔄',
        label: 'Migrating Database',
      };
    case 'restarting':
      return {
        color: 'text-amber-400',
        bgColor: 'bg-amber-500/20',
        icon: '🔄',
        label: 'Restarting Services',
      };
    case 'health_check':
      return {
        color: 'text-sky-400',
        bgColor: 'bg-sky-500/20',
        icon: '🏥',
        label: 'Health Check',
      };
    case 'completed':
      return {
        color: 'text-emerald-400',
        bgColor: 'bg-emerald-500/20',
        icon: '✅',
        label: 'Completed',
      };
    case 'failed':
      return {
        color: 'text-rose-400',
        bgColor: 'bg-rose-500/20',
        icon: '❌',
        label: 'Failed',
      };
    case 'rolled_back':
      return {
        color: 'text-amber-400',
        bgColor: 'bg-amber-500/20',
        icon: '↩️',
        label: 'Rolled Back',
      };
    case 'cancelled':
      return {
        color: 'text-slate-400',
        bgColor: 'bg-slate-500/20',
        icon: '🚫',
        label: 'Cancelled',
      };
    default:
      return {
        color: 'text-slate-400',
        bgColor: 'bg-slate-500/20',
        icon: '❓',
        label: status,
      };
  }
}

/**
 * Format duration in seconds to human readable string
 */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '-';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

/**
 * Check if an update status indicates it's in progress
 */
export function isUpdateInProgress(status: UpdateStatus): boolean {
  return [
    'pending',
    'checking',
    'downloading',
    'backing_up',
    'installing',
    'migrating',
    'restarting',
    'health_check',
  ].includes(status);
}

/**
 * Get channel display info
 */
export function getChannelInfo(channel: UpdateChannel): {
  label: string;
  color: string;
  description: string;
} {
  switch (channel) {
    case 'stable':
      return {
        label: 'Stable',
        color: 'text-emerald-400',
        description: 'Production-ready releases',
      };
    case 'unstable':
      return {
        label: 'Unstable',
        color: 'text-amber-400',
        description: 'Pre-release versions with new features',
      };
    default:
      return {
        label: channel,
        color: 'text-slate-400',
        description: '',
      };
  }
}
