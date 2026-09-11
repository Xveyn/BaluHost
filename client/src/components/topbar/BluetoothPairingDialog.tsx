/**
 * Koppel-Dialog: zeigt den Stand der eigenen Kopplung.
 *
 * Die Sitzung lebt im Besitzer-Worker des Backends; hier wird nur
 * `GET /pairing` abgefragt. Verschwindet die Sitzung, bevor ein Endstand kam
 * (Besitzer-Worker tot, SHM geräumt), zeigt der Dialog „abgebrochen" — nie
 * einen Code, der nicht mehr gilt.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import {
  answerPairing,
  cancelPairing,
  getPairingSession,
  TERMINAL_STAGES,
  type DeviceKind,
  type PairingSession,
} from '../../api/bluetooth';

interface BluetoothPairingDialogProps {
  sessionId: string;
  deviceName: string;
  kind: DeviceKind;
  onClose: () => void;
  /** Nur für Tests kürzer. */
  pollMs?: number;
}

export function BluetoothPairingDialog({
  sessionId,
  deviceName,
  kind,
  onClose,
  pollMs = 1000,
}: BluetoothPairingDialogProps) {
  const { t } = useTranslation('bluetooth');
  const [session, setSession] = useState<PairingSession | null>(null);
  const [lost, setLost] = useState(false);
  const [sending, setSending] = useState(false);
  const seen = useRef(false);
  const finished = useRef(false);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      if (finished.current) return;
      try {
        const next = await getPairingSession();
        if (!active) return;
        const mine = next && next.session_id === sessionId ? next : null;
        if (mine) {
          seen.current = true;
          setSession(mine);
          if (TERMINAL_STAGES.has(mine.stage)) finished.current = true;
        } else if (seen.current) {
          finished.current = true;
          setLost(true);
        }
      } catch {
        // Nächster Takt versucht es erneut.
      }
    };
    void poll();
    const id = setInterval(() => void poll(), pollMs);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [sessionId, pollMs]);

  const stage = lost ? 'cancelled' : (session?.stage ?? 'connecting');
  const done = lost || (session !== null && TERMINAL_STAGES.has(session.stage));
  const title = t('dialog.title', { name: deviceName });

  const send = async (action: () => Promise<void>) => {
    setSending(true);
    try {
      await action();
    } catch {
      // Der nächste Poll zeigt den tatsächlichen Stand.
    } finally {
      setSending(false);
    }
  };

  const code = session?.code ?? null;
  const entered = session?.entered ?? null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-sm rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-xl">
        <h2 className="mb-3 text-base font-medium text-slate-100">{title}</h2>

        {kind === 'input' && !done && (
          <p className="mb-3 text-xs text-amber-400">{t('dialog.inputWarning')}</p>
        )}

        {stage === 'connecting' && (
          <p className="flex items-center gap-2 text-sm text-slate-300">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('dialog.connecting')}
          </p>
        )}

        {(stage === 'display_passkey' || stage === 'display_pin') && code && (
          <>
            <p className="mb-2 text-sm text-slate-300">
              {stage === 'display_passkey' ? t('dialog.displayPasskey') : t('dialog.displayPin')}
            </p>
            <p data-testid="pairing-code" className="mb-2 text-center font-mono text-3xl tracking-[0.4em] text-slate-100">
              {code}
            </p>
            {stage === 'display_passkey' && entered !== null && (
              <p data-testid="pairing-progress" aria-hidden="true" className="text-center text-slate-400">
                {'●'.repeat(Math.min(entered, code.length))}
                {'○'.repeat(Math.max(0, code.length - entered))}
              </p>
            )}
          </>
        )}

        {stage === 'confirm' && code && (
          <>
            <p className="mb-2 text-sm text-slate-300">{t('dialog.confirm')}</p>
            <p data-testid="pairing-code" className="mb-3 text-center font-mono text-3xl tracking-[0.4em] text-slate-100">
              {code}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={sending}
                onClick={() => void send(() => answerPairing(sessionId, true))}
                className="flex-1 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {t('dialog.accept')}
              </button>
              <button
                type="button"
                disabled={sending}
                onClick={() => void send(() => answerPairing(sessionId, false))}
                className="flex-1 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:border-rose-500/50 disabled:opacity-50"
              >
                {t('dialog.reject')}
              </button>
            </div>
          </>
        )}

        {stage === 'succeeded' && <p className="text-sm text-emerald-400">{t('dialog.succeeded')}</p>}
        {stage === 'cancelled' && <p className="text-sm text-slate-300">{t('dialog.cancelled')}</p>}
        {stage === 'failed' && (
          <p className="text-sm text-rose-400">{t(`dialog.error.${session?.error ?? 'unknown'}`)}</p>
        )}

        <div className="mt-4 flex justify-end">
          {done ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:border-sky-500/50"
            >
              {t('dialog.close')}
            </button>
          ) : (
            <button
              type="button"
              disabled={sending}
              onClick={() => void send(() => cancelPairing(sessionId))}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:border-rose-500/50 disabled:opacity-50"
            >
              {t('dialog.cancel')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
