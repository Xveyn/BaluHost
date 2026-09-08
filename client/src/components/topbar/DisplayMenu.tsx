/**
 * Displaysteuerung in der Topbar.
 *
 * Zeigt ein Monitor-Symbol; im Popover steht pro Ausgang die KWin-Wahl und
 * ein Auswahlfeld für den Video-Modus.
 *
 * Drei Eigenheiten, die Absicht sind:
 * - Der Zustand wird nur abgefragt, solange das Popover offen ist. Eine
 *   Fernbedienung, die im Hintergrund pollt, kostet Anfragen ohne Gegenwert.
 * - „gewählt" (KWin) und „leuchtet" (DRM) sind getrennte Aussagen. Beides in
 *   ein Abzeichen zu falten, ist die Verwechslung, die dieses Feature auflöst.
 * - Der globale Ein/Aus-Schalter fehlt bewusst: er steht zwei Symbole weiter
 *   im Systemmenü, und zwei Komponenten für denselben Zustand driften.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Monitor, MonitorOff } from 'lucide-react';
import {
  applyDisplayLayout,
  formatMode,
  getDisplayLayout,
  type DisplayLayout,
  type DisplayOutputWish,
} from '../../api/displayOutput';
import { getMyPowerPermissions } from '../../api/powerPermissions';

/** Abfragetakt, solange das Popover offen ist. */
const POLL_MS = 5000;

/** Der bearbeitete Wunsch je Ausgang, bevor „Anwenden" ihn abschickt. */
interface Draft {
  selected: boolean;
  modeId: string | null;
}

/**
 * i18n-Schlüssel statt übersetztem Text: `error` überlebt so einen
 * Sprachwechsel, während das Popover offen bleibt — übersetzt wird erst beim
 * Rendern (`t(error)`), nie beim Setzen.
 */
type ErrorKey = 'loadError' | 'saveError' | 'conflictError';

export function DisplayMenu() {
  const { t, i18n } = useTranslation('display');
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [layout, setLayout] = useState<DisplayLayout | null>(null);
  const [draft, setDraft] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);
  const dirty = useRef(false);

  useEffect(() => {
    let active = true;
    getMyPowerPermissions()
      .then((perms) => active && setAllowed(perms.can_manage_displays))
      .catch(() => active && setAllowed(false));
    return () => {
      active = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    // Läuft noch eine Antwort, wird übersprungen — sonst stauen sich bei
    // langsamer Verbindung die Anfragen.
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const next = await getDisplayLayout();
      setLayout(next);
      // Einen angefangenen Entwurf NICHT überschreiben — sonst springt die
      // Auswahl beim nächsten Takt auf den Serverwert zurück.
      if (!dirty.current) {
        setDraft(
          Object.fromEntries(
            next.outputs.map((o) => [o.name, { selected: o.selected, modeId: o.current_mode_id }]),
          ),
        );
      }
      // Nur den eigenen Fehler löschen: eine apply-Fehlermeldung
      // (saveError/conflictError) soll bis zur nächsten Nutzeraktion stehen
      // bleiben, nicht beim nächsten Poll-Takt verschwinden — sonst würde
      // dieser refresh() genau die Meldung wieder wegwischen, die handleApply
      // absichtlich erst nach dem Refetch gesetzt hat.
      setError((prev) => (prev === 'loadError' ? null : prev));
    } catch {
      setError('loadError');
    } finally {
      inFlight.current = false;
    }
    // Leere Deps sind hier Absicht, nicht Nachlässigkeit: refresh() muss über
    // Renders hinweg dieselbe Identität behalten, weil der Poll-Effekt weiter
    // unten (deps [isOpen, refresh]) sonst bei jedem Render das Intervall
    // abbaut und sofort neu aufsetzt — inklusive eines sofortigen erneuten
    // refresh()-Aufrufs, der wiederum einen Render auslöst. Genau das hat den
    // Test-Worker in eine Endlosschleife gehängt, als hier noch `t()`
    // aufgerufen wurde: react-i18next liefert `t` zwar pro Sprache stabil,
    // aber unter dem Test-Mock ändert sich die Identität bei jedem Render —
    // deshalb lebt der Fehlertext jetzt nur als Schlüssel (siehe `ErrorKey`)
    // und wird erst beim Rendern übersetzt, nie hier drin.
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    void refresh();
    const id = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(id);
  }, [isOpen, refresh]);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        dirty.current = false;
      }
    };
    if (isOpen) document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [isOpen]);

  const wishes: DisplayOutputWish[] = useMemo(() => {
    if (!layout) return [];
    return layout.outputs.map((output) => {
      const entry = draft[output.name] ?? { selected: output.selected, modeId: output.current_mode_id };
      const mode = output.modes.find((m) => m.id === entry.modeId);
      const wish: DisplayOutputWish = { name: output.name, selected: entry.selected };
      // id und name reisen immer gemeinsam — das Backend lehnt eine einzelne
      // Hälfte ab, weil die Gegenprobe sonst abschaltbar wäre.
      if (entry.selected && mode) {
        wish.mode_id = mode.id;
        wish.mode_name = mode.name;
      }
      return wish;
    });
  }, [layout, draft]);

  const nothingSelected =
    layout !== null &&
    layout.outputs.some((o) => o.connected) &&
    !layout.outputs.some((o) => o.connected && (draft[o.name]?.selected ?? o.selected));

  const handleApply = async () => {
    setBusy(true);
    setError(null);
    try {
      await applyDisplayLayout(wishes);
      dirty.current = false;
      await refresh();
    } catch (err: unknown) {
      const statusCode = (err as { response?: { status?: number } })?.response?.status;
      if (statusCode === 409) {
        // Der Refetch MUSS vor dem Setzen der Meldung laufen: refresh()
        // setzt bei Erfolg selbst setError(null) — danach gesetzt, würde die
        // Konflikt-Meldung sich im selben Atemzug wieder löschen.
        dirty.current = false;
        await refresh();
        setError('conflictError');
      } else {
        setError('saveError');
      }
    } finally {
      setBusy(false);
    }
  };

  if (!allowed) return null;

  const anyLit = layout?.outputs.some((o) => o.lit === true) ?? false;
  // Vor dem ersten geladenen Layout ist "leuchtet keiner" nicht beantwortet,
  // sondern schlicht noch nicht gefragt — dasselbe Falschaussage-Muster wie
  // bei `lit`. Erst nach einem geladenen Layout darf das Symbol wirklich
  // "dunkel" behaupten.
  const showLitIcon = layout === null || anyLit;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        aria-label={t('title')}
        onClick={() => {
          // Schließt sich das Popover gerade (isOpen war true), verwirft der
          // Klick einen angefangenen, ungespeicherten Entwurf — sonst würde
          // er beim nächsten Öffnen dem Server-Poll im Weg stehen, obwohl der
          // Nutzer gar nicht mehr mitten in der Bearbeitung ist.
          if (isOpen) dirty.current = false;
          setIsOpen((open) => !open);
        }}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
      >
        {showLitIcon ? <Monitor className="h-5 w-5" /> : <MonitorOff className="h-5 w-5" />}
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-96 rounded-xl border border-slate-800 bg-slate-900/95 p-4 shadow-xl backdrop-blur-xl">
          {layout && !layout.available && (
            <p className="text-sm text-slate-400">{t('unavailable')}</p>
          )}

          {layout?.available && (
            <>
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{t('outputs')}</p>

              {layout.outputs.map((output) => {
                const entry = draft[output.name] ?? {
                  selected: output.selected,
                  modeId: output.current_mode_id,
                };
                return (
                  <div key={output.name} className="mb-4 border-b border-slate-800 pb-3 last:border-0">
                    <div className="mb-1 flex items-center gap-2">
                      <input
                        type="checkbox"
                        id={`display-${output.name}`}
                        aria-label={t('outputs') + ':' + output.name}
                        checked={entry.selected}
                        onChange={(e) => {
                          dirty.current = true;
                          setDraft((prev) => ({
                            ...prev,
                            [output.name]: { ...entry, selected: e.target.checked },
                          }));
                        }}
                      />
                      <label htmlFor={`display-${output.name}`} className="text-sm text-slate-200">
                        {output.name}
                      </label>
                      <span className="ml-auto text-xs text-slate-500">
                        {output.selected ? t('selected') : t('notSelected')}
                      </span>
                      <span className="text-xs text-slate-500">
                        {output.lit === null ? t('litUnknown') : output.lit ? t('lit') : t('dark')}
                      </span>
                    </div>

                    <select
                      aria-label={t('mode', { output: output.name })}
                      value={entry.modeId ?? ''}
                      disabled={!entry.selected}
                      onChange={(e) => {
                        dirty.current = true;
                        setDraft((prev) => ({
                          ...prev,
                          [output.name]: { ...entry, modeId: e.target.value },
                        }));
                      }}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200 disabled:opacity-50"
                    >
                      {output.modes.map((mode) => (
                        <option key={mode.id} value={mode.id}>
                          {formatMode(mode, i18n.language)}
                        </option>
                      ))}
                    </select>
                  </div>
                );
              })}

              {!layout.displays_powered && (
                <p className="mb-2 text-xs text-amber-400">{t('allDark')}</p>
              )}
              {nothingSelected && (
                <p className="mb-2 text-xs text-amber-400">{t('keepOneSelected')}</p>
              )}
              {error && <p className="mb-2 text-xs text-rose-400">{t(error)}</p>}

              <button
                type="button"
                onClick={() => void handleApply()}
                disabled={busy || nothingSelected}
                className="w-full rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:opacity-50"
              >
                {busy ? t('applying') : t('apply')}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
