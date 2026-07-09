import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import type { HandshakeStatus, EnergyCurrent, PiSystem, SnapshotData } from '../../api/pi';

vi.mock('../../api/pi', () => ({
  getHandshakeStatus: vi.fn(),
  getPiEnergyCurrent: vi.fn(),
  getPiSystemStatus: vi.fn(),
  getHandshakeSnapshot: vi.fn(),
}));

import {
  getHandshakeStatus,
  getPiEnergyCurrent,
  getPiSystemStatus,
  getHandshakeSnapshot,
} from '../../api/pi';
import { usePiDashboardData } from '../../hooks/usePiDashboardData';

const handshakeMock = vi.mocked(getHandshakeStatus);
const energyMock = vi.mocked(getPiEnergyCurrent);
const systemMock = vi.mocked(getPiSystemStatus);
const snapshotMock = vi.mocked(getHandshakeSnapshot);

const handshake = { nas_state: 'online', since: null, last_snapshot: null, inbox_size_mb: 0, inbox_files: 2 } as HandshakeStatus;
const energy = { devices: [], total_power_w: 12.5 } as EnergyCurrent;
const piSystem = { cpu_percent: 10, memory_percent: 20, memory_used_mb: 1, memory_total_mb: 2, temperature_c: 40, uptime_seconds: 100, hostname: 'pi' } as PiSystem;
const snapshot = { baluhost_version: '1.0.0', storage: { arrays: [], total_bytes: 0, used_bytes: 0 } } as unknown as SnapshotData;

describe('usePiDashboardData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    handshakeMock.mockResolvedValue(handshake);
    energyMock.mockResolvedValue(energy);
    systemMock.mockResolvedValue(piSystem);
    snapshotMock.mockResolvedValue(snapshot);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns all four data slices when every endpoint succeeds', async () => {
    const { result } = renderHook(() => usePiDashboardData(), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.handshake).not.toBeNull();
      expect(result.current.snapshot).not.toBeNull();
    });

    expect(result.current.handshake?.inbox_files).toBe(2);
    expect(result.current.energy?.total_power_w).toBe(12.5);
    expect(result.current.piSystem?.hostname).toBe('pi');
    expect(result.current.snapshot?.baluhost_version).toBe('1.0.0');
  });

  it('keeps successful endpoints when one fails (independent queries)', async () => {
    handshakeMock.mockRejectedValue(new Error('handshake down'));

    const { result } = renderHook(() => usePiDashboardData(), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.piSystem).not.toBeNull();
    });

    // The failing endpoint yields null; the others still populate.
    expect(result.current.handshake).toBeNull();
    expect(result.current.energy?.total_power_w).toBe(12.5);
    expect(result.current.snapshot?.baluhost_version).toBe('1.0.0');
  });

  it('refetch() re-requests every endpoint', async () => {
    const { result } = renderHook(() => usePiDashboardData(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.handshake).not.toBeNull());
    expect(getHandshakeStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.refetch();
    });

    expect(getHandshakeStatus).toHaveBeenCalledTimes(2);
    expect(getPiEnergyCurrent).toHaveBeenCalledTimes(2);
    expect(getPiSystemStatus).toHaveBeenCalledTimes(2);
    expect(getHandshakeSnapshot).toHaveBeenCalledTimes(2);
  });

  it('polls every endpoint on the interval', async () => {
    vi.useFakeTimers();

    renderHook(() => usePiDashboardData(30000), { wrapper: createQueryWrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(getHandshakeStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(getHandshakeStatus).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });
});
