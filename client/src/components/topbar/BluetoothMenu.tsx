/**
 * Bluetooth-Steuerung in der Topbar.
 *
 * Absichtliche Eigenheiten:
 * - Abgefragt wird nur bei offenem Popover (alle 3 s).
 * - „Koppeln" ist außerhalb privater Netze gesperrt; der Server prüft das
 *   ohnehin, `can_pair_here` spart nur den vergeblichen Klick.
 * - Der Koppel-Dialog hängt nicht am Popover: schließt man es mitten in der
 *   Kopplung, bleibt der Dialog stehen.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bluetooth, BluetoothOff, Gamepad2, Headphones, Keyboard, Loader2, Trash2 } from 'lucide-react';
import {
  connectDevice,
  disconnectDevice,
  getBluetoothState,
  removeDevice,
  setAdapterPowered,
  startPairing,
  startScan,
  type BluetoothDevice,
  type BluetoothState,
  type DeviceKind,
} from '../../api/bluetooth';
import { getMyPowerPermissions } from '../../api/powerPermissions';
import { BluetoothPairingDialog } from './BluetoothPairingDialog';

const POLL_MS = 3000;
const KIND_ORDER: DeviceKind[] = ['controller', 'audio', 'input', 'other'];

/** i18n-Schlüssel statt Text — übersetzt wird erst beim Rendern. */
type ErrorKey = 'loadError' | 'actionError';

interface PairingTarget {
  sessionId: string;
  name: string;
  kind: DeviceKind;
}

function KindIcon({ kind }: { kind: DeviceKind }) {
  if (kind === 'controller') return <Gamepad2 className="h-4 w-4" />;
  if (kind === 'audio') return <Headphones className="h-4 w-4" />;
  if (kind === 'input') return <Keyboard className="h-4 w-4" />;
  return <Bluetooth className="h-4 w-4" />;
}

const SMALL_BUTTON =
  'rounded-lg border border-slate-700 px-2 py-0.5 text-xs text-slate-200 transition hover:border-sky-500/50 disabled:opacity-50';

export function BluetoothMenu() {
  const { t } = useTranslation('bluetooth');
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<BluetoothState | null>(null);
  const [error, setError] = useState<ErrorKey | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [scanUntil, setScanUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [pairing, setPairing] = useState<PairingTarget | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    let active = true;
    getMyPowerPermissions()
      .then((perms) => active && setAllowed(perms.can_manage_bluetooth))
      .catch(() => active && setAllowed(false));
    return () => {
      active = false;
    };
  }, []);

  // Leere Deps sind Absicht (siehe DisplayMenu): eine wechselnde Identität
  // liesse den Poll-Effekt bei jedem Render neu aufsetzen.
  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      setState(await getBluetoothState());
      setError((prev) => (prev === 'loadError' ? null : prev));
    } catch {
      setError('loadError');
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    void refresh();
    const id = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(id);
  }, [isOpen, refresh]);

  useEffect(() => {
    if (scanUntil === null) return;
    const id = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= scanUntil) setScanUntil(null);
    }, 1000);
    return () => clearInterval(id);
  }, [scanUntil]);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [isOpen]);

  const run = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await refresh();
    } catch {
      setError('actionError');
    } finally {
      setBusy(null);
    }
  };

  const handleScan = () =>
    run('scan', async () => {
      const until = await startScan();
      setNow(Date.now());
      setScanUntil(new Date(until).getTime());
    });

  const handlePair = (device: BluetoothDevice) =>
    run(device.address, async () => {
      const sessionId = await startPairing(device.address);
      setPairing({ sessionId, name: device.name, kind: device.kind });
    });

  const handleRemove = (device: BluetoothDevice) => {
    if (!window.confirm(t('removeConfirm', { name: device.name }))) return;
    void run(device.address, () => removeDevice(device.address));
  };

  if (!allowed) return null;

  const adapter = state?.available ? state.adapter : null;
  const paired = state?.devices.filter((d) => d.paired) ?? [];
  const found = state?.devices.filter((d) => !d.paired) ?? [];
  const secondsLeft = scanUntil !== null ? Math.max(0, Math.ceil((scanUntil - now) / 1000)) : 0;
  let pairBlocked: string | null = null;
  if (state && !state.can_pair_here) pairBlocked = t('pairOnlyLocal');
  else if (state?.pairing_active && !pairing) pairBlocked = t('pairBusy');

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        aria-label={t('title')}
        onClick={() => setIsOpen((open) => !open)}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
      >
        {adapter && !adapter.powered ? <BluetoothOff className="h-5 w-5" /> : <Bluetooth className="h-5 w-5" />}
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-96 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-800 bg-slate-900/95 p-4 shadow-xl backdrop-blur-xl">
          {state && !state.available && (
            <p className="text-sm text-slate-400">
              {t('unavailable')}
              {state.detail ? ` ${state.detail}` : ''}
            </p>
          )}

          {adapter && (
            <>
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm text-slate-200">{adapter.name}</span>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void run('adapter', () => setAdapterPowered(!adapter.powered))}
                  className={SMALL_BUTTON}
                >
                  {adapter.powered ? t('powerOff') : t('powerOn')}
                </button>
              </div>

              {state?.warning && <p className="mb-2 text-xs text-amber-400">{state.warning}</p>}
              {!adapter.powered && <p className="text-sm text-slate-400">{t('adapterOff')}</p>}

              {adapter.powered && (
                <>
                  {paired.length === 0 && <p className="mb-2 text-sm text-slate-400">{t('noDevices')}</p>}

                  {KIND_ORDER.map((kind) => {
                    const group = paired.filter((d) => d.kind === kind);
                    if (group.length === 0) return null;
                    return (
                      <div key={kind} className="mb-3">
                        <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">{t(`kind.${kind}`)}</p>
                        {group.map((device) => (
                          <div key={device.address} className="flex items-center gap-2 py-1">
                            <span className="text-slate-400">
                              <KindIcon kind={device.kind} />
                            </span>
                            <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{device.name}</span>
                            {device.battery_percent !== null && (
                              <span className="text-xs text-slate-500">
                                {t('battery', { percent: device.battery_percent })}
                              </span>
                            )}
                            <button
                              type="button"
                              disabled={busy !== null}
                              onClick={() =>
                                void run(device.address, () =>
                                  device.connected ? disconnectDevice(device.address) : connectDevice(device.address),
                                )
                              }
                              className={SMALL_BUTTON}
                            >
                              {busy === device.address ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : device.connected ? (
                                t('disconnect')
                              ) : (
                                t('connect')
                              )}
                            </button>
                            <button
                              type="button"
                              aria-label={`${t('remove')}: ${device.name}`}
                              disabled={busy !== null}
                              onClick={() => handleRemove(device)}
                              className="text-slate-500 transition hover:text-rose-400 disabled:opacity-50"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    );
                  })}

                  <div className="border-t border-slate-800 pt-3">
                    {scanUntil !== null ? (
                      <p className="mb-2 text-xs text-slate-400">{t('scanning', { seconds: secondsLeft })}</p>
                    ) : (
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void handleScan()}
                        className="w-full rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:opacity-50"
                      >
                        {t('addDevice')}
                      </button>
                    )}
                    {scanUntil !== null && found.length === 0 && (
                      <p className="text-xs text-slate-500">{t('noneFound')}</p>
                    )}
                    {found.map((device) => (
                      <div key={device.address} className="flex items-center gap-2 py-1">
                        <span className="text-slate-400">
                          <KindIcon kind={device.kind} />
                        </span>
                        <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{device.name}</span>
                        <button
                          type="button"
                          disabled={busy !== null || pairBlocked !== null}
                          title={pairBlocked ?? undefined}
                          onClick={() => void handlePair(device)}
                          className={SMALL_BUTTON}
                        >
                          {t('pair')}
                        </button>
                      </div>
                    ))}
                    {pairBlocked && found.length > 0 && (
                      <p className="mt-1 text-xs text-amber-400">{pairBlocked}</p>
                    )}
                  </div>
                </>
              )}
            </>
          )}

          {error && <p className="mt-2 text-xs text-rose-400">{t(error)}</p>}
        </div>
      )}

      {pairing && (
        <BluetoothPairingDialog
          sessionId={pairing.sessionId}
          deviceName={pairing.name}
          kind={pairing.kind}
          onClose={() => {
            setPairing(null);
            void refresh();
          }}
        />
      )}
    </div>
  );
}
