import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

// Der Mock muss den Namensraum mit ausgeben, sonst liefert t('title') nur
// 'title' und die Erwartungen auf 'audio:title' schlagen fehl.
vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string) => `${ns}:${key}`,
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
});
