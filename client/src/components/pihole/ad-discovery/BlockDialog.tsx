import { useState, useEffect } from 'react';
import { Shield, List, X } from 'lucide-react';
import { getCustomLists, type CustomListEntry } from '../../../api/adDiscovery';

interface BlockDialogProps {
  domain: string;
  onConfirm: (target: string, listId?: number) => void;
  onCancel: () => void;
}

export default function BlockDialog({ domain, onConfirm, onCancel }: BlockDialogProps) {
  const [target, setTarget] = useState<'deny_list' | 'custom_list'>('deny_list');
  const [listId, setListId] = useState<number | undefined>();
  const [lists, setLists] = useState<CustomListEntry[]>([]);

  useEffect(() => {
    getCustomLists().then(r => setLists(r.lists)).catch(() => {});
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onCancel}>
      <div className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-800 p-6 shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">Block Domain</h3>
          <button onClick={onCancel} className="text-slate-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>
        <p className="mb-4 text-sm text-slate-300">
          Block <code className="rounded bg-slate-700 px-1.5 py-0.5 text-blue-300">{domain}</code>
        </p>
        <div className="space-y-3">
          <label className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 ${target === 'deny_list' ? 'border-blue-500 bg-blue-500/10' : 'border-slate-600 hover:border-slate-500'}`}>
            <input type="radio" checked={target === 'deny_list'} onChange={() => setTarget('deny_list')} className="hidden" />
            <Shield className="h-5 w-5 text-blue-400" />
            <div>
              <div className="text-sm font-medium text-white">Pi-hole Deny List</div>
              <div className="text-xs text-slate-400">Block this domain directly</div>
            </div>
          </label>
          <label className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 ${target === 'custom_list' ? 'border-blue-500 bg-blue-500/10' : 'border-slate-600 hover:border-slate-500'}`}>
            <input type="radio" checked={target === 'custom_list'} onChange={() => setTarget('custom_list')} className="hidden" />
            <List className="h-5 w-5 text-green-400" />
            <div>
              <div className="text-sm font-medium text-white">Custom List</div>
              <div className="text-xs text-slate-400">Add to a named blocklist</div>
            </div>
          </label>
          {target === 'custom_list' && lists.length > 0 && (
            <select
              value={listId ?? ''}
              onChange={e => setListId(Number(e.target.value) || undefined)}
              className="w-full rounded-md border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-white"
            >
              <option value="">Select a list...</option>
              {lists.map(l => <option key={l.id} value={l.id}>{l.name} ({l.domain_count} domains)</option>)}
            </select>
          )}
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button onClick={onCancel} className="rounded-md px-4 py-2 text-sm text-slate-300 hover:text-white">Cancel</button>
          <button
            onClick={() => onConfirm(target, listId)}
            disabled={target === 'custom_list' && !listId}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
          >
            Block
          </button>
        </div>
      </div>
    </div>
  );
}
