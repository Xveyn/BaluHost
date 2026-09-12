import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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
  // Weder vite.config.ts noch setup.ts setzen `clearMocks`, die Zaehler
  // ueberleben also den einzelnen Test. Ohne das hier misst jede Aussage der
  // Form "genau einmal abgefragt" die Aufrufe aller vorherigen Tests mit.
  vi.clearAllMocks();
  vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_displays: true } as never);
  vi.mocked(getDisplayLayout).mockResolvedValue(structuredClone(LAYOUT) as never);
});

// setup.ts hat keinen aequivalenten globalen Hook. Muss unconditional laufen,
// nicht erst nach der letzten Assertion eines Fake-Timer-Tests — sonst
// ueberlebt ein Fehlschlag dort die Umstellung und faelscht jeden Timer in
// den danach laufenden Tests dieser Datei.
afterEach(() => {
  vi.useRealTimers();
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

  it('fragt einmal beim Mounten ab, damit das Symbol nicht raet', async () => {
    // Frueher wurde erst beim Oeffnen gefragt. Dadurch behauptete das Symbol
    // nach jedem Seitenaufbau "an", bis jemand einmal geklickt hatte.
    render(<DisplayMenu />);
    await screen.findByLabelText('display:title');
    await waitFor(() => expect(getDisplayLayout).toHaveBeenCalledTimes(1));
  });

  it('pollt nicht weiter, solange das Popover zu bleibt', async () => {
    // Der eine Abruf beim Mounten ersetzt kein Hintergrund-Polling: eine
    // Fernbedienung, die im Hintergrund taktet, kostet Anfragen ohne Wert.
    render(<DisplayMenu />);
    await screen.findByLabelText('display:title');
    await waitFor(() => expect(getDisplayLayout).toHaveBeenCalledTimes(1));
    vi.useFakeTimers();
    await vi.advanceTimersByTimeAsync(30000);
    expect(getDisplayLayout).toHaveBeenCalledTimes(1);
  });

  it('fragt nichts ab ohne das Recht', async () => {
    // Sonst feuert jeder Nutzer ohne Recht bei jedem Seitenaufbau eine
    // Anfrage, die nur mit 403 zurueckkommt.
    vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_displays: false } as never);
    render(<DisplayMenu />);
    await waitFor(() => expect(getMyPowerPermissions).toHaveBeenCalled());
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

  it('zeichnet das Symbol gedaempft, solange der Zustand unbekannt ist', async () => {
    // Vor der ersten Antwort ist "leuchtet" nicht beantwortet, sondern noch
    // nicht gefragt. `Monitor` allein ist dafuer nicht neutral - es ist das
    // An-Symbol. Die Daempfung macht den Unterschied sichtbar.
    let resolveLayout: (value: unknown) => void = () => {};
    vi.mocked(getDisplayLayout).mockReturnValue(
      new Promise((resolve) => {
        resolveLayout = resolve;
      }) as never,
    );
    const { container } = render(<DisplayMenu />);
    await screen.findByLabelText('display:title');
    expect(container.querySelector('.lucide-monitor')?.getAttribute('class')).toContain('opacity-40');
    resolveLayout(structuredClone(LAYOUT));
    await waitFor(() =>
      expect(container.querySelector('.lucide-monitor-off')?.getAttribute('class')).not.toContain(
        'opacity-40',
      ),
    );
  });

  it('zeigt MonitorOff ohne Klick, sobald das Layout nichts Leuchtendes meldet', async () => {
    // LAYOUT hat beide Ausgaenge mit lit: false. Frueher blieb das Symbol
    // bis zum ersten Oeffnen auf "an" stehen - genau der gemeldete Fehler.
    const { container } = render(<DisplayMenu />);
    await screen.findByLabelText('display:title');
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

  it('raeumt eine apply-Fehlermeldung beim erneuten Oeffnen aus', async () => {
    vi.mocked(applyDisplayLayout).mockRejectedValueOnce({ response: { status: 500 } });
    render(<DisplayMenu />);
    const button = await screen.findByLabelText('display:title');

    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText('DP-3')).toBeInTheDocument());

    fireEvent.click(screen.getByText('display:apply'));
    await waitFor(() => expect(applyDisplayLayout).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText('display:saveError')).toBeInTheDocument());

    // Schliessen (Klick auf den Trigger-Button toggelt isOpen)...
    fireEvent.click(button);
    // ...und wieder oeffnen: eine Interaktion, von der der Nutzer laengst
    // weg ist, darf im frisch geoeffneten Popover nicht mehr auftauchen.
    fireEvent.click(button);
    await waitFor(() => expect(screen.queryByText('display:saveError')).toBeNull());
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
