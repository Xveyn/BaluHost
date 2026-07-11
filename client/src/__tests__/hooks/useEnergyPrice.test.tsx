import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/energy', () => ({ getEnergyPriceConfig: vi.fn(), updateEnergyPriceConfig: vi.fn() }));

import toast from 'react-hot-toast';
import { getEnergyPriceConfig, updateEnergyPriceConfig } from '../../api/energy';
import { useEnergyPrice } from '../../hooks/useEnergyPrice';

const cfg = { id: 1, cost_per_kwh: 0.3, currency: 'EUR', updated_at: '', updated_by_user_id: null };

beforeEach(() => {
  vi.clearAllMocks();
  (getEnergyPriceConfig as any).mockResolvedValue(cfg);
  (updateEnergyPriceConfig as any).mockResolvedValue({ ...cfg, cost_per_kwh: 0.4 });
});

describe('useEnergyPrice', () => {
  it('seeds config on mount', async () => {
    const { result } = renderHook(() => useEnergyPrice());
    await waitFor(() => expect(result.current.priceConfig?.cost_per_kwh).toBe(0.3));
    expect(result.current.priceInput).toBe('0.3');
  });

  it('rejects out-of-range price (no update, error toast)', async () => {
    const { result } = renderHook(() => useEnergyPrice());
    await waitFor(() => expect(result.current.priceConfig).not.toBeNull());
    act(() => result.current.setPriceInput('99'));
    await act(async () => { await result.current.savePrice(); });
    expect(updateEnergyPriceConfig).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalled();
  });

  it('saves in-range price and calls onSaved', async () => {
    const onSaved = vi.fn();
    const { result } = renderHook(() => useEnergyPrice(onSaved));
    await waitFor(() => expect(result.current.priceConfig).not.toBeNull());
    act(() => result.current.setPriceInput('0.4'));
    await act(async () => { await result.current.savePrice(); });
    expect(updateEnergyPriceConfig).toHaveBeenCalledWith({ cost_per_kwh: 0.4, currency: 'EUR' });
    expect(onSaved).toHaveBeenCalled();
  });
});
