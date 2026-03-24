import { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, Code, Type } from 'lucide-react';
import toast from 'react-hot-toast';
import { getPatterns, createPattern, updatePattern, deletePattern, type PatternEntry } from '../../../api/adDiscovery';

const CATEGORIES = ['ads', 'tracking', 'telemetry', 'analytics', 'fingerprinting', 'custom'];

export default function PatternsPanel() {
  const [patterns, setPatterns] = useState<PatternEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newPattern, setNewPattern] = useState({ pattern: '', is_regex: false, weight: 0.5, category: 'custom' });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getPatterns();
      setPatterns(result.patterns);
    } catch {
      toast.error('Failed to load patterns');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleCreate = async () => {
    if (!newPattern.pattern.trim()) return;
    try {
      await createPattern(newPattern);
      toast.success('Pattern created');
      setShowAdd(false);
      setNewPattern({ pattern: '', is_regex: false, weight: 0.5, category: 'custom' });
      fetchData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to create pattern');
    }
  };

  const handleToggle = async (p: PatternEntry) => {
    try {
      await updatePattern(p.id, { enabled: !p.enabled });
      fetchData();
    } catch {
      toast.error('Failed to toggle pattern');
    }
  };

  const handleDelete = async (p: PatternEntry) => {
    if (p.is_default) return;
    try {
      await deletePattern(p.id);
      toast.success('Pattern deleted');
      fetchData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to delete');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Heuristic Patterns</h3>
        <button onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-1.5 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600">
          <Plus className="h-4 w-4" /> Add Pattern
        </button>
      </div>

      {showAdd && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/60 p-4 space-y-3">
          <div className="flex gap-3">
            <input value={newPattern.pattern} onChange={e => setNewPattern(p => ({ ...p, pattern: e.target.value }))}
              placeholder="Pattern string..." className="flex-1 rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white" />
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={newPattern.is_regex} onChange={e => setNewPattern(p => ({ ...p, is_regex: e.target.checked }))} /> Regex
            </label>
          </div>
          <div className="flex gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Weight:</span>
              <input type="range" min="0.1" max="1.0" step="0.1" value={newPattern.weight}
                onChange={e => setNewPattern(p => ({ ...p, weight: parseFloat(e.target.value) }))} className="w-24" />
              <span className="text-xs text-white">{newPattern.weight.toFixed(1)}</span>
            </div>
            <select value={newPattern.category} onChange={e => setNewPattern(p => ({ ...p, category: e.target.value }))}
              className="rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white">
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <button onClick={handleCreate} className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-500">Add</button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-700/50">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-700 bg-slate-800/60">
            <tr>
              <th className="px-3 py-2 text-slate-400 font-medium">Pattern</th>
              <th className="px-3 py-2 text-slate-400 font-medium">Type</th>
              <th className="px-3 py-2 text-slate-400 font-medium">Weight</th>
              <th className="px-3 py-2 text-slate-400 font-medium">Category</th>
              <th className="px-3 py-2 text-slate-400 font-medium">Enabled</th>
              <th className="px-3 py-2 text-slate-400 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {loading ? (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-500">Loading...</td></tr>
            ) : patterns.map(p => (
              <tr key={p.id} className={`${p.is_default ? 'bg-slate-800/20' : ''} hover:bg-slate-800/40`}>
                <td className="px-3 py-2 font-mono text-xs text-white">{p.pattern}</td>
                <td className="px-3 py-2">
                  {p.is_regex
                    ? <span className="flex items-center gap-1 text-xs text-purple-300"><Code className="h-3 w-3" /> regex</span>
                    : <span className="flex items-center gap-1 text-xs text-slate-400"><Type className="h-3 w-3" /> substring</span>
                  }
                </td>
                <td className="px-3 py-2 text-slate-300">{p.weight.toFixed(1)}</td>
                <td className="px-3 py-2"><span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-300">{p.category}</span></td>
                <td className="px-3 py-2">
                  <button onClick={() => handleToggle(p)}
                    className={`relative h-5 w-9 rounded-full transition-colors ${p.enabled ? 'bg-blue-600' : 'bg-slate-600'}`}>
                    <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${p.enabled ? 'left-[18px]' : 'left-0.5'}`} />
                  </button>
                </td>
                <td className="px-3 py-2">
                  {!p.is_default && (
                    <button onClick={() => handleDelete(p)} className="rounded p-1 text-red-400 hover:bg-red-500/10">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
