import { describe, it, expect } from 'vitest';
import { formatNetworkSpeed } from '../../hooks/useNetworkStatus';

describe('formatNetworkSpeed', () => {
  it('returns "0 Mbps" for 0', () => {
    expect(formatNetworkSpeed(0)).toBe('0 Mbps');
  });

  it('returns "0 Mbps" for very small values below threshold', () => {
    expect(formatNetworkSpeed(0.005)).toBe('0 Mbps');
  });

  it('formats sub-Mbps values as Kbps', () => {
    expect(formatNetworkSpeed(0.5)).toBe('500 Kbps');
  });

  it('formats moderate Mbps values with 1 decimal', () => {
    expect(formatNetworkSpeed(50)).toBe('50,0 Mbps');
  });

  it('formats high Mbps values without decimals', () => {
    expect(formatNetworkSpeed(500)).toBe('500 Mbps');
  });

  it('formats Gbps values', () => {
    expect(formatNetworkSpeed(2500)).toBe('2,50 Gbps');
  });
});
