import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import { apiClient } from '../../lib/api';
import {
  answerPairing,
  cancelPairing,
  connectDevice,
  getBluetoothState,
  getPairingSession,
  removeDevice,
  setAdapterPowered,
  startPairing,
  startScan,
} from '../../api/bluetooth';

const BASE = '/api/plugins/bluetooth';
const get = apiClient.get as ReturnType<typeof vi.fn>;
const post = apiClient.post as ReturnType<typeof vi.fn>;
const del = apiClient.delete as ReturnType<typeof vi.fn>;

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  del.mockReset();
  post.mockResolvedValue({ data: { success: true } });
  del.mockResolvedValue({ data: { success: true } });
});

describe('bluetooth api', () => {
  it('liest den Zustand', async () => {
    get.mockResolvedValue({ data: { available: true } });
    expect(await getBluetoothState()).toEqual({ available: true });
    expect(get).toHaveBeenCalledWith(`${BASE}/state`);
  });

  it('schaltet den Adapter', async () => {
    await setAdapterPowered(false);
    expect(post).toHaveBeenCalledWith(`${BASE}/adapter/power`, { powered: false });
  });

  it('liefert das Scan-Ende', async () => {
    post.mockResolvedValue({ data: { until: '2026-09-11T12:00:30Z' } });
    expect(await startScan()).toBe('2026-09-11T12:00:30Z');
  });

  it('kodiert die Adresse im Pfad', async () => {
    await connectDevice('AA:BB:CC:DD:EE:0F');
    expect(post).toHaveBeenCalledWith(`${BASE}/devices/AA%3ABB%3ACC%3ADD%3AEE%3A0F/connect`);
    await removeDevice('AA:BB:CC:DD:EE:0F');
    expect(del).toHaveBeenCalledWith(`${BASE}/devices/AA%3ABB%3ACC%3ADD%3AEE%3A0F`);
  });

  it('startet eine Kopplung und liefert die Sitzung', async () => {
    post.mockResolvedValue({ data: { session_id: 'abc' } });
    expect(await startPairing('AA:BB:CC:DD:EE:0F')).toBe('abc');
  });

  it('liest die eigene Sitzung, auch null', async () => {
    get.mockResolvedValue({ data: null });
    expect(await getPairingSession()).toBeNull();
    expect(get).toHaveBeenCalledWith(`${BASE}/pairing`);
  });

  it('beantwortet und bricht ab', async () => {
    await answerPairing('abc', true);
    expect(post).toHaveBeenCalledWith(`${BASE}/pairing/abc/confirm`, { accept: true });
    await cancelPairing('abc');
    expect(post).toHaveBeenCalledWith(`${BASE}/pairing/abc/cancel`);
  });
});
