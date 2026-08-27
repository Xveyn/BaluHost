/**
 * Audiosteuerung in der Topbar.
 *
 * Zeigt ein Lautsprecher-Symbol; im Popover stehen Ausgabegerät, Master-Pegel
 * und ein Mixer je laufender Anwendung.
 *
 * Zwei Eigenheiten, die Absicht sind:
 * - Der Zustand wird nur abgefragt, solange das Popover offen ist. Eine
 *   Fernbedienung, die im Hintergrund pollt, kostet Anfragen ohne Gegenwert.
 * - Angezeigt wird der Anwendungsname, nie der Titel. `media.name` verrät,
 *   was gerade läuft; der Titel erscheint nur im Tooltip.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Volume2, VolumeX } from 'lucide-react';
import {
  getAudioState,
  setDefaultSink,
  setSinkMute,
  setSinkVolume,
  setStreamMute,
  setStreamVolume,
  type AudioState,
} from '../../api/audioControl';
import { getMyPowerPermissions } from '../../api/powerPermissions';

/** Wartezeit, bevor eine Reglerbewegung zur Anfrage wird. */
const DEBOUNCE_MS = 200;

/** Abfragetakt, solange das Popover offen ist. */
const POLL_MS = 2000;

export function AudioMenu() {
  const { t } = useTranslation('audio');
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<AudioState | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  useEffect(() => {
    let active = true;
    getMyPowerPermissions()
      .then((perms) => active && setAllowed(perms.can_control_audio))
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
      setState(await getAudioState());
    } catch {
      setState({ sinks: [], streams: [], available: false, detail: null });
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    void refresh();
    const id = setInterval(() => {
      // Solange eine Reglerbewegung noch aussteht, NICHT abfragen: der Abruf
      // brächte den alten Serverwert zurück und liesse den Regler mitten im
      // Ziehen zurückspringen. Sobald der entprellte Schreibvorgang durch ist,
      // ruft er selbst refresh() auf.
      if (timers.current.size > 0) return;
      void refresh();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [isOpen, refresh]);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [isOpen]);

  const timersRef = timers.current;
  useEffect(() => () => timersRef.forEach((id) => clearTimeout(id)), [timersRef]);

  /** Verzögert einen Schreibvorgang und verwirft dabei die Zwischenschritte. */
  const debounce = useCallback((key: string, run: () => Promise<void>) => {
    const existing = timers.current.get(key);
    if (existing) clearTimeout(existing);
    timers.current.set(
      key,
      setTimeout(() => {
        timers.current.delete(key);
        void run().then(refresh).catch(() => undefined);
      }, DEBOUNCE_MS),
    );
  }, [refresh]);

  /** Zeigt den neuen Wert sofort, damit der Regler dem Finger folgt. */
  const optimisticSink = (id: number, percent: number) =>
    setState((prev) =>
      prev
        ? { ...prev, sinks: prev.sinks.map((s) => (s.id === id ? { ...s, volume_percent: percent } : s)) }
        : prev,
    );

  const optimisticStream = (id: number, percent: number) =>
    setState((prev) =>
      prev
        ? {
            ...prev,
            streams: prev.streams.map((s) =>
              s.id === id ? { ...s, volume_percent: percent } : s,
            ),
          }
        : prev,
    );

  if (!allowed) return null;

  const defaultSink = state?.sinks.find((s) => s.is_default) ?? null;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        aria-label={t('title')}
        onClick={() => setIsOpen((open) => !open)}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
      >
        {defaultSink?.muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-xl border border-slate-800 bg-slate-900/95 p-4 shadow-xl backdrop-blur-xl">
          {state && !state.available && (
            <p className="text-sm text-slate-400">{t('unavailable')}</p>
          )}

          {state?.available && (
            <>
              <label className="mb-1 block text-xs uppercase tracking-wide text-slate-500">
                {t('output')}
              </label>
              <select
                aria-label={t('output')}
                value={defaultSink?.name ?? ''}
                onChange={(e) => void setDefaultSink(e.target.value).then(refresh)}
                className="mb-4 w-full rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
              >
                {state.sinks.map((sink) => (
                  <option key={sink.id} value={sink.name}>
                    {sink.description}
                  </option>
                ))}
              </select>

              {defaultSink && (
                <div className="mb-4 flex items-center gap-2">
                  <button
                    type="button"
                    aria-label={defaultSink.muted ? t('unmute') : t('mute')}
                    onClick={() =>
                      void setSinkMute(defaultSink.id, !defaultSink.muted).then(refresh)
                    }
                    className="text-slate-400 hover:text-sky-400"
                  >
                    {defaultSink.muted ? (
                      <VolumeX className="h-4 w-4" />
                    ) : (
                      <Volume2 className="h-4 w-4" />
                    )}
                  </button>
                  <input
                    type="range"
                    aria-label={t('sinkVolume')}
                    min={0}
                    max={150}
                    value={defaultSink.volume_percent}
                    onChange={(e) => {
                      const percent = Number(e.target.value);
                      optimisticSink(defaultSink.id, percent);
                      debounce(`sink:${defaultSink.id}`, () =>
                        setSinkVolume(defaultSink.id, percent),
                      );
                    }}
                    className="flex-1"
                  />
                  <span className="w-10 text-right text-xs text-slate-400">
                    {defaultSink.volume_percent}%
                  </span>
                </div>
              )}

              <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{t('apps')}</p>
              {state.streams.length === 0 ? (
                <p className="text-sm text-slate-400">{t('noStreams')}</p>
              ) : (
                state.streams.map((stream) => (
                  <div
                    key={stream.id}
                    className={`mb-3 flex items-center gap-2 ${stream.corked ? 'opacity-50' : ''}`}
                    title={stream.title ?? undefined}
                  >
                    <button
                      type="button"
                      aria-label={
                        stream.muted
                          ? t('unmuteApp', { app: stream.application })
                          : t('muteApp', { app: stream.application })
                      }
                      onClick={() => void setStreamMute(stream.id, !stream.muted).then(refresh)}
                      className="text-slate-400 hover:text-sky-400"
                    >
                      {stream.muted ? (
                        <VolumeX className="h-4 w-4" />
                      ) : (
                        <Volume2 className="h-4 w-4" />
                      )}
                    </button>
                    <div className="flex-1">
                      <p className="truncate text-xs text-slate-300">
                        {stream.application}
                        {stream.corked && (
                          <span className="ml-1 text-slate-500">({t('paused')})</span>
                        )}
                      </p>
                      <input
                        type="range"
                        aria-label={t('streamVolume', { app: stream.application })}
                        min={0}
                        max={150}
                        value={stream.volume_percent}
                        onChange={(e) => {
                          const percent = Number(e.target.value);
                          optimisticStream(stream.id, percent);
                          debounce(`stream:${stream.id}`, () =>
                            setStreamVolume(stream.id, percent),
                          );
                        }}
                        className="w-full"
                      />
                    </div>
                  </div>
                ))
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
