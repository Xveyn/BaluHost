import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const values = options ? Object.values(options).join('/') : '';
      return values ? `${ns}:${key}:${values}` : `${ns}:${key}`;
    },
    i18n: { language: 'de' },
  }),
}));

vi.mock('../../../api/displayOutput', async () => {
  const actual = await vi.importActual<typeof import('../../../api/displayOutput')>(
    '../../../api/displayOutput',
  );
  return {
    ...actual,
    getDisplayLayout: vi.fn(),
    applyDisplayLayout: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock('../../../api/powerPermissions', () => ({
  getMyPowerPermissions: vi.fn(),
}));

import { DisplayMenu } from '../../../components/topbar/DisplayMenu';
import { getDisplayLayout, applyDisplayLayout } from '../../../api/displayOutput';
import { getMyPowerPermissions } from '../../../api/powerPermissions';
import displayDe from '../../../i18n/locales/de/display.json';
import displayEn from '../../../i18n/locales/en/display.json';

const LAYOUT = {
  available: true,
  detail: null,
  displays_powered: false,
  outputs: [
    {
      name: 'HDMI-A-1', connected: true, selected: false, lit: false,
      current_mode_id: '1', preferred_mode_id: '1', scale: 1, priority: 0,
      modes: [{ id: '1', name: '2560x1440@144', width: 2560, height: 1440, refresh_rate: 143.999 }],
    },
    {
      name: 'DP-3', connected: true, selected: true, lit: false,
      current_mode_id: '57', preferred_mode_id: '56', scale: 2.5, priority: 1,
      modes: [
        { id: '57', name: '3840x2160@120', width: 3840, height: 2160, refresh_rate: 120 },
        { id: '58', name: '3840x2160@120', width: 3840, height: 2160, refresh_rate: 119.87999725 },
      ],
    },
  ],
};

beforeEach(() => {
  vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_displays: true } as never);
  vi.mocked(getDisplayLayout).mockResolvedValue(structuredClone(LAYOUT) as never);
});

async function open() {
  render(<DisplayMenu />);
  const button = await screen.findByLabelText('display:title');
  fireEvent.click(button);
  await waitFor(() => expect(getDisplayLayout).toHaveBeenCalled());
}

describe('DisplayMenu', () => {
  it('bleibt unsichtbar ohne das Recht', async () => {
    vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_displays: false } as never);
    const { container } = render(<DisplayMenu />);
    await waitFor(() => expect(getMyPowerPermissions).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it('fragt erst ab, wenn das Popover offen ist', async () => {
    render(<DisplayMenu />);
    await screen.findByLabelText('display:title');
    expect(getDisplayLayout).not.toHaveBeenCalled();
  });

  it('listet beide Ausgaenge', async () => {
    await open();
    expect(await screen.findByText('DP-3')).toBeTruthy();
    expect(screen.getByText('HDMI-A-1')).toBeTruthy();
  });

  it('zeigt gewaehlt und leuchtet als getrennte Aussagen', async () => {
    // Der mehrdeutige Zustand von BaluNode: KWin haelt DP-3 fuer gewaehlt,
    // DRM meldet dunkel. Beides muss sichtbar sein, sonst widerspricht sich
    // die Oberflaeche.
    await open();
    expect(screen.getAllByText('display:selected').length).toBe(1);
    expect(screen.getAllByText('display:dark').length).toBe(2);
  });

  it('unterscheidet die beiden namensgleichen 4K-Modi im Auswahlfeld', async () => {
    await open();
    const select = screen.getByLabelText('display:mode:DP-3') as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.textContent);
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels.some((l) => l?.includes('119,88'))).toBe(true);
  });

  it('schickt id und name zusammen', async () => {
    await open();
    const select = screen.getByLabelText('display:mode:DP-3') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: '58' } });
    fireEvent.click(screen.getByText('display:apply'));
    await waitFor(() => expect(applyDisplayLayout).toHaveBeenCalled());
    const wishes = vi.mocked(applyDisplayLayout).mock.calls[0][0];
    const dp3 = wishes.find((w) => w.name === 'DP-3');
    expect(dp3).toEqual({
      name: 'DP-3', selected: true, mode_id: '58', mode_name: '3840x2160@120',
    });
  });

  it('sperrt Anwenden, wenn nichts mehr gewaehlt waere', async () => {
    await open();
    fireEvent.click(screen.getByLabelText('display:outputs:DP-3'));
    const apply = screen.getByText('display:apply').closest('button') as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
  });

  it('meldet eine unerreichbare Sitzung statt einer leeren Liste', async () => {
    vi.mocked(getDisplayLayout).mockResolvedValue({
      ...LAYOUT, available: false, outputs: [],
    } as never);
    await open();
    expect(await screen.findByText('display:unavailable')).toBeTruthy();
  });

  it('zeigt das neutrale Monitor-Symbol vor dem ersten Laden, nicht "dunkel"', async () => {
    // Vor dem ersten Oeffnen wurde nie gefragt, ob etwas leuchtet - "dunkel"
    // zu behaupten waere hier dieselbe Falschaussage wie bei `lit === null`.
    const { container } = render(<DisplayMenu />);
    await screen.findByLabelText('display:title');
    expect(container.querySelector('.lucide-monitor-off')).toBeNull();
    expect(container.querySelector('.lucide-monitor')).toBeTruthy();
  });

  it('zeigt MonitorOff erst, nachdem ein geladenes Layout nichts Leuchtendes zeigt', async () => {
    // LAYOUT hat beide Ausgaenge mit lit: false - jetzt ist "dunkel"
    // tatsaechlich beantwortet, nicht nur unbekannt.
    const { container } = render(<DisplayMenu />);
    const button = await screen.findByLabelText('display:title');
    fireEvent.click(button);
    await waitFor(() => expect(getDisplayLayout).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector('.lucide-monitor-off')).toBeTruthy());
  });

  it('behaelt eine apply-Fehlermeldung ueber den naechsten Poll-Takt hinweg', async () => {
    vi.mocked(applyDisplayLayout).mockRejectedValueOnce({ response: { status: 500 } });
    render(<DisplayMenu />);
    const button = await screen.findByLabelText('display:title');

    // Die Fake-Timer MUESSEN vor dem Oeffnen aktiv sein: das Poll-Intervall
    // wird beim Oeffnen aufgesetzt und lebt sonst auf der echten Uhr weiter,
    // egal wie weit `advanceTimersByTimeAsync` danach vorspult.
    vi.useFakeTimers();
    fireEvent.click(button);
    await vi.waitFor(() => expect(screen.getByText('DP-3')).toBeInTheDocument());

    fireEvent.click(screen.getByText('display:apply'));
    await vi.waitFor(() => expect(applyDisplayLayout).toHaveBeenCalled());
    await vi.waitFor(() => expect(screen.getByText('display:saveError')).toBeInTheDocument());

    // Ein weiterer Poll-Takt (POLL_MS = 5000) laeuft erfolgreich durch und
    // darf die Fehlermeldung nicht loeschen - genau der Fehler, den dieser
    // Fix behebt (refresh() loeschte frueher jeden Fehler, nicht nur seinen
    // eigenen).
    await vi.advanceTimersByTimeAsync(5000);

    expect(screen.getByText('display:saveError')).toBeTruthy();
    vi.useRealTimers();
  });
});

describe('display i18n locale contract', () => {
  // Der react-i18next-Mock oben kann diesen Fehler grundsaetzlich nicht
  // fangen: er baut den Anzeigetext IMMER aus `options` zusammen, egal ob der
  // echte Uebersetzungsstring ueberhaupt einen {{output}}-Platzhalter hat.
  // Echtes react-i18next ignoriert eine Interpolation ohne passenden
  // Platzhalter dagegen lautlos — jedes Auswahlfeld haette denselben
  // aria-label-Text, zwei Formularelemente waeren fuer einen Screenreader
  // ununterscheidbar. Nur ein Test gegen die echten JSON-Dateien deckt das
  // auf.
  it('mode-Label traegt den {{output}}-Platzhalter in beiden Sprachen', () => {
    expect(displayDe.mode).toContain('{{output}}');
    expect(displayEn.mode).toContain('{{output}}');
  });
});
