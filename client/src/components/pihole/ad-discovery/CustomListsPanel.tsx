import { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, Download, Upload, ChevronDown, ChevronUp, X, Rocket } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getCustomLists, createCustomList, deleteCustomList, deployCustomList,
  undeployCustomList, exportCustomList, getCustomListDomains,
  addCustomListDomains, removeCustomListDomain,
  type CustomListEntry, type CustomListDomainEntry,
} from '../../../api/adDiscovery';

export default function CustomListsPanel() {
  const [lists, setLists] = useState<CustomListEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newList, setNewList] = useState({ name: '', description: '' });
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [domains, setDomains] = useState<CustomListDomainEntry[]>([]);
  const [domainsPage, setDomainsPage] = useState(1);
  const [newDomains, setNewDomains] = useState('');

  const fetchLists = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getCustomLists();
      setLists(result.lists);
    } catch {
      toast.error('Failed to load custom lists');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchLists(); }, [fetchLists]);

  const fetchDomains = useCallback(async (listId: number, page = 1) => {
    try {
      const result = await getCustomListDomains(listId, page);
      setDomains(result.domains);
      setDomainsPage(page);
    } catch {
      toast.error('Failed to load domains');
    }
  }, []);

  const handleExpand = (id: number) => {
    if (expandedId === id) { setExpandedId(null); return; }
    setExpandedId(id);
    fetchDomains(id);
  };

  const handleCreate = async () => {
    if (!newList.name.trim()) return;
    try {
      await createCustomList(newList);
      toast.success('List created');
      setShowCreate(false);
      setNewList({ name: '', description: '' });
      fetchLists();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to create list');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteCustomList(id);
      toast.success('List deleted');
      if (expandedId === id) setExpandedId(null);
      fetchLists();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to delete');
    }
  };

  const handleDeploy = async (id: number) => {
    try {
      await deployCustomList(id);
      toast.success('List deployed to Pi-hole');
      fetchLists();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to deploy');
    }
  };

  const handleUndeploy = async (id: number) => {
    try {
      await undeployCustomList(id);
      toast.success('List undeployed');
      fetchLists();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to undeploy');
    }
  };

  const handleExport = async (id: number, name: string) => {
    try {
      const blob = await exportCustomList(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${name.replace(/\s+/g, '_')}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Failed to export');
    }
  };

  const handleAddDomains = async (listId: number) => {
    const domainsArr = newDomains.split(/[\n,]/).map(d => d.trim()).filter(Boolean);
    if (!domainsArr.length) return;
    try {
      await addCustomListDomains(listId, domainsArr);
      toast.success(`${domainsArr.length} domain(s) added`);
      setNewDomains('');
      fetchDomains(listId, domainsPage);
      fetchLists();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to add domains');
    }
  };

  const handleRemoveDomain = async (listId: number, domain: string) => {
    try {
      await removeCustomListDomain(listId, domain);
      toast.success('Domain removed');
      fetchDomains(listId, domainsPage);
      fetchLists();
    } catch {
      toast.error('Failed to remove domain');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Custom Blocklists</h3>
        <button onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600">
          <Plus className="h-4 w-4" /> Create List
        </button>
      </div>

      {showCreate && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/60 p-4 space-y-3">
          <input value={newList.name} onChange={e => setNewList(l => ({ ...l, name: e.target.value }))}
            placeholder="List name" className="w-full rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white" />
          <input value={newList.description} onChange={e => setNewList(l => ({ ...l, description: e.target.value }))}
            placeholder="Description (optional)" className="w-full rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white" />
          <button onClick={handleCreate} className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-500">Create</button>
        </div>
      )}

      {loading ? (
        <p className="text-center text-sm text-slate-500">Loading...</p>
      ) : lists.length === 0 ? (
        <p className="text-center text-sm text-slate-500">No custom lists yet</p>
      ) : (
        <div className="space-y-3">
          {lists.map(l => (
            <div key={l.id} className="rounded-lg border border-slate-700 bg-slate-800/40">
              <div className="flex items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <button onClick={() => handleExpand(l.id)} className="text-slate-400 hover:text-white">
                    {expandedId === l.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-white text-sm">{l.name}</span>
                      {l.deployed
                        ? <span className="rounded-full bg-green-500/20 px-2 py-0.5 text-xs text-green-300">Active</span>
                        : <span className="rounded-full bg-slate-500/20 px-2 py-0.5 text-xs text-slate-400">Not deployed</span>
                      }
                    </div>
                    {l.description && <p className="text-xs text-slate-500">{l.description}</p>}
                    <span className="text-xs text-slate-400">{l.domain_count} domains</span>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {l.deployed
                    ? <button onClick={() => handleUndeploy(l.id)} title="Undeploy" className="rounded p-1.5 text-orange-400 hover:bg-orange-500/10"><Rocket className="h-4 w-4" /></button>
                    : <button onClick={() => handleDeploy(l.id)} title="Deploy" className="rounded p-1.5 text-green-400 hover:bg-green-500/10"><Upload className="h-4 w-4" /></button>
                  }
                  <button onClick={() => handleExport(l.id, l.name)} title="Export" className="rounded p-1.5 text-blue-400 hover:bg-blue-500/10"><Download className="h-4 w-4" /></button>
                  <button onClick={() => handleDelete(l.id)} title="Delete" className="rounded p-1.5 text-red-400 hover:bg-red-500/10"><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>

              {expandedId === l.id && (
                <div className="border-t border-slate-700 p-4 space-y-3">
                  {/* Add domains */}
                  <div className="flex gap-2">
                    <input value={newDomains} onChange={e => setNewDomains(e.target.value)}
                      placeholder="Add domains (comma or newline separated)"
                      className="flex-1 rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white" />
                    <button onClick={() => handleAddDomains(l.id)}
                      className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-500">Add</button>
                  </div>
                  {/* Domain list */}
                  <div className="max-h-64 overflow-y-auto space-y-1">
                    {domains.map((d: CustomListDomainEntry) => (
                      <div key={d.id} className="flex items-center justify-between rounded bg-slate-800/60 px-3 py-1.5">
                        <span className="font-mono text-xs text-slate-300">{d.domain}</span>
                        <button onClick={() => handleRemoveDomain(l.id, d.domain)}
                          className="text-slate-500 hover:text-red-400"><X className="h-3.5 w-3.5" /></button>
                      </div>
                    ))}
                    {domains.length === 0 && <p className="text-center text-xs text-slate-500 py-2">No domains yet</p>}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
