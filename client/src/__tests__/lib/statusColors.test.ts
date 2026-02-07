import { describe, it, expect } from 'vitest';
import { getStatusClasses, inferStatusLevel } from '../../lib/statusColors';

describe('getStatusClasses', () => {
  it('returns emerald classes for success', () => {
    const classes = getStatusClasses('success');
    expect(classes).toContain('emerald');
  });

  it('returns amber classes for warning', () => {
    const classes = getStatusClasses('warning');
    expect(classes).toContain('amber');
  });

  it('returns rose classes for error', () => {
    const classes = getStatusClasses('error');
    expect(classes).toContain('rose');
  });

  it('returns sky classes for info', () => {
    const classes = getStatusClasses('info');
    expect(classes).toContain('sky');
  });

  it('returns slate classes for neutral', () => {
    const classes = getStatusClasses('neutral');
    expect(classes).toContain('slate');
  });
});

describe('inferStatusLevel', () => {
  it.each([
    ['clean', 'success'],
    ['optimal', 'success'],
    ['passed', 'success'],
    ['running', 'success'],
    ['active', 'success'],
    ['healthy', 'success'],
    ['ok', 'success'],
  ] as const)('maps "%s" to %s', (status, expected) => {
    expect(inferStatusLevel(status)).toBe(expected);
  });

  it.each([
    ['degraded', 'warning'],
    ['warning', 'warning'],
    ['rebuilding', 'warning'],
    ['write-mostly', 'warning'],
    ['disabled', 'warning'],
  ] as const)('maps "%s" to %s', (status, expected) => {
    expect(inferStatusLevel(status)).toBe(expected);
  });

  it.each([
    ['failed', 'error'],
    ['error', 'error'],
    ['critical', 'error'],
    ['removed', 'error'],
    ['inactive', 'error'],
  ] as const)('maps "%s" to %s', (status, expected) => {
    expect(inferStatusLevel(status)).toBe(expected);
  });

  it.each([
    ['syncing', 'info'],
    ['checking', 'info'],
    ['pending', 'info'],
  ] as const)('maps "%s" to %s', (status, expected) => {
    expect(inferStatusLevel(status)).toBe(expected);
  });

  it('returns neutral for unknown status', () => {
    expect(inferStatusLevel('something-else')).toBe('neutral');
  });

  it('is case-insensitive', () => {
    expect(inferStatusLevel('CLEAN')).toBe('success');
    expect(inferStatusLevel('Failed')).toBe('error');
    expect(inferStatusLevel('SYNCING')).toBe('info');
  });
});
