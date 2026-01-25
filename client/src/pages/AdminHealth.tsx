import { useEffect, useState } from 'react';
import { buildApiUrl } from '../lib/api';

export default function AdminHealth() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(buildApiUrl('/api/system/health'), {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setHealth(data);
    } catch (err: any) {
      setError(err?.message || 'Fehler beim Laden');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchHealth(); }, []);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <h1 className="text-2xl sm:text-3xl font-semibold text-white">System Health</h1>
        <div>
          <button
            onClick={fetchHealth}
            className="min-h-[44px] rounded-md bg-sky-500 px-4 py-2.5 text-sm font-medium text-white touch-manipulation active:scale-95 transition-transform"
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && <div className="mt-4 text-red-400 text-sm">{error}</div>}

      <div className="mt-4 space-y-4">
        {health ? (
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 sm:p-4">
            <pre className="whitespace-pre-wrap text-xs sm:text-sm overflow-x-auto">{JSON.stringify(health, null, 2)}</pre>
          </div>
        ) : (
          <div className="text-sm text-slate-400">No data yet.</div>
        )}
      </div>
    </div>
  );
}
