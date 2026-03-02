import { useState, useEffect } from "react";
import { Shield, ShieldOff, Clock, Server, ArrowRightLeft } from "lucide-react";
import { formatUptime } from "../../lib/formatters";
import type { PiholeStatus, FailoverStatus } from "../../api/pihole";
import { getFailoverStatus } from "../../api/pihole";

interface PiholeStatusBarProps {
  status: PiholeStatus;
  onBlockingToggle: (enabled: boolean) => void;
  loading: boolean;
}

export default function PiholeStatusBar({
  status,
  onBlockingToggle,
  loading,
}: PiholeStatusBarProps) {
  const [failover, setFailover] = useState<FailoverStatus | null>(null);

  useEffect(() => {
    getFailoverStatus().then(setFailover).catch(() => {});
    const interval = setInterval(() => {
      getFailoverStatus().then(setFailover).catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const statusColor =
    status.container_status === "running"
      ? "bg-emerald-500"
      : status.container_status === "stopped"
        ? "bg-red-500"
        : "bg-yellow-500";

  const statusLabel =
    status.container_status === "running"
      ? "Running"
      : status.container_status === "stopped"
        ? "Stopped"
        : "Connecting";

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-slate-700/50 bg-slate-800/60 px-5 py-3">
      {/* Container status */}
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${statusColor}`} />
        {loading ? (
          <div className="h-4 w-20 animate-pulse rounded bg-slate-700" />
        ) : (
          <span className="text-sm text-slate-300">{statusLabel}</span>
        )}
      </div>

      {/* Divider */}
      <div className="hidden sm:block h-5 w-px bg-slate-700" />

      {/* Version */}
      <div className="flex items-center gap-1.5 text-sm text-slate-400">
        <Server className="h-3.5 w-3.5" />
        {loading ? (
          <div className="h-4 w-16 animate-pulse rounded bg-slate-700" />
        ) : (
          <span>{status.version || "N/A"}</span>
        )}
      </div>

      {/* Divider */}
      <div className="hidden sm:block h-5 w-px bg-slate-700" />

      {/* Mode badge */}
      <span
        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
          status.mode === "docker"
            ? "bg-sky-500/20 text-sky-400"
            : status.mode === "remote"
              ? "bg-violet-500/20 text-violet-400"
              : "bg-amber-500/20 text-amber-400"
        }`}
      >
        {status.mode === "docker"
          ? "Docker"
          : status.mode === "remote"
            ? "Remote"
            : "Dev"}
      </span>

      {/* Failover badge */}
      {failover && failover.remote_configured && (
        <>
          <div className="hidden sm:block h-5 w-px bg-slate-700" />
          <div
            className={`flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
              failover.failover_active
                ? "bg-amber-500/20 text-amber-400"
                : "bg-emerald-500/20 text-emerald-400"
            }`}
            title={
              failover.last_failover_at
                ? `Last failover: ${new Date(failover.last_failover_at).toLocaleString()}`
                : undefined
            }
          >
            <ArrowRightLeft className="h-3 w-3" />
            {failover.failover_active
              ? "Failover: NAS"
              : "Active: Pi"}
          </div>
        </>
      )}

      {/* Divider */}
      <div className="hidden sm:block h-5 w-px bg-slate-700" />

      {/* Uptime */}
      <div className="flex items-center gap-1.5 text-sm text-slate-400">
        <Clock className="h-3.5 w-3.5" />
        {loading ? (
          <div className="h-4 w-24 animate-pulse rounded bg-slate-700" />
        ) : (
          <span>{status.uptime != null ? formatUptime(status.uptime) : "\u2014"}</span>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Blocking toggle */}
      <button
        onClick={() => onBlockingToggle(!status.blocking_enabled)}
        disabled={loading || status.container_status !== "running"}
        className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
          status.blocking_enabled
            ? "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30"
            : "bg-red-500/20 text-red-400 hover:bg-red-500/30"
        } disabled:cursor-not-allowed disabled:opacity-50`}
      >
        {status.blocking_enabled ? (
          <>
            <Shield className="h-4 w-4" />
            Blocking Enabled
          </>
        ) : (
          <>
            <ShieldOff className="h-4 w-4" />
            Blocking Disabled
          </>
        )}
      </button>
    </div>
  );
}
