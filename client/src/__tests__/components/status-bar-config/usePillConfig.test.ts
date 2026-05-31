import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { Mock } from 'vitest';

vi.mock('../../../api/statusBar', () => ({
  getStatusBarConfig: vi.fn(),
  updateStatusBarConfig: vi.fn(),
}));

import { getStatusBarConfig, updateStatusBarConfig } from '../../../api/statusBar';
import { usePillConfig } from '../../../components/status-bar-config/usePillConfig';

const sample = {
  pills: [
    { pill_id: 'power', name_key: 'statusBar.pills.power.name', enabled: false, visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x', display_mode: 'always', display_mode_configurable: false },
    { pill_id: 'raid', name_key: 'statusBar.pills.raid.name', enabled: false, visibility: 'admin', visibility_locked: true, sort_order: 1, href: '/y', display_mode: 'always', display_mode_configurable: false },
    { pill_id: 'desktop', name_key: 'statusBar.pills.desktop.name', enabled: false, visibility: 'admin', visibility_locked: false, sort_order: 2, href: '/z', display_mode: 'always', display_mode_configurable: true },
  ],
  show_bottom_upload: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  (getStatusBarConfig as any).mockResolvedValue(structuredClone(sample));
  (updateStatusBarConfig as any).mockResolvedValue(structuredClone(sample));
});

describe('usePillConfig', () => {
  it('loads config on mount', async () => {
    const { result } = renderHook(() => usePillConfig());
    await waitFor(() => expect(result.current.pills).toHaveLength(3));
    expect(result.current.showBottomUpload).toBe(true);
  });

  it('toggles enabled locally', async () => {
    const { result } = renderHook(() => usePillConfig());
    await waitFor(() => expect(result.current.pills).toHaveLength(3));
    act(() => result.current.setEnabled('power', true));
    expect(result.current.pills.find(p => p.pill_id === 'power')!.enabled).toBe(true);
  });

  it('save() PUTs current local state', async () => {
    const { result } = renderHook(() => usePillConfig());
    await waitFor(() => expect(result.current.pills).toHaveLength(3));
    act(() => result.current.setEnabled('power', true));
    await act(async () => { await result.current.save(); });
    expect(updateStatusBarConfig).toHaveBeenCalledTimes(1);
    const payload = (updateStatusBarConfig as any).mock.calls[0][0];
    expect(payload.pills.find((p: any) => p.pill_id === 'power').enabled).toBe(true);
  });

  it('includes display_mode in the save payload and setDisplayMode updates it', async () => {
    const { result } = renderHook(() => usePillConfig());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setDisplayMode('desktop', 'when_off'));
    await act(async () => { await result.current.save(); });
    const payload = (updateStatusBarConfig as Mock).mock.calls[0][0];
    const desktop = payload.pills.find((p: any) => p.pill_id === 'desktop');
    expect(desktop.display_mode).toBe('when_off');
    expect(payload.pills.every((p: any) => typeof p.display_mode === 'string')).toBe(true);
  });
});
