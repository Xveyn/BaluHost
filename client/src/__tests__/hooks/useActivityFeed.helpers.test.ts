import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  getActionIcon,
  getActionTitle,
  formatRelativeTime,
  transformLog,
} from '../../hooks/useActivityFeed';
import type { FileAccessLog } from '../../api/logging';

describe('getActionIcon', () => {
  it('maps upload to "upload"', () => {
    expect(getActionIcon('upload')).toBe('upload');
  });

  it('maps download to "download"', () => {
    expect(getActionIcon('download')).toBe('download');
  });

  it('maps delete to "delete"', () => {
    expect(getActionIcon('delete')).toBe('delete');
  });

  it('maps create to "create"', () => {
    expect(getActionIcon('create')).toBe('create');
  });

  it('maps mkdir to "create"', () => {
    expect(getActionIcon('mkdir')).toBe('create');
  });

  it('maps login to "user"', () => {
    expect(getActionIcon('login')).toBe('user');
  });

  it('maps auth to "user"', () => {
    expect(getActionIcon('auth')).toBe('user');
  });

  it('maps move to "move"', () => {
    expect(getActionIcon('move')).toBe('move');
  });

  it('maps rename to "move"', () => {
    expect(getActionIcon('rename')).toBe('move');
  });

  it('maps copy to "copy"', () => {
    expect(getActionIcon('copy')).toBe('copy');
  });

  it('maps share to "share"', () => {
    expect(getActionIcon('share')).toBe('share');
  });

  it('returns "file" for unknown actions', () => {
    expect(getActionIcon('something-unknown')).toBe('file');
  });
});

describe('getActionTitle', () => {
  it('maps upload to "File Uploaded"', () => {
    expect(getActionTitle('upload')).toBe('File Uploaded');
  });

  it('maps download to "File Downloaded"', () => {
    expect(getActionTitle('download')).toBe('File Downloaded');
  });

  it('maps delete to "File Deleted"', () => {
    expect(getActionTitle('delete')).toBe('File Deleted');
  });

  it('maps login to "User Login"', () => {
    expect(getActionTitle('login')).toBe('User Login');
  });

  it('capitalizes unknown actions', () => {
    expect(getActionTitle('custom')).toBe('Custom');
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
    const date = new Date('2026-02-07T11:59:30Z');
    expect(formatRelativeTime(date)).toBe('just now');
  });

  it('returns minutes for < 60 minutes ago', () => {
    const date = new Date('2026-02-07T11:55:00Z');
    expect(formatRelativeTime(date)).toBe('5 minutes ago');
  });

  it('returns singular minute', () => {
    const date = new Date('2026-02-07T11:59:00Z');
    expect(formatRelativeTime(date)).toBe('1 minute ago');
  });

  it('returns hours for < 24 hours ago', () => {
    const date = new Date('2026-02-07T09:00:00Z');
    expect(formatRelativeTime(date)).toBe('3 hours ago');
  });

  it('returns singular hour', () => {
    const date = new Date('2026-02-07T11:00:00Z');
    expect(formatRelativeTime(date)).toBe('1 hour ago');
  });

  it('returns days for < 7 days ago', () => {
    const date = new Date('2026-02-05T12:00:00Z');
    expect(formatRelativeTime(date)).toBe('2 days ago');
  });

  it('returns singular day', () => {
    const date = new Date('2026-02-06T12:00:00Z');
    expect(formatRelativeTime(date)).toBe('1 day ago');
  });

  it('returns date string for >= 7 days ago', () => {
    const date = new Date('2026-01-20T12:00:00Z');
    const result = formatRelativeTime(date);
    // Should be a date string, not a relative time
    expect(result).not.toContain('ago');
    expect(result).not.toBe('just now');
  });
});

describe('transformLog', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-02-07T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('transforms a FileAccessLog to an ActivityItem', () => {
    const log: FileAccessLog = {
      timestamp: '2026-02-07T11:55:00Z',
      event_type: 'file_access',
      user: 'admin',
      action: 'upload',
      resource: '/documents/report.pdf',
      success: true,
      details: { size_bytes: 2048 },
    };

    const item = transformLog(log, 0);

    expect(item.id).toBe('2026-02-07T11:55:00Z-0');
    expect(item.title).toBe('File Uploaded');
    expect(item.icon).toBe('upload');
    expect(item.success).toBe(true);
    expect(item.detail).toContain('admin');
    expect(item.detail).toContain('report.pdf');
    expect(item.detail).toContain('KB');
    expect(item.ago).toBe('5 minutes ago');
  });

  it('handles logs without user or unknown user', () => {
    const log: FileAccessLog = {
      timestamp: '2026-02-07T11:55:00Z',
      event_type: 'file_access',
      user: 'unknown',
      action: 'download',
      resource: '/file.txt',
      success: true,
    };

    const item = transformLog(log, 1);
    // "unknown" user should not appear in detail
    expect(item.detail).not.toContain('unknown');
    expect(item.detail).toContain('file.txt');
  });

  it('handles logs without details.size_bytes', () => {
    const log: FileAccessLog = {
      timestamp: '2026-02-07T11:55:00Z',
      event_type: 'file_access',
      user: 'admin',
      action: 'delete',
      resource: '/old.txt',
      success: false,
    };

    const item = transformLog(log, 2);
    expect(item.success).toBe(false);
    expect(item.detail).not.toContain('KB');
  });
});
