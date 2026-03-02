import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";
import { getDomains, addDomain, removeDomain } from "../../api/pihole";

type ListType = "deny_exact" | "deny_regex" | "allow_exact" | "allow_regex";

function splitTab(tab: ListType): [string, string] {
  const [listType, kind] = tab.split("_");
  return [listType, kind];
}

interface DomainRow {
  id: number;
  domain: string;
  comment?: string;
}

const TABS: { key: ListType; label: string }[] = [
  { key: "deny_exact", label: "Deny / Exact" },
  { key: "deny_regex", label: "Deny / Regex" },
  { key: "allow_exact", label: "Allow / Exact" },
  { key: "allow_regex", label: "Allow / Regex" },
];

export default function PiholeDomainManagement() {
  const [activeTab, setActiveTab] = useState<ListType>("deny_exact");
  const [domains, setDomains] = useState<DomainRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);

  const fetchDomains = useCallback(async () => {
    setLoading(true);
    try {
      const [listType, kind] = splitTab(activeTab);
      const result = await getDomains(listType, kind);
      setDomains(result.domains.map((d) => ({ id: d.id ?? 0, domain: d.domain, comment: d.comment })));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to load domains");
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchDomains();
  }, [fetchDomains]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newDomain.trim();
    if (!trimmed) return;

    setAdding(true);
    try {
      const [lt, k] = splitTab(activeTab);
      await addDomain(lt, k, trimmed);
      toast.success("Domain added");
      setNewDomain("");
      await fetchDomains();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to add domain");
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (id: number, domain: string) => {
    setRemovingId(id);
    try {
      const [lt, k] = splitTab(activeTab);
      await removeDomain(lt, k, domains.find((d) => d.id === id)?.domain ?? "");
      toast.success(`Removed ${domain}`);
      await fetchDomains();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to remove domain");
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60">
      {/* Tab bar */}
      <div className="flex overflow-x-auto border-b border-slate-700/50 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-shrink-0 whitespace-nowrap px-3 py-2.5 text-center text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "border-b-2 border-sky-500 text-sky-400"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Domain table */}
        <div className="mb-4 max-h-80 overflow-y-auto overflow-x-auto">
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-10 animate-pulse rounded bg-slate-700/40"
                />
              ))}
            </div>
          ) : domains.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">
              No domains in this list
            </p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 text-xs uppercase text-slate-500">
                  <th className="pb-2 pr-4">Domain</th>
                  <th className="pb-2 pr-4">Comment</th>
                  <th className="pb-2 w-10" />
                </tr>
              </thead>
              <tbody>
                {domains.map((d) => (
                  <tr
                    key={d.id}
                    className="border-b border-slate-700/30 hover:bg-slate-700/20"
                  >
                    <td className="py-2 pr-4 font-mono text-xs text-slate-200">
                      {d.domain}
                    </td>
                    <td className="py-2 pr-4 text-xs text-slate-500">
                      {d.comment || "—"}
                    </td>
                    <td className="py-2">
                      <button
                        onClick={() => handleRemove(d.id, d.domain)}
                        disabled={removingId === d.id}
                        className="rounded p-1 text-slate-500 hover:bg-red-500/20 hover:text-red-400 disabled:opacity-50"
                      >
                        {removingId === d.id ? (
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
        <form
          onSubmit={handleAdd}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={newDomain}
            onChange={(e) => setNewDomain(e.target.value)}
            placeholder={
              activeTab.includes("regex")
                ? "Enter regex pattern..."
                : "Enter domain..."
            }
            className="flex-1 rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
          />
          <button
            type="submit"
            disabled={adding || !newDomain.trim()}
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
