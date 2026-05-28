import { describe, it, expect } from 'vitest';
import { resolveIcon } from '../../../components/topbar/iconMap';

describe('resolveIcon', () => {
  it('returns a component for a known icon name', () => {
    expect(resolveIcon('Zap')).toBeTruthy();
  });
  it('returns null for unknown / null', () => {
    expect(resolveIcon(null)).toBeNull();
    expect(resolveIcon('NotAnIcon')).toBeNull();
  });
});
