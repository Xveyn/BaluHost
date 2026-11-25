import { describe, it, expect, vi } from 'vitest';
import { hasHandoffFragment, takeHandoffCode } from '../../lib/sessionHandoff';

describe('hasHandoffFragment', () => {
  it('erkennt handoff= im Fragment', () => {
    expect(hasHandoffFragment('#handoff=abc')).toBe(true);
    expect(hasHandoffFragment('#x=1&handoff=abc')).toBe(true);
  });
  it('false ohne Fragment oder ohne Code', () => {
    expect(hasHandoffFragment('')).toBe(false);
    expect(hasHandoffFragment('#other=1')).toBe(false);
    expect(hasHandoffFragment('#handoff=')).toBe(false);
  });
});

describe('takeHandoffCode', () => {
  it('gibt den Code zurueck und entfernt das Fragment', () => {
    const replaceState = vi.fn();
    const code = takeHandoffCode(
      { hash: '#handoff=abc_-123', pathname: '/login', search: '?a=1' },
      { replaceState },
    );
    expect(code).toBe('abc_-123');
    expect(replaceState).toHaveBeenCalledWith(null, '', '/login?a=1');
  });
  it('ohne Fragment: null und kein replaceState', () => {
    const replaceState = vi.fn();
    expect(takeHandoffCode({ hash: '', pathname: '/login', search: '' }, { replaceState })).toBeNull();
    expect(replaceState).not.toHaveBeenCalled();
  });
  it('entfernt das Fragment auch bei leerem Code nicht ungefragt', () => {
    const replaceState = vi.fn();
    expect(takeHandoffCode({ hash: '#handoff=', pathname: '/login', search: '' }, { replaceState })).toBeNull();
    expect(replaceState).not.toHaveBeenCalled();
  });
});
