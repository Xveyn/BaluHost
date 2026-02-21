/**
 * Shared types for file-manager components.
 */

export interface StorageInfo {
  totalBytes: number;
  usedBytes: number;
  availableBytes: number;
}

export interface StorageMountpoint {
  id: string;
  name: string;
  type: string;
  path: string;
  size_bytes: number;
  used_bytes: number;
  available_bytes: number;
  raid_level?: string;
  status: string;
  is_default: boolean;
}

export interface SyncDeviceInfo {
  deviceName: string;
  platform: 'windows' | 'mac' | 'linux';
  syncDirection: 'bidirectional' | 'push' | 'pull';
  lastReportedAt: string;
}

export interface FileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modifiedAt: string;
  ownerId?: number;
  ownerName?: string;
  file_id?: number;
  syncInfo?: SyncDeviceInfo[];
}

export interface ApiFileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modified_at?: string;
  mtime?: string;
  ownerId?: number;
  owner_id?: number;
  ownerName?: string;
  owner_name?: string;
  file_id?: number;
  sync_info?: Array<{
    device_name: string;
    platform: string;
    sync_direction: string;
    last_reported_at: string;
  }>;
}

export interface PermissionRule {
  userId: string;
  canView: boolean;
  canEdit: boolean;
  canDelete: boolean;
}
