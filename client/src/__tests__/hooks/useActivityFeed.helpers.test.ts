import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mapActionType, formatRelativeTime } from '../../hooks/useActivityFeed';

describe('mapActionType', () => {
  it('maps file.upload to upload/upload', () => {
    expect(mapActionType('file.upload')).toEqual({ icon: 'upload', titleKey: 'upload' });
  });

  it('maps file.download to download/download', () => {
    expect(mapActionType('file.download')).toEqual({ icon: 'download', titleKey: 'download' });
  });

  it('maps file.delete to delete/delete', () => {
    expect(mapActionType('file.delete')).toEqual({ icon: 'delete', titleKey: 'delete' });
  });

  it('maps folder.create to create/create', () => {
    expect(mapActionType('folder.create')).toEqual({ icon: 'create', titleKey: 'create' });
  });

  it('maps file.move to move/move', () => {
    expect(mapActionType('file.move')).toEqual({ icon: 'move', titleKey: 'move' });
  });

  it('maps file.rename to move/rename', () => {
    expect(mapActionType('file.rename')).toEqual({ icon: 'move', titleKey: 'rename' });
  });

  it('maps file.share to share/share', () => {
    expect(mapActionType('file.share')).toEqual({ icon: 'share', titleKey: 'share' });
  });

  it('maps file.permission to share/permission', () => {
    expect(mapActionType('file.permission')).toEqual({ icon: 'share', titleKey: 'permission' });
  });

  it('maps file.edit to file/edit', () => {
    expect(mapActionType('file.edit')).toEqual({ icon: 'file', titleKey: 'edit' });
  });

  it('maps file.open to file/open', () => {
    expect(mapActionType('file.open')).toEqual({ icon: 'file', titleKey: 'open' });
  });

  it('maps sync.triggered to file/sync', () => {
    expect(mapActionType('sync.triggered')).toEqual({ icon: 'file', titleKey: 'sync' });
  });

  it('falls back to file/default for unknown action types', () => {
    expect(mapActionType('something.unknown')).toEqual({ icon: 'file', titleKey: 'default' });
  });
});

describe('formatRelativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-02-07T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "just now" for < 60 seconds ago', () => {
    expect(formatRelativeTime(new Date('2026-02-07T11:59:30Z'))).toBe('just now');
  });

  it('returns minutes for < 60 minutes ago', () => {
    expect(formatRelativeTime(new Date('2026-02-07T11:55:00Z'))).toBe('5 minutes ago');
  });

  it('returns singular minute', () => {
    expect(formatRelativeTime(new Date('2026-02-07T11:59:00Z'))).toBe('1 minute ago');
  });

  it('returns hours for < 24 hours ago', () => {
    expect(formatRelativeTime(new Date('2026-02-07T09:00:00Z'))).toBe('3 hours ago');
  });

  it('returns singular hour', () => {
    expect(formatRelativeTime(new Date('2026-02-07T11:00:00Z'))).toBe('1 hour ago');
  });

  it('returns days for < 7 days ago', () => {
    expect(formatRelativeTime(new Date('2026-02-05T12:00:00Z'))).toBe('2 days ago');
  });

  it('returns singular day', () => {
    expect(formatRelativeTime(new Date('2026-02-06T12:00:00Z'))).toBe('1 day ago');
  });

  it('returns a date string for >= 7 days ago', () => {
    const result = formatRelativeTime(new Date('2026-01-20T12:00:00Z'));
    expect(result).not.toContain('ago');
    expect(result).not.toBe('just now');
  });
});
