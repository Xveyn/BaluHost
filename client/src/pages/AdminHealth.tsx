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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">System Health</h1>
        <div>
          <button
            onClick={fetchHealth}
            className="rounded-md bg-sky-500 px-3 py-2 text-sm font-medium text-white"
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && <div className="mt-4 text-red-400">{error}</div>}

      <div className="mt-4 space-y-4">
        {health ? (
          <div className="rounded-md border border-slate-800 bg-slate-900/60 p-4">
            <pre className="whitespace-pre-wrap text-sm">{JSON.stringify(health, null, 2)}</pre>
          </div>
        ) : (
          <div className="text-sm text-slate-400">No data yet.</div>
        )}
      </div>
    </div>
  );
}
