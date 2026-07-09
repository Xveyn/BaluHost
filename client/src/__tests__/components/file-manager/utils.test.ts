import { describe, it, expect } from 'vitest';
import { mapApiFileItem, getFullPath, toRelativePath, parentPath } from '../../../components/file-manager/utils';
import type { ApiFileItem, StorageMountpoint } from '../../../components/file-manager/types';

const raid: StorageMountpoint = {
  id: 'a', name: 'Main', type: 'raid', path: '/mnt/main',
  size_bytes: 100, used_bytes: 40, available_bytes: 60, status: 'ok', is_default: true,
};
const dev: StorageMountpoint = { ...raid, id: 'd', type: 'dev-storage', path: 'dev-storage' };

describe('mapApiFileItem', () => {
  it('maps a full API item incl. sync_info and snake_case fallbacks', () => {
    const raw: ApiFileItem = {
      name: 'a.txt', path: 'docs/a.txt', size: 12, type: 'file',
      modified_at: '2026-01-01T00:00:00Z', owner_id: 7, owner_name: 'bob', file_id: 3,
      sync_info: [{ device_name: 'pc', platform: 'windows', sync_direction: 'push', last_reported_at: 't' }],
      can_read: true, can_write: false, can_delete: true,
    };
    expect(mapApiFileItem(raw)).toEqual({
      name: 'a.txt', path: 'docs/a.txt', size: 12, type: 'file',
      modifiedAt: '2026-01-01T00:00:00Z', ownerId: 7, ownerName: 'bob', file_id: 3,
      syncInfo: [{ deviceName: 'pc', platform: 'windows', syncDirection: 'push', lastReportedAt: 't' }],
      canRead: true, canWrite: false, canDelete: true,
    });
  });

  it('falls back mtime->modifiedAt and leaves a timestamp when none given', () => {
    const m = mapApiFileItem({ name: 'x', path: 'x', size: 0, type: 'directory', mtime: 'm1' });
    expect(m.modifiedAt).toBe('m1');
    const n = mapApiFileItem({ name: 'y', path: 'y', size: 0, type: 'file' });
    expect(typeof n.modifiedAt).toBe('string');
    expect(n.syncInfo).toBeUndefined();
  });
});

describe('getFullPath', () => {
  it('passes the relative path through for dev-storage', () => {
    expect(getFullPath(dev, 'docs')).toBe('docs');
  });
  it('joins under the mountpoint path for real mounts', () => {
    expect(getFullPath(raid, 'docs')).toBe('/mnt/main/docs');
    expect(getFullPath(raid, '/docs')).toBe('/mnt/main/docs');
  });
  it('returns the mountpoint path for an empty relative path', () => {
    expect(getFullPath(raid, '')).toBe('/mnt/main');
  });
  it('returns the relative path unchanged with no mountpoint', () => {
    expect(getFullPath(null, 'docs')).toBe('docs');
  });
});

describe('toRelativePath', () => {
  it('strips the mountpoint prefix for real mounts', () => {
    expect(toRelativePath(raid, '/mnt/main/docs')).toBe('docs');
  });
  it('returns unchanged for dev-storage or a non-matching prefix', () => {
    expect(toRelativePath(dev, 'docs')).toBe('docs');
    expect(toRelativePath(raid, '/other/docs')).toBe('/other/docs');
  });
});

describe('parentPath', () => {
  it('drops the last segment', () => {
    expect(parentPath('a/b/c')).toBe('a/b');
  });
  it('returns empty for a single segment or empty input', () => {
    expect(parentPath('a')).toBe('');
    expect(parentPath('')).toBe('');
  });
});
