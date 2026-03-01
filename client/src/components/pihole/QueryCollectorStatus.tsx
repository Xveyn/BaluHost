import { useState, useEffect } from "react";
import { Database, RefreshCw, Power, PowerOff } from "lucide-react";
import toast from "react-hot-toast";
import {
  getCollectorStatus,
  updateCollectorConfig,
  type QueryCollectorStatus as CollectorStatus,
} from "../../api/pihole";

export default function QueryCollectorStatus() {
  const [status, setStatus] = useState<CollectorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pollInterval, setPollInterval] = useState(30);
  const [retentionDays, setRetentionDays] = useState(30);

  const fetchStatus = async () => {
    try {
      const data = await getCollectorStatus();
      setStatus(data);
      setPollInterval(data.poll_interval_seconds);
      setRetentionDays(data.retention_days);
    } catch {
      // Silently fail — collector might not be initialized yet
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleToggle = async () => {
    if (!status) return;
    setSaving(true);
    try {
      const data = await updateCollectorConfig({ is_enabled: !status.is_enabled });
      setStatus(data);
      toast.success(data.is_enabled ? "Collector enabled" : "Collector disabled");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to update collector");
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const data = await updateCollectorConfig({
        poll_interval_seconds: pollInterval,
        retention_days: retentionDays,
      });
      setStatus(data);
      toast.success("Collector settings saved");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
        <div className="h-32 animate-pulse rounded bg-slate-700" />
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Database className="h-5 w-5 text-slate-400" />
          <h4 className="text-sm font-medium text-slate-200">
            DNS Query Collector
          </h4>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
              status.running
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-slate-700/50 text-slate-400"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                status.running ? "bg-emerald-400" : "bg-slate-500"
              }`}
            />
            {status.running ? "Running" : "Stopped"}
          </span>
          <button
            onClick={handleToggle}
            disabled={saving}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              status.is_enabled
                ? "bg-red-500/20 text-red-400 hover:bg-red-500/30"
                : "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30"
            }`}
          >
            {status.is_enabled ? (
              <span className="flex items-center gap-1"><PowerOff className="h-3.5 w-3.5" /> Disable</span>
            ) : (
              <span className="flex items-center gap-1"><Power className="h-3.5 w-3.5" /> Enable</span>
            )}
          </button>
        </div>
      </div>

      {/* Status Info */}
      <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
        <div>
          <span className="text-slate-400">Total Queries Stored</span>
          <p className="text-lg font-semibold text-slate-200">
            {status.total_queries_stored.toLocaleString()}
          </p>
        </div>
        <div>
          <span className="text-slate-400">Last Poll</span>
          <p className="text-slate-200">
            {status.last_poll_at
              ? new Date(status.last_poll_at).toLocaleString([], {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "Never"}
          </p>
        </div>
      </div>

      {/* Error Display */}
      {status.last_error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          Last error: {status.last_error}
          {status.last_error_at && (
            <span className="text-red-400/70">
              {" "}({new Date(status.last_error_at).toLocaleString()})
            </span>
          )}
        </div>
      )}

      {/* Configuration */}
      <div className="grid grid-cols-2 gap-4 border-t border-slate-700/50 pt-4">
        <div>
          <label className="mb-1 block text-xs text-slate-400">
            Poll Interval (seconds)
          </label>
          <input
            type="number"
            min={10}
            max={300}
            value={pollInterval}
            onChange={(e) => setPollInterval(Number(e.target.value))}
            className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-1.5 px-3 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">
            Retention (days)
          </label>
          <input
            type="number"
            min={1}
            max={365}
            value={retentionDays}
            onChange={(e) => setRetentionDays(Number(e.target.value))}
            className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-1.5 px-3 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
          />
        </div>
      </div>
      <div className="mt-3 flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${saving ? "animate-spin" : ""}`} />
          Save
        </button>
      </div>
    </div>
  );
}
