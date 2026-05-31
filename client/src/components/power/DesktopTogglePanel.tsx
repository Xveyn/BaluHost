/**
 * Desktop Toggle Panel
 *
 * Stops/starts the KDE display manager (SDDM) so the GPU can enter a
 * low-power state while the NAS remains fully accessible over the network.
 * The desktop session is re-started automatically when re-enabled.
 */

import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Monitor } from 'lucide-react';
import {
  type DesktopStatus,
  getDesktopStatus,
  disableDesktop,
  enableDesktop,
} from '../../api/desktop';

export function DesktopTogglePanel() {
  const [status, setStatus] = useState<DesktopStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const data = await getDesktopStatus();
      setStatus(data);
    } catch {
      // Silent fail — error surface is the loading skeleton staying visible
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onToggle() {
    if (!status || busy) return;
    setBusy(true);
    try {
      const result =
        status.state === 'running' ? await disableDesktop() : await enableDesktop();
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message || 'Aktion fehlgeschlagen');
      }
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Aktion fehlgeschlagen');
    } finally {
      setBusy(false);
    }
  }

  if (loading || !status) {
    return (
      <div className="card border-slate-700/50 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700/50 rounded w-1/3" />
          <div className="h-16 bg-slate-700/50 rounded" />
        </div>
      </div>
    );
  }

  const running = status.state === 'running';
  const unknown = status.state === 'unknown';

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${running ? 'bg-emerald-500/20' : 'bg-slate-700/40'}`}>
            <Monitor className={`h-5 w-5 ${running ? 'text-emerald-400' : 'text-slate-400'}`} />
          </div>
          <div>
            <h4 className="text-sm font-medium text-white">Desktop (KDE)</h4>
            <p className="mt-0.5 text-xs text-slate-400">
              Beendet die KDE-Sitzung, damit die GPU in den Ruhezustand wechseln kann.
              Beim Aktivieren startet der Desktop neu.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onToggle}
          disabled={busy || unknown}
          className={`shrink-0 flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
            running
              ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30'
              : 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30'
          }`}
          title={running ? 'Desktop deaktivieren' : 'Desktop aktivieren'}
        >
          {busy ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <Monitor className="h-4 w-4" />
          )}
          <span className="hidden sm:inline">
            {running ? 'Deaktivieren' : 'Aktivieren'}
          </span>
        </button>
      </div>

      <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
        <span>Status:</span>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
            running
              ? 'bg-emerald-500/20 text-emerald-400'
              : unknown
              ? 'bg-slate-700/40 text-slate-400'
              : 'bg-amber-500/20 text-amber-400'
          }`}
        >
          {running ? 'Läuft' : unknown ? 'Unbekannt' : 'Gestoppt'}
        </span>
        <span className="text-slate-600">{status.display_manager}</span>
        {status.detail ? (
          <span className="text-slate-500">— {status.detail}</span>
        ) : null}
      </div>
    </div>
  );
}
