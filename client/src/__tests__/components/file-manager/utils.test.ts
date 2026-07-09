import { describe, it, expect } from 'vitest';
import { mapApiFileItem, getFullPath, toRelativePath, parentPath, vclWarningLevel, buildOwnerNameCache } from '../../../components/file-manager/utils';
import type { ApiFileItem, StorageMountpoint, FileItem } from '../../../components/file-manager/types';

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

describe('vclWarningLevel', () => {
  it('returns critical at or above 95%', () => {
    expect(vclWarningLevel(95)).toBe('critical');
    expect(vclWarningLevel(99.9)).toBe('critical');
  });
  it('returns warning in [80, 95)', () => {
    expect(vclWarningLevel(80)).toBe('warning');
    expect(vclWarningLevel(94.9)).toBe('warning');
  });
  it('returns null below 80%', () => {
    expect(vclWarningLevel(79.9)).toBeNull();
    expect(vclWarningLevel(0)).toBeNull();
  });
});

describe('buildOwnerNameCache', () => {
  const f = (over: Partial<FileItem>): FileItem => ({
    name: 'x', path: 'x', size: 0, type: 'file', modifiedAt: 't', ...over,
  });
  it('maps ownerId -> ownerName for valid entries', () => {
    const cache = buildOwnerNameCache([f({ ownerId: 7, ownerName: 'bob' }), f({ ownerId: 9, ownerName: 'ann' })]);
    expect(cache).toEqual({ '7': 'bob', '9': 'ann' });
  });
  it('skips missing / "null" / absent owner names', () => {
    const cache = buildOwnerNameCache([
      f({ ownerId: 1, ownerName: undefined }),
      f({ ownerId: 2, ownerName: 'null' }),
      f({ ownerName: 'noid' }),
    ]);
    expect(cache).toEqual({});
  });
});
