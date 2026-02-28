import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, RefreshCw, Globe } from "lucide-react";
import toast from "react-hot-toast";
import {
  getLocalDns,
  addLocalDns,
  removeLocalDns,
} from "../../api/pihole";

interface DnsRecord {
  domain: string;
  ip: string;
}

export default function PiholeLocalDns() {
  const [records, setRecords] = useState<DnsRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [newIp, setNewIp] = useState("");
  const [adding, setAdding] = useState(false);
  const [removingDomain, setRemovingDomain] = useState<string | null>(null);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getLocalDns();
      setRecords(result.records);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to load DNS records");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedDomain = newDomain.trim();
    const trimmedIp = newIp.trim();
    if (!trimmedDomain || !trimmedIp) return;

    setAdding(true);
    try {
      await addLocalDns(trimmedDomain, trimmedIp);
      toast.success("DNS record added");
      setNewDomain("");
      setNewIp("");
      await fetchRecords();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to add DNS record");
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (domain: string, ip: string) => {
    setRemovingDomain(domain);
    try {
      await removeLocalDns(domain, ip);
      toast.success(`Removed ${domain}`);
      await fetchRecords();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to remove DNS record");
    } finally {
      setRemovingDomain(null);
    }
  };

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-slate-700/50 px-4 py-3">
        <Globe className="h-4 w-4 text-sky-400" />
        <h3 className="text-sm font-medium text-slate-300">
          Local DNS Records
        </h3>
      </div>

      {/* Table */}
      <div className="max-h-80 overflow-y-auto p-4">
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-10 animate-pulse rounded bg-slate-700/40"
              />
            ))}
          </div>
        ) : records.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">
            No local DNS records
          </p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-700/50 text-xs uppercase text-slate-500">
                <th className="pb-2 pr-4">Domain</th>
                <th className="pb-2 pr-4">IP Address</th>
                <th className="pb-2 w-10" />
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => (
                <tr
                  key={i}
                  className="border-b border-slate-700/30 hover:bg-slate-700/20"
                >
                  <td className="py-2.5 pr-4 font-mono text-xs text-slate-200">
                    {r.domain}
                  </td>
                  <td className="py-2.5 pr-4 font-mono text-xs text-slate-400">
                    {r.ip}
                  </td>
                  <td className="py-2.5">
                    <button
                      onClick={() => handleRemove(r.domain, r.ip)}
                      disabled={removingDomain === r.domain}
                      className="rounded p-1 text-slate-500 hover:bg-red-500/20 hover:text-red-400 disabled:opacity-50"
                    >
                      {removingDomain === r.domain ? (
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Add form */}
      <div className="border-t border-slate-700/50 p-4">
        <form onSubmit={handleAdd} className="flex items-end gap-2">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-slate-500">Domain</label>
            <input
              type="text"
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              placeholder="mydevice.local"
              className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
            />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs text-slate-500">
              IP Address
            </label>
            <input
              type="text"
              value={newIp}
              onChange={(e) => setNewIp(e.target.value)}
              placeholder="192.168.1.100"
              className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
            />
          </div>
          <button
            type="submit"
            disabled={adding || !newDomain.trim() || !newIp.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {adding ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Add
          </button>
        </form>
      </div>
    </div>
  );
}
