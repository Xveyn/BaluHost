import { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, RefreshCw, Globe } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getReferenceLists, createReferenceList, updateReferenceList,
  deleteReferenceList, refreshReferenceLists, type ReferenceListEntry,
} from '../../../api/adDiscovery';

function statusBadge(list: ReferenceListEntry) {
  if (list.last_error) return <span className="rounded-full bg-red-500/20 px-2 py-0.5 text-xs text-red-300">Error</span>;
  if (!list.last_fetched_at) return <span className="rounded-full bg-slate-500/20 px-2 py-0.5 text-xs text-slate-400">Never fetched</span>;
  return <span className="rounded-full bg-green-500/20 px-2 py-0.5 text-xs text-green-300">Current</span>;
}

export default function ReferenceListsPanel() {
  const [lists, setLists] = useState<ReferenceListEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newList, setNewList] = useState({ name: '', url: '', fetch_interval_hours: 24 });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getReferenceLists();
      setLists(result.lists);
    } catch {
      toast.error('Failed to load reference lists');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleCreate = async () => {
    if (!newList.name.trim() || !newList.url.trim()) return;
    try {
      await createReferenceList(newList);
      toast.success('Reference list added');
      setShowAdd(false);
      setNewList({ name: '', url: '', fetch_interval_hours: 24 });
      fetchData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to add list');
    }
  };

  const handleToggle = async (l: ReferenceListEntry) => {
    try {
      await updateReferenceList(l.id, { enabled: !l.enabled });
      fetchData();
    } catch {
      toast.error('Failed to toggle list');
    }
  };

  const handleDelete = async (l: ReferenceListEntry) => {
    if (l.is_default) return;
    try {
      await deleteReferenceList(l.id);
      toast.success('List deleted');
      fetchData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to delete');
    }
  };

  const handleRefreshAll = async () => {
    setRefreshing(true);
    try {
      await refreshReferenceLists();
      toast.success('Lists refreshed');
      fetchData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to refresh');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Community Reference Lists</h3>
        <div className="flex gap-2">
          <button onClick={handleRefreshAll} disabled={refreshing}
            className="flex items-center gap-1.5 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600 disabled:opacity-50">
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} /> Refresh All
          </button>
          <button onClick={() => setShowAdd(!showAdd)}
            className="flex items-center gap-1.5 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600">
            <Plus className="h-4 w-4" /> Add List
          </button>
        </div>
      </div>

      {showAdd && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/60 p-4 space-y-3">
          <input value={newList.name} onChange={e => setNewList(l => ({ ...l, name: e.target.value }))}
            placeholder="List name" className="w-full rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white" />
          <input value={newList.url} onChange={e => setNewList(l => ({ ...l, url: e.target.value }))}
            placeholder="https://..." className="w-full rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white" />
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400">Refresh every</span>
            <input type="number" min={1} max={168} value={newList.fetch_interval_hours}
              onChange={e => setNewList(l => ({ ...l, fetch_interval_hours: parseInt(e.target.value) || 24 }))}
              className="w-16 rounded-md border border-slate-600 bg-slate-700 px-2 py-1 text-sm text-white" />
            <span className="text-xs text-slate-400">hours</span>
            <div className="flex-1" />
            <button onClick={handleCreate} className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-500">Add</button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-center text-sm text-slate-500">Loading...</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {lists.map(l => (
            <div key={l.id} className={`rounded-lg border p-4 ${l.enabled ? 'border-slate-600 bg-slate-800/40' : 'border-slate-700/50 bg-slate-800/20 opacity-60'}`}>
              <div className="flex items-start justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Globe className="h-4 w-4 text-slate-400" />
                    <span className="font-medium text-white text-sm">{l.name}</span>
                    {statusBadge(l)}
                  </div>
                  <p className="mt-1 truncate text-xs text-slate-500">{l.url}</p>
                </div>
                <button onClick={() => handleToggle(l)}
                  className={`relative h-5 w-9 flex-shrink-0 rounded-full transition-colors ${l.enabled ? 'bg-blue-600' : 'bg-slate-600'}`}>
                  <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${l.enabled ? 'left-[18px]' : 'left-0.5'}`} />
                </button>
              </div>
              <div className="mt-2 flex items-center gap-3 text-xs text-slate-400">
                <span>{l.domain_count.toLocaleString()} domains</span>
                {l.last_fetched_at && <span>Fetched {new Date(l.last_fetched_at).toLocaleDateString()}</span>}
                {l.last_error && <span className="text-red-400 truncate max-w-[200px]" title={l.last_error}>{l.last_error}</span>}
              </div>
              {!l.is_default && (
                <div className="mt-2 flex justify-end">
                  <button onClick={() => handleDelete(l)} className="rounded p-1 text-red-400 hover:bg-red-500/10">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
