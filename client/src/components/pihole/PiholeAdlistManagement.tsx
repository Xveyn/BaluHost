import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, RefreshCw, Download } from "lucide-react";
import toast from "react-hot-toast";
import {
  getAdlists,
  addAdlist,
  removeAdlist,
  toggleAdlist,
  updateGravity,
} from "../../api/pihole";

interface AdlistRow {
  id: number;
  url: string;
  comment?: string;
  domain_count?: number;
  enabled: boolean;
}

export default function PiholeAdlistManagement() {
  const [adlists, setAdlists] = useState<AdlistRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [newComment, setNewComment] = useState("");
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [updatingGravity, setUpdatingGravity] = useState(false);

  const fetchAdlists = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getAdlists();
      setAdlists(result.lists.map((l) => ({ id: l.id ?? 0, url: l.url, comment: l.comment, domain_count: l.number, enabled: l.enabled })));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to load adlists");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAdlists();
  }, [fetchAdlists]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedUrl = newUrl.trim();
    if (!trimmedUrl) return;

    setAdding(true);
    try {
      await addAdlist(trimmedUrl, newComment.trim() || undefined);
      toast.success("Adlist added");
      setNewUrl("");
      setNewComment("");
      await fetchAdlists();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to add adlist");
    } finally {
      setAdding(false);
    }
  };

  const handleToggle = async (url: string, id: number, currentEnabled: boolean) => {
    setTogglingId(id);
    try {
      await toggleAdlist(url, !currentEnabled);
      toast.success(currentEnabled ? "Adlist disabled" : "Adlist enabled");
      await fetchAdlists();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to toggle adlist");
    } finally {
      setTogglingId(null);
    }
  };

  const handleRemove = async (url: string, id: number) => {
    setRemovingId(id);
    try {
      await removeAdlist(url);
      toast.success("Adlist removed");
      await fetchAdlists();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to remove adlist");
    } finally {
      setRemovingId(null);
    }
  };

  const handleUpdateGravity = async () => {
    setUpdatingGravity(true);
    try {
      await updateGravity();
      toast.success("Gravity updated successfully");
      await fetchAdlists();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to update gravity");
    } finally {
      setUpdatingGravity(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-700/50 px-4 py-3">
        <h3 className="text-sm font-medium text-slate-300">
          Adlists (Blocklists)
        </h3>
        <button
          onClick={handleUpdateGravity}
          disabled={updatingGravity}
          className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {updatingGravity ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Update Gravity
        </button>
      </div>

      {/* Table */}
      <div className="max-h-96 overflow-y-auto p-4">
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-10 animate-pulse rounded bg-slate-700/40"
              />
            ))}
          </div>
        ) : adlists.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">
            No adlists configured
          </p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-700/50 text-xs uppercase text-slate-500">
                <th className="pb-2 pr-4">URL</th>
                <th className="pb-2 pr-4">Comment</th>
                <th className="pb-2 pr-4 text-right">Domains</th>
                <th className="pb-2 pr-4 text-center">Enabled</th>
                <th className="pb-2 w-10" />
              </tr>
            </thead>
            <tbody>
              {adlists.map((al) => (
                <tr
                  key={al.id}
                  className={`border-b border-slate-700/30 hover:bg-slate-700/20 ${!al.enabled ? "opacity-50" : ""}`}
                >
                  <td className="max-w-xs truncate py-2.5 pr-4 font-mono text-xs text-slate-200">
                    {al.url}
                  </td>
                  <td className="py-2.5 pr-4 text-xs text-slate-500">
                    {al.comment || "—"}
                  </td>
                  <td className="py-2.5 pr-4 text-right text-xs text-slate-400">
                    {al.domain_count != null
                      ? al.domain_count.toLocaleString()
                      : "—"}
                  </td>
                  <td className="py-2.5 pr-4 text-center">
                    <button
                      onClick={() => handleToggle(al.url, al.id, al.enabled)}
                      disabled={togglingId === al.id}
                      className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none disabled:opacity-50"
                      style={{ backgroundColor: al.enabled ? '#0284c7' : '#334155' }}
                    >
                      {togglingId === al.id ? (
                        <RefreshCw className="mx-auto h-3 w-3 animate-spin text-white" />
                      ) : (
                        <span
                          className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${al.enabled ? "translate-x-4.5" : "translate-x-1"}`}
                        />
                      )}
                    </button>
                  </td>
                  <td className="py-2.5">
                    <button
                      onClick={() => handleRemove(al.url, al.id)}
                      disabled={removingId === al.id}
                      className="rounded p-1 text-slate-500 hover:bg-red-500/20 hover:text-red-400 disabled:opacity-50"
                    >
                      {removingId === al.id ? (
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
            <label className="mb-1 block text-xs text-slate-500">URL</label>
            <input
              type="url"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="https://example.com/blocklist.txt"
              className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
            />
          </div>
          <div className="w-48">
            <label className="mb-1 block text-xs text-slate-500">
              Comment (optional)
            </label>
            <input
              type="text"
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              placeholder="Description..."
              className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
            />
          </div>
          <button
            type="submit"
            disabled={adding || !newUrl.trim()}
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
