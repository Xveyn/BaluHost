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

export interface FileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modifiedAt: string;
  ownerId?: number;
  ownerName?: string;
  file_id?: number;
}

export interface ApiFileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modified_at?: string;
  mtime?: string;
}

export interface PermissionRule {
  userId: string;
  canView: boolean;
  canEdit: boolean;
  canDelete: boolean;
}
