import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

import { apiClient } from '../../lib/api';
import {
  getAudioState,
  setSinkVolume,
  setSinkMute,
  setDefaultSink,
  setStreamVolume,
  setStreamMute,
} from '../../api/audioControl';

describe('audioControl API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { sinks: [], streams: [], available: true, detail: null },
    });
    (apiClient.put as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { success: true } });
  });

  it('liest den Zustand von einer einzigen Route', async () => {
    const state = await getAudioState();
    expect(apiClient.get).toHaveBeenCalledWith('/api/plugins/audio_control/state');
    expect(state.available).toBe(true);
  });

  it('setzt den Geraetepegel', async () => {
    await setSinkVolume(61, 40);
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/sinks/61/volume', {
      percent: 40,
    });
  });

  it('setzt die Geraete-Stummschaltung', async () => {
    await setSinkMute(61, true);
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/sinks/61/mute', {
      muted: true,
    });
  });

  it('setzt das Standardgeraet', async () => {
    await setDefaultSink('alsa_output.test');
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/default-sink', {
      name: 'alsa_output.test',
    });
  });

  it('setzt den Streampegel', async () => {
    await setStreamVolume(789, 20);
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/streams/789/volume', {
      percent: 20,
    });
  });

  it('setzt die Stream-Stummschaltung', async () => {
    await setStreamMute(789, true);
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/streams/789/mute', {
      muted: true,
    });
  });
});
