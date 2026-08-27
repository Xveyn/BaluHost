import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

// Der Mock muss den Namensraum mit ausgeben, sonst liefert t('title') nur
// 'title' und die Erwartungen auf 'audio:title' schlagen fehl. Interpolations-
// Werte (z. B. {{app}}) muessen ebenfalls durchgereicht werden, sonst laesst
// sich die Unterscheidbarkeit der Pro-Stream-Beschriftungen gar nicht pruefen.
vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const values = options ? Object.values(options).join('/') : '';
      return values ? `${ns}:${key}:${values}` : `${ns}:${key}`;
    },
    i18n: { language: 'de' },
  }),
}));

vi.mock('../../../api/audioControl', () => ({
  getAudioState: vi.fn(),
  setSinkVolume: vi.fn().mockResolvedValue(undefined),
  setSinkMute: vi.fn().mockResolvedValue(undefined),
  setDefaultSink: vi.fn().mockResolvedValue(undefined),
  setStreamVolume: vi.fn().mockResolvedValue(undefined),
  setStreamMute: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../../api/powerPermissions', () => ({
  getMyPowerPermissions: vi.fn(),
}));

import { AudioMenu } from '../../../components/topbar/AudioMenu';
import { getAudioState, setSinkVolume } from '../../../api/audioControl';
import { getMyPowerPermissions } from '../../../api/powerPermissions';

const STATE = {
  available: true,
  detail: null,
  sinks: [
    {
      id: 61,
      name: 'onboard',
      description: 'Onboard Digital',
      volume_percent: 95,
      muted: false,
      is_default: true,
    },
    {
      id: 90,
      name: 'gpu',
      description: 'GPU HDMI',
      volume_percent: 100,
      muted: false,
      is_default: false,
    },
  ],
  streams: [
    {
      id: 789,
      sink_id: 61,
      application: 'Firefox',
      binary: 'firefox-esr',
      title: 'Ein sehr privater Videotitel',
      volume_percent: 55,
      muted: false,
      corked: false,
    },
  ],
};

const allowed = { can_control_audio: true };

beforeEach(() => {
  vi.clearAllMocks();
  (getMyPowerPermissions as ReturnType<typeof vi.fn>).mockResolvedValue(allowed);
  (getAudioState as ReturnType<typeof vi.fn>).mockResolvedValue(STATE);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('AudioMenu', () => {
  it('rendert nichts ohne die Berechtigung', async () => {
    (getMyPowerPermissions as ReturnType<typeof vi.fn>).mockResolvedValue({
      can_control_audio: false,
    });
    const { container } = render(<AudioMenu />);
    await waitFor(() => expect(getMyPowerPermissions).toHaveBeenCalled());
    expect(container.querySelector('button')).toBeNull();
  });

  it('zeigt den Knopf mit der Berechtigung', async () => {
    render(<AudioMenu />);
    expect(await screen.findByRole('button', { name: 'audio:title' })).toBeTruthy();
  });

  it('fragt den Zustand erst beim Oeffnen ab', async () => {
    render(<AudioMenu />);
    const button = await screen.findByRole('button', { name: 'audio:title' });
    expect(getAudioState).not.toHaveBeenCalled();

    fireEvent.click(button);
    await waitFor(() => expect(getAudioState).toHaveBeenCalledTimes(1));
  });

  it('zeigt die Anwendung, nicht den Titel', async () => {
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));

    expect(await screen.findByText('Firefox')).toBeTruthy();
    expect(screen.queryByText('Ein sehr privater Videotitel')).toBeNull();
  });

  it('meldet einen nicht erreichbaren Audio-Stack statt leerer Regler', async () => {
    (getAudioState as ReturnType<typeof vi.fn>).mockResolvedValue({
      available: false,
      detail: null,
      sinks: [],
      streams: [],
    });
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));

    expect(await screen.findByText('audio:unavailable')).toBeTruthy();
  });

  it('weist auf eine leere Stream-Liste hin', async () => {
    (getAudioState as ReturnType<typeof vi.fn>).mockResolvedValue({ ...STATE, streams: [] });
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));

    expect(await screen.findByText('audio:noStreams')).toBeTruthy();
  });

  it('entprellt den Regler auf eine einzige Anfrage', async () => {
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));
    const slider = await screen.findByLabelText('audio:sinkVolume');

    vi.useFakeTimers();
    fireEvent.change(slider, { target: { value: '40' } });
    fireEvent.change(slider, { target: { value: '41' } });
    fireEvent.change(slider, { target: { value: '42' } });
    vi.advanceTimersByTime(300);
    vi.useRealTimers();

    await waitFor(() => expect(setSinkVolume).toHaveBeenCalledTimes(1));
    expect(setSinkVolume).toHaveBeenCalledWith(61, 42);
  });

  it('unterbricht den Abruf nicht mitten in einer Ziehbewegung', async () => {
    render(<AudioMenu />);
    const button = await screen.findByRole('button', { name: 'audio:title' });

    vi.useFakeTimers();
    fireEvent.click(button);
    // Ersten Abruf abwarten (nicht Teil des Wettrennens) — bis der Regler im
    // DOM steht, ist auch der resultierende State-Update-Microtask geflusht.
    await vi.waitFor(() => expect(screen.getByLabelText('audio:sinkVolume')).toBeInTheDocument());
    expect(getAudioState).toHaveBeenCalledTimes(1);

    const slider = screen.getByLabelText('audio:sinkVolume');
    // Simuliert eine langsame Ziehbewegung: Change-Events alle 100ms — deutlich
    // unter der 200ms-Entprellzeit, aber ueber die 2s-Abrufmarke hinaus.
    for (let i = 0; i < 25; i++) {
      fireEvent.change(slider, { target: { value: String(40 + i) } });
      await vi.advanceTimersByTimeAsync(100);
    }

    // Der Poll-Tick bei 2000ms faellt mitten in eine laufende Entprellung —
    // er darf den alten Serverwert nicht ueber den Regler stuelpen.
    expect(getAudioState).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it('beschriftet Mute-Knopf und Regler je Stream unterscheidbar mit dem Anwendungsnamen', async () => {
    (getAudioState as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...STATE,
      streams: [
        ...STATE.streams,
        {
          id: 790,
          sink_id: 61,
          application: 'Spotify',
          binary: 'spotify',
          title: 'Ein Song',
          volume_percent: 30,
          muted: false,
          corked: false,
        },
      ],
    });
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));

    const firefoxMute = await screen.findByRole('button', { name: 'audio:muteApp:Firefox' });
    const spotifyMute = await screen.findByRole('button', { name: 'audio:muteApp:Spotify' });
    expect(firefoxMute).not.toBe(spotifyMute);

    expect(screen.getByLabelText('audio:streamVolume:Firefox')).toBeTruthy();
    expect(screen.getByLabelText('audio:streamVolume:Spotify')).toBeTruthy();
  });

  it('zeigt pausierte Streams im Text, nicht nur ueber Transparenz', async () => {
    (getAudioState as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...STATE,
      streams: [{ ...STATE.streams[0], corked: true }],
    });
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));

    expect(await screen.findByText('audio:paused', { exact: false })).toBeTruthy();
  });
});
