import { useEffect, useState, useRef } from 'react';
import { getRaidStatus, triggerRaidScrub } from '../api/raid';
import { fetchSmartStatus, getSmartMode, toggleSmartMode, runSmartTest } from '../api/smart';
import { requestConfirmation, executeConfirmation } from '../api/raid';

function StatusBadge({ status }: { status?: string }) {
  const s = (status || '').toLowerCase();
  const className = s.includes('ok') || s === 'optimal' || s === 'active' || s === 'passed' || s === 'online'
    ? 'bg-emerald-600 text-white'
    : s.includes('degrad') || s.includes('warning') || s === 'idle' || s === 'info'
    ? 'bg-amber-500 text-slate-900'
    : 'bg-red-600 text-white';

  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {status ?? 'unknown'}
    </span>
  );
}

function ProgressBar({ value }: { value?: number | null }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="mt-2 w-full rounded bg-slate-800/60">
      <div className="h-2 rounded bg-sky-500" style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function SchedulerControls() {
  const [raid, setRaid] = useState<any>(null);
  const [smart, setSmart] = useState<any>(null);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [smartMode, setSmartMode] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Array<{ id: string; message: string; type?: 'success'|'error'|'info'; closing?: boolean }>>([]);
  const [confirmModal, setConfirmModal] = useState<{ visible: boolean; token?: string; expires_at?: number; action?: string; payload?: any; loading?: boolean }>({ visible: false });
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);
  const tokenRef = useRef<HTMLDivElement | null>(null);

  const addToast = (message: string, type: 'success'|'error'|'info' = 'info', timeout = 5000) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2,8)}`;
    const t = { id, message, type, closing: false };
    setToasts((s) => [...s, t]);

    // Schedule graceful close before removal to allow exit animation
    const closeDelay = 300; // animation duration
    const removeAfter = timeout;
    setTimeout(() => {
      setToasts((s) => s.map(x => x.id === id ? { ...x, closing: true } : x));
      setTimeout(() => setToasts((s) => s.filter(x => x.id !== id)), closeDelay);
    }, Math.max(0, removeAfter - closeDelay));
  };

  const dismissToast = (id: string) => {
    // start exit animation, then remove
    setToasts((s) => s.map(x => x.id === id ? { ...x, closing: true } : x));
    setTimeout(() => setToasts((s) => s.filter(x => x.id !== id)), 300);
  };

  const load = async () => {
    try {
      const [r, s, m] = await Promise.all([getRaidStatus(), fetchSmartStatus(), getSmartMode()]);
      setRaid(r);
      setSmart(s);
      setSelectedDevice(s?.devices?.[0]?.name ?? null);
      setSmartMode(m);
    } catch (err: any) {
      setMsg(err?.message || 'Fehler');
    }
  };

  useEffect(() => { load(); }, []);

  const handleRaidScrub = async () => {
    setBusy(true); setMsg(null);
    try {
      const res = await triggerRaidScrub();
      setMsg(res.message || 'Scrub gestartet');
      addToast(res.message || 'Scrub gestartet', 'success');
      await load();
    } catch (err: any) {
      const text = err?.message || String(err);
      setMsg(text || 'Fehler beim Scrub');
      addToast(text || 'Fehler beim Scrub', 'error');
    } finally { setBusy(false); }
  };

  const requestDeleteArray = async (arrayName: string) => {
    setBusy(true);
    try {
      const res = await requestConfirmation('delete_array', { array: arrayName, force: false });
      setConfirmModal({ visible: true, token: res.token, expires_at: res.expires_at, action: 'delete_array', payload: { array: arrayName } });
      addToast('Confirmation token created. Confirm to execute.', 'info', 8000);
    } catch (err: any) {
      const text = err?.message || String(err);
      addToast(text, 'error');
    } finally { setBusy(false); }
  };

  const executeToken = async () => {
    if (!confirmModal.token) return;
    setConfirmModal((s) => ({ ...s, loading: true }));
    try {
      const resp = await executeConfirmation(confirmModal.token!);
      addToast(resp.message || 'Action executed', 'success');
      setConfirmModal({ visible: false });
      await load();
    } catch (err: any) {
      const text = err?.message || String(err);
      addToast(text, 'error');
      setConfirmModal({ visible: false });
    }
  };

  // Accessibility: focus management & keyboard handling for modal
  useEffect(() => {
    if (confirmModal.visible) {
      // focus the confirm button when modal opens
      setTimeout(() => confirmButtonRef.current?.focus(), 0);

      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          setConfirmModal({ visible: false });
        }
        if (e.key === 'c' && (e.ctrlKey || e.metaKey)) {
          // Ctrl/Cmd+C - copy token if modal open
          if (confirmModal.token) {
            e.preventDefault();
            void (async () => {
              try {
                await navigator.clipboard.writeText(confirmModal.token!);
                addToast('Token copied to clipboard', 'success');
              } catch {
                addToast('Kopieren fehlgeschlagen', 'error');
              }
            })();
          }
        }
      };

      document.addEventListener('keydown', onKey);
      return () => document.removeEventListener('keydown', onKey);
    }
  }, [confirmModal.visible]);

  const copyTokenToClipboard = async () => {
    if (!confirmModal.token) return;
    try {
      await navigator.clipboard.writeText(confirmModal.token);
      addToast('Token copied to clipboard', 'success');
    } catch {
      // fallback: create temporary textarea
      try {
        const ta = document.createElement('textarea');
        ta.value = confirmModal.token;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        addToast('Token copied to clipboard', 'success');
      } catch {
        addToast('Copy failed', 'error');
      }
    }
  };

  const handleSmartTest = async () => {
    setBusy(true); setMsg(null);
    try {
      const device = selectedDevice || smart?.devices?.[0]?.name;
      if (!device) throw new Error('Kein Gerät für SMART-Test gefunden');
      const res = await runSmartTest({ device, type: 'short' });
      setMsg(res.message || 'SMART-Test gestartet');
      addToast(res.message || 'SMART-Test gestartet', 'success');
      await load();
    } catch (err: any) {
      const extract = (e: any) => {
        const text = e?.message || String(e);
        try {
          const parsed = JSON.parse(text);
          if (parsed?.detail) return typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail);
          if (parsed?.message) return parsed.message;
        } catch {}
        return text;
      };
      const text = extract(err) || 'Fehler beim SMART-Test';
      setMsg(text);
      addToast(text, 'error');
    } finally { setBusy(false); }
  };

  const handleToggleSmart = async () => {
    setBusy(true); setMsg(null);
    try {
      const res = await toggleSmartMode();
      setSmartMode(res);
      const text = res.message || `SMART mode: ${res.mode}`;
      setMsg(text);
      addToast(text, 'success');
    } catch (err: any) {
      const text = err?.message || 'Fehler beim Umschalten des SMART-Modus';
      setMsg(text);
      addToast(text, 'error');
    } finally { setBusy(false); }
  };

  return (
    <>
    <div>
      {/* Toast container */}
      <div className="fixed right-2 sm:right-4 top-16 sm:top-20 z-50 flex max-w-[calc(100vw-1rem)] sm:max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`rounded-md px-3 sm:px-4 py-2 shadow-lg transform transition-all duration-300 ease-out flex items-start justify-between gap-2 sm:gap-3 ${t.closing ? 'opacity-0 -translate-y-2 scale-95' : 'opacity-100 translate-y-0'} ${t.type === 'success' ? 'bg-emerald-600 text-white' : t.type === 'error' ? 'bg-red-600 text-white' : 'bg-slate-800 text-white'}`}
          >
            <div className="mr-2 sm:mr-3 flex-1 text-xs sm:text-sm leading-snug">{t.message}</div>
            <button onClick={() => dismissToast(t.id)} className="min-h-[36px] min-w-[36px] flex items-center justify-center rounded-md p-1 text-sm opacity-90 hover:opacity-100 touch-manipulation">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <h1 className="text-2xl sm:text-3xl font-semibold text-white">Schedulers & Manual Tests</h1>
        <div className="flex flex-wrap gap-2">
          <button onClick={handleRaidScrub} disabled={busy} className="min-h-[44px] rounded-md bg-emerald-600 px-3 sm:px-4 py-2.5 text-xs sm:text-sm font-medium text-white touch-manipulation active:scale-95 transition-transform disabled:opacity-50">Trigger RAID Scrub</button>
          <button onClick={handleSmartTest} disabled={busy} className="min-h-[44px] rounded-md bg-amber-600 px-3 sm:px-4 py-2.5 text-xs sm:text-sm font-medium text-white touch-manipulation active:scale-95 transition-transform disabled:opacity-50">Run SMART Short</button>
          <button onClick={handleToggleSmart} disabled={busy} className="min-h-[44px] rounded-md bg-sky-500 px-3 sm:px-4 py-2.5 text-xs sm:text-sm font-medium text-white touch-manipulation active:scale-95 transition-transform disabled:opacity-50">Toggle SMART Mode</button>
        </div>
      </div>

      {msg && <div className="mt-4 text-sm text-slate-200">{msg}</div>}

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-md border border-slate-800 bg-slate-900/60 p-4">
          <h2 className="text-lg font-medium">RAID Status</h2>
          <div className="mt-3 space-y-4">
            {raid?.arrays?.length ? (
              raid.arrays.map((a: any) => (
                <div key={a.name} className="rounded-md border border-slate-800 bg-slate-950/40 p-3">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-3">
                    <div>
                      <div className="text-sm font-medium">{a.name} <span className="text-xs text-slate-400">({a.level})</span></div>
                      <div className="text-xs text-slate-400">Size: {a.size_bytes ? Math.round(a.size_bytes / (1024*1024*1024)) + ' GB' : 'n/a'}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={a.status || a.sync_action} />
                      <button onClick={() => requestDeleteArray(a.name)} disabled={busy} className="min-h-[36px] rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white touch-manipulation active:scale-95 transition-transform disabled:opacity-50">Delete</button>
                    </div>
                  </div>

                  {a.resync_progress != null && (
                    <div className="mt-3">
                      <div className="text-xs text-slate-400">Resync Progress</div>
                      <ProgressBar value={a.resync_progress} />
                      <div className="mt-1 text-xs text-slate-400">{Math.round((a.resync_progress||0)*100)}%</div>
                    </div>
                  )}

                  <div className="mt-3 text-xs">
                    <div className="text-slate-400 mb-1">Devices</div>
                    <div className="flex flex-wrap gap-2">
                      {a.devices?.map((d: any) => (
                        <div key={d.name} className="rounded-md border border-slate-800 bg-slate-900/60 px-2 py-1 text-xs">{d.name} <span className="text-[10px] text-slate-400">{d.state}</span></div>
                      ))}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-slate-400">No arrays detected.</div>
            )}
          </div>
        </div>

        <div className="rounded-md border border-slate-800 bg-slate-900/60 p-4">
          <h2 className="text-lg font-medium">SMART Status</h2>
          <div className="mt-3 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <label className="text-xs text-slate-400">Device:</label>
                <select
                  value={selectedDevice ?? ''}
                  onChange={(e) => setSelectedDevice(e.target.value || null)}
                  className="rounded-md bg-slate-800 px-2 py-1 text-sm"
                >
                  {(smart?.devices ?? []).map((d: any) => (
                    <option key={d.name} value={d.name}>{d.name}{d.model ? ` — ${d.model}` : ''}</option>
                  ))}
                </select>
              </div>
              <div className="text-xs text-slate-400">Selected: <span className="text-slate-100">{selectedDevice ?? 'none'}</span></div>
            </div>
            {smart?.devices?.length ? (
              smart.devices.map((dev: any) => (
                <div key={dev.name} className="rounded-md border border-slate-800 bg-slate-950/40 p-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-sm font-medium">{dev.model ?? dev.name}</div>
                      <div className="text-xs text-slate-400">{dev.name} • {dev.serial ?? ''}</div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <div className="text-xs">Temp: <span className="font-medium">{dev.temperature ?? 'n/a'}</span>°C</div>
                      <StatusBadge status={dev.status} />
                    </div>
                  </div>

                  <div className="mt-3 text-xs text-slate-400">Attributes: {dev.attributes?.length ?? 0}</div>
                </div>
              ))
            ) : (
              <div className="text-sm text-slate-400">No SMART devices found.</div>
            )}

            <div className="mt-2 text-sm text-slate-400">Mode: <span className="font-medium text-slate-100">{smartMode?.mode ?? 'unknown'}</span></div>
          </div>
        </div>
      </div>
    </div>

      {confirmModal.visible && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4" role="presentation">
          <div className="absolute inset-0 bg-black/60" onClick={() => setConfirmModal((s) => ({ ...s, visible: false }))} />
          <div
            className="relative z-10 w-full max-w-lg rounded-lg bg-slate-900 p-4 sm:p-6 shadow-lg max-h-[90vh] overflow-y-auto"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-modal-title"
          >
            <h3 id="confirm-modal-title" className="text-base sm:text-lg font-medium text-white">Confirm {confirmModal.action}</h3>
            <p className="mt-2 text-xs sm:text-sm text-slate-400">A one-time confirmation token was created. Click Confirm to execute the action now.</p>
            <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-slate-400">Token</div>
                  <div ref={tokenRef} className="mt-1 font-mono text-xs sm:text-sm break-all text-slate-100" aria-live="polite">{confirmModal.token}</div>
                  <div className="mt-2 text-xs text-slate-400">Expires at: {confirmModal.expires_at ? new Date(confirmModal.expires_at * 1000).toLocaleString() : 'n/a'}</div>
                </div>
                <div className="flex-shrink-0">
                  <button onClick={copyTokenToClipboard} aria-label="Copy token to clipboard" className="min-h-[44px] rounded-md bg-slate-700 px-3 py-2 text-sm text-white touch-manipulation active:scale-95 transition-transform">Copy</button>
                </div>
              </div>
            </div>
            <div className="mt-4 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
              <button onClick={() => setConfirmModal((s) => ({ ...s, visible: false }))} className="min-h-[44px] rounded-md px-4 py-2 text-sm text-slate-300 touch-manipulation active:scale-95 transition-transform">Cancel</button>
              <button ref={confirmButtonRef} onClick={executeToken} disabled={confirmModal.loading} className="min-h-[44px] rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white touch-manipulation active:scale-95 transition-transform disabled:opacity-50">Confirm Execute</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
