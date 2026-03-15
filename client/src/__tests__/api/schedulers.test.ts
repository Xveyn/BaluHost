import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  formatDuration,
  formatInterval,
  formatRelativeTime,
  getStatusColor,
  getStatusBadgeClasses,
  getSchedulerIcon,
  parseResultSummary,
  groupExecutionsByHour,
  SchedulerExecStatus,
  type SchedulerExecution,
} from '../../api/schedulers';

// --- Helper functions (pure, no API calls) ---

describe('formatDuration', () => {
  it('returns "-" for null', () => {
    expect(formatDuration(null)).toBe('-');
  });

  it('formats milliseconds', () => {
    expect(formatDuration(500)).toBe('500ms');
    expect(formatDuration(0)).toBe('0ms');
  });

  it('formats seconds', () => {
    expect(formatDuration(1500)).toContain('s');
    expect(formatDuration(30000)).toContain('s');
  });

  it('formats minutes', () => {
    expect(formatDuration(90000)).toContain('min');
  });

  it('formats hours', () => {
    expect(formatDuration(3700000)).toContain('h');
  });
});

describe('formatInterval', () => {
  it('formats seconds', () => {
    expect(formatInterval(30)).toBe('Every 30s');
  });

  it('formats single minute', () => {
    expect(formatInterval(60)).toBe('Every minute');
  });

  it('formats multiple minutes', () => {
    expect(formatInterval(300)).toBe('Every 5 min');
  });

  it('formats single hour', () => {
    expect(formatInterval(3600)).toBe('Every hour');
  });

  it('formats multiple hours', () => {
    expect(formatInterval(7200)).toBe('Every 2h');
  });

  it('formats single day', () => {
    expect(formatInterval(86400)).toBe('Daily');
  });

  it('formats multiple days', () => {
    expect(formatInterval(172800)).toBe('Every 2 days');
  });
});

describe('formatRelativeTime', () => {
  it('returns "-" for null', () => {
    expect(formatRelativeTime(null)).toBe('-');
  });

  it('returns "just now" for recent past', () => {
    const now = new Date();
    now.setSeconds(now.getSeconds() - 5);
    expect(formatRelativeTime(now.toISOString())).toBe('just now');
  });

  it('returns minutes ago', () => {
    const date = new Date();
    date.setMinutes(date.getMinutes() - 10);
    expect(formatRelativeTime(date.toISOString())).toBe('10m ago');
  });

  it('returns hours ago', () => {
    const date = new Date();
    date.setHours(date.getHours() - 3);
    expect(formatRelativeTime(date.toISOString())).toBe('3h ago');
  });

  it('returns days ago', () => {
    const date = new Date();
    date.setDate(date.getDate() - 2);
    expect(formatRelativeTime(date.toISOString())).toBe('2d ago');
  });

  it('returns future time with "in" prefix', () => {
    const date = new Date();
    date.setHours(date.getHours() + 2);
    expect(formatRelativeTime(date.toISOString())).toBe('in 2h');
  });
});

describe('getStatusColor', () => {
  it('returns correct colors for each status', () => {
    expect(getStatusColor(SchedulerExecStatus.REQUESTED)).toContain('amber');
    expect(getStatusColor(SchedulerExecStatus.RUNNING)).toContain('blue');
    expect(getStatusColor(SchedulerExecStatus.COMPLETED)).toContain('green');
    expect(getStatusColor(SchedulerExecStatus.FAILED)).toContain('red');
    expect(getStatusColor(SchedulerExecStatus.CANCELLED)).toContain('yellow');
  });

  it('returns gray for null', () => {
    expect(getStatusColor(null)).toContain('gray');
  });
});

describe('getStatusBadgeClasses', () => {
  it('returns bg + text classes for each status', () => {
    const classes = getStatusBadgeClasses(SchedulerExecStatus.COMPLETED);
    expect(classes).toContain('bg-green');
    expect(classes).toContain('text-green');
  });

  it('returns gray for null', () => {
    const classes = getStatusBadgeClasses(null);
    expect(classes).toContain('bg-gray');
  });
});

describe('getSchedulerIcon', () => {
  it('returns specific icons for known schedulers', () => {
    expect(getSchedulerIcon('raid_scrub')).toBe('💾');
    expect(getSchedulerIcon('smart_scan')).toBe('🔍');
    expect(getSchedulerIcon('backup')).toBe('📦');
  });

  it('returns clock for unknown scheduler', () => {
    expect(getSchedulerIcon('unknown_thing')).toBe('⏰');
  });
});

describe('parseResultSummary', () => {
  it('returns null for null input', () => {
    expect(parseResultSummary(null)).toBeNull();
  });

  it('parses valid JSON', () => {
    expect(parseResultSummary('{"count": 5}')).toEqual({ count: 5 });
  });

  it('returns null for invalid JSON', () => {
    expect(parseResultSummary('not json')).toBeNull();
  });
});

describe('groupExecutionsByHour', () => {
  it('returns 24 hour buckets', () => {
    const result = groupExecutionsByHour([]);
    expect(result).toHaveLength(24);
  });

  it('each bucket has required fields', () => {
    const result = groupExecutionsByHour([]);
    result.forEach(bucket => {
      expect(bucket).toHaveProperty('hour');
      expect(bucket).toHaveProperty('executions');
      expect(bucket).toHaveProperty('completedCount');
      expect(bucket).toHaveProperty('failedCount');
      expect(bucket).toHaveProperty('runningCount');
    });
  });

  it('groups executions into the correct hour', () => {
    const now = new Date();
    const execution: SchedulerExecution = {
      id: 1,
      scheduler_name: 'backup',
      job_id: null,
      started_at: now.toISOString(),
      completed_at: now.toISOString(),
      status: 'completed',
      trigger_type: 'scheduled',
      result_summary: null,
      error_message: null,
      user_id: null,
      duration_ms: 500,
      duration_display: '500ms',
    };

    const result = groupExecutionsByHour([execution]);
    const totalExecs = result.reduce((sum, b) => sum + b.executions.length, 0);
    expect(totalExecs).toBe(1);

    const bucketWithExec = result.find(b => b.executions.length > 0);
    expect(bucketWithExec?.completedCount).toBe(1);
  });
});
