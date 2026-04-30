import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import * as api from '../../api/monitoring';
import { useGpuPresence, __resetGpuPresenceCache } from '../../hooks/useGpuPresence';

vi.mock('../../api/monitoring');

describe('useGpuPresence', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    __resetGpuPresenceCache();
  });

  it('returns present:true with info when /gpu/info returns data', async () => {
    (api.getGpuInfo as any).mockResolvedValue({
      vendor: 'amd', device_name: 'AMD Radeon RX 7900 XT',
      pci_slot: '0000:03:00.0', vram_total_bytes: 21474836480, driver_version: null,
    });

    const { result } = renderHook(() => useGpuPresence());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.present).toBe(true);
    expect(result.current.info?.device_name).toContain('7900 XT');
  });

  it('returns present:false when /gpu/info returns null (404)', async () => {
    (api.getGpuInfo as any).mockResolvedValue(null);
    const { result } = renderHook(() => useGpuPresence());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.present).toBe(false);
    expect(result.current.info).toBeNull();
  });
});
