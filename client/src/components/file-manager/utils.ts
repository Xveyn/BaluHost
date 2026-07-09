import type { ApiFileItem, FileItem, StorageMountpoint } from './types';

/** Maps a raw API file item to the UI `FileItem` shape (moved from FileManager.loadFiles). */
export function mapApiFileItem(file: ApiFileItem): FileItem {
  return {
    name: file.name,
    path: file.path,
    size: file.size,
    type: file.type,
    modifiedAt: file.modified_at ?? file.mtime ?? new Date().toISOString(),
    ownerId: file.ownerId ?? file.owner_id,
    ownerName: file.ownerName ?? file.owner_name,
    file_id: file.file_id,
    syncInfo: file.sync_info?.map((si) => ({
      deviceName: si.device_name,
      platform: si.platform as 'windows' | 'mac' | 'linux',
      syncDirection: si.sync_direction as 'bidirectional' | 'push' | 'pull',
      lastReportedAt: si.last_reported_at,
    })),
    canRead: file.can_read ?? undefined,
    canWrite: file.can_write ?? undefined,
    canDelete: file.can_delete ?? undefined,
  };
}

/** Resolves a relative browser path to the backend full path for a mountpoint. */
export function getFullPath(mountpoint: StorageMountpoint | null, relativePath: string): string {
  if (!mountpoint) return relativePath;
  if (mountpoint.type === 'dev-storage') return relativePath;
  const clean = relativePath.startsWith('/') ? relativePath.slice(1) : relativePath;
  return clean ? `${mountpoint.path}/${clean}` : mountpoint.path;
}

/** Inverse of getFullPath for navigation: strips the mountpoint prefix (real mounts only). */
export function toRelativePath(mountpoint: StorageMountpoint | null, folderPath: string): string {
  if (mountpoint && mountpoint.type !== 'dev-storage') {
    const prefix = mountpoint.path;
    if (folderPath.startsWith(prefix)) {
      return folderPath.slice(prefix.length).replace(/^\//, '');
    }
  }
  return folderPath;
}

/** Parent of a relative path (drops the last segment). */
export function parentPath(currentPath: string): string {
  const parts = currentPath.split('/').filter(Boolean);
  parts.pop();
  return parts.join('/');
}
