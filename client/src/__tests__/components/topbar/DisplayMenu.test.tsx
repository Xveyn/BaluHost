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
    setDisplayBrightness: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock('../../../api/powerPermissions', () => ({
  getMyPowerPermissions: vi.fn(),
}));

import { DisplayMenu } from '../../../components/topbar/DisplayMenu';
import {
  applyDisplayLayout,
  getDisplayLayout,
  setDisplayBrightness,
} from '../../../api/displayOutput';
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
  // Genau EIN Helligkeitsobjekt bei zwei Ausgaengen — so hat powerdevil es auf
  // BaluNode gemeldet. Die Objekt-ID ist kein Connector-Name.
  brightness: {
    available: true,
    detail: null,
    displays: [{ id: 'display13', label: 'Example XY27', internal: false, percent: 100 }],
  },
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

describe('DisplayMenu Helligkeit', () => {
  const slider = () =>
    screen.getByLabelText('display:brightnessFor:Example XY27') as HTMLInputElement;

  it('zeigt einen Regler je steuerbaren Bildschirm, nicht je Ausgang', async () => {
    // Zwei Ausgaenge, ein Regler: powerdevil fuehrt nur eingeschaltete,
    // steuerbare Bildschirme, und die Zuordnung zu einem Connector gibt die
    // Schnittstelle nicht her.
    await open();
    expect(screen.getAllByRole('slider').length).toBe(1);
    expect(slider().value).toBe('100');
    expect(screen.getByText('Example XY27')).toBeTruthy();
  });

  it('laesst den Bildschirm nicht auf null drehen', async () => {
    // Die Untergrenze ist die Zusage an den Menschen am Schreibtisch: die
    // Weboberflaeche darf ihn nicht vor einem schwarzen Bildschirm sitzen
    // lassen. Das Backend lehnt 0 ohnehin mit 422 ab.
    await open();
    expect(slider().min).toBe('5');
    expect(slider().max).toBe('100');
  });

  it('zeigt den neuen Wert sofort, bevor der Server geantwortet hat', async () => {
    await open();
    fireEvent.change(slider(), { target: { value: '60' } });
    // Ohne optimistische Anzeige springt der Regler unter dem Finger zurueck.
    expect(slider().value).toBe('60');
    expect(screen.getByText('60 %')).toBeTruthy();
  });

  it('schickt einen Reglerwert erst nach der Entprellung', async () => {
    await open();
    vi.useFakeTimers();
    fireEvent.change(slider(), { target: { value: '60' } });
    expect(setDisplayBrightness).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(250);
    expect(setDisplayBrightness).toHaveBeenCalledTimes(1);
    expect(setDisplayBrightness).toHaveBeenCalledWith('display13', 60);
  });

  it('verwirft die Zwischenschritte einer Reglerbewegung', async () => {
    // Ein Ziehen erzeugt Dutzende Aenderungen. Ohne Verwerfen wird daraus ein
    // Dutzend D-Bus-Aufrufe, und das Limit von 60/min ist in Sekunden leer.
    await open();
    vi.useFakeTimers();
    fireEvent.change(slider(), { target: { value: '80' } });
    fireEvent.change(slider(), { target: { value: '70' } });
    fireEvent.change(slider(), { target: { value: '55' } });
    await vi.advanceTimersByTimeAsync(250);
    expect(setDisplayBrightness).toHaveBeenCalledTimes(1);
    expect(setDisplayBrightness).toHaveBeenCalledWith('display13', 55);
  });

  it('laesst den Poll-Takt aus, solange eine Reglerbewegung aussteht', async () => {
    // Sonst holt der Takt den alten Serverwert und der Regler springt mitten
    // im Ziehen zurueck.
    //
    // Die Zeiten sind der Gegenstand des Tests, nicht Beiwerk: der Poll-Takt
    // liegt bei 5000 ms, die Entprellung bei 200 ms. Eine Bewegung bei 4900 ms
    // ist bei 5000 ms also noch offen — genau dann MUSS der Takt aussetzen.
    // Spult man stattdessen erst 5000 ms weiter und bewegt dann, ist die
    // Entprellung beim naechsten Takt laengst durch und der Test misst nichts.
    render(<DisplayMenu />);
    const button = await screen.findByLabelText('display:title');
    vi.useFakeTimers();
    fireEvent.click(button);
    await vi.waitFor(() => expect(screen.getByText('DP-3')).toBeInTheDocument());
    const callsBefore = vi.mocked(getDisplayLayout).mock.calls.length;

    await vi.advanceTimersByTimeAsync(4900);
    fireEvent.change(slider(), { target: { value: '40' } });
    // Ueber den Takt bei 5000 ms hinweg, aber vor der Entprellung bei 5100 ms.
    await vi.advanceTimersByTimeAsync(150);
    expect(vi.mocked(getDisplayLayout).mock.calls.length).toBe(callsBefore);

    // Und danach holt der Schreibvorgang den frischen Zustand selbst.
    await vi.advanceTimersByTimeAsync(100);
    expect(setDisplayBrightness).toHaveBeenCalledWith('display13', 40);
    expect(vi.mocked(getDisplayLayout).mock.calls.length).toBe(callsBefore + 1);
  });

  it('meldet, wenn kein Bildschirm steuerbar ist', async () => {
    vi.mocked(getDisplayLayout).mockResolvedValue({
      ...structuredClone(LAYOUT),
      brightness: { available: true, detail: null, displays: [] },
    } as never);
    await open();
    expect(await screen.findByText('display:noBrightness')).toBeTruthy();
    expect(screen.queryAllByRole('slider').length).toBe(0);
  });

  it('unterscheidet den unerreichbaren Dienst von der leeren Liste', async () => {
    // Zwei verschiedene Aussagen: "powerdevil antwortet nicht" ist nicht
    // dasselbe wie "es gibt nichts zu regeln".
    vi.mocked(getDisplayLayout).mockResolvedValue({
      ...structuredClone(LAYOUT),
      brightness: { available: false, detail: null, displays: [] },
    } as never);
    await open();
    expect(await screen.findByText('display:brightnessUnavailable')).toBeTruthy();
    expect(screen.queryByText('display:noBrightness')).toBeNull();
  });

  it('meldet einen fehlgeschlagenen Schreibvorgang', async () => {
    vi.mocked(setDisplayBrightness).mockRejectedValueOnce({ response: { status: 502 } });
    await open();
    vi.useFakeTimers();
    fireEvent.change(slider(), { target: { value: '60' } });
    await vi.advanceTimersByTimeAsync(250);
    await vi.waitFor(() =>
      expect(screen.getByText('display:brightnessError')).toBeInTheDocument(),
    );
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

  it('brightnessFor-Label traegt den {{display}}-Platzhalter in beiden Sprachen', () => {
    // Dieselbe Falle wie oben: mehrere Regler mit identischem aria-label sind
    // fuer einen Screenreader ununterscheidbar, und der Mock kann das nicht
    // sehen.
    expect(displayDe.brightnessFor).toContain('{{display}}');
    expect(displayEn.brightnessFor).toContain('{{display}}');
  });
});
