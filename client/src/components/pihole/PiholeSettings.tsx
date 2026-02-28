import { useState, useEffect } from "react";
import { Settings, Save, RefreshCw, Wifi, WifiOff, Monitor, Shield } from "lucide-react";
import toast from "react-hot-toast";
import {
  getPiholeConfig,
  updatePiholeConfig,
  getFailoverStatus,
  type FailoverStatus,
} from "../../api/pihole";

interface LocalConfig {
  mode: "docker" | "remote" | "disabled";
  pihole_url?: string;
  password?: string;
  upstream_dns?: string;
  docker_image_tag?: string;
  web_port?: number;
  vpn_dns_enabled?: boolean;
  remote_pihole_url?: string;
  remote_password?: string;
  health_check_interval?: number;
  has_password?: boolean;
  has_remote_password?: boolean;
  // DNS settings
  dns_dnssec?: boolean;
  dns_rev_server?: string | null;
  dns_rate_limit_count?: number;
  dns_rate_limit_interval?: number;
  dns_domain_needed?: boolean;
  dns_bogus_priv?: boolean;
  dns_domain_name?: string;
  dns_expand_hosts?: boolean;
}

export default function PiholeSettings() {
  const [config, setConfig] = useState<LocalConfig>({
    mode: "disabled",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [remotePasswordVisible, setRemotePasswordVisible] = useState(false);
  const [failoverStatus, setFailoverStatus] = useState<FailoverStatus | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [result, foStatus] = await Promise.all([
          getPiholeConfig(),
          getFailoverStatus().catch(() => null),
        ]);
        setConfig(result as unknown as LocalConfig);
        setFailoverStatus(foStatus);
      } catch (err: any) {
        toast.error(err?.response?.data?.detail || "Failed to load Pi-hole configuration");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { ...config };
      if (!payload.password) delete payload.password;
      if (!payload.remote_password) delete payload.remote_password;
      await updatePiholeConfig(payload);
      toast.success("Configuration saved");
      // Refresh failover status
      const foStatus = await getFailoverStatus().catch(() => null);
      setFailoverStatus(foStatus);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  const updateField = <K extends keyof LocalConfig>(
    key: K,
    value: LocalConfig[K]
  ) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-6">
        <div className="space-y-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-slate-700/40" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Main Configuration */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/60">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-slate-700/50 px-4 py-3">
          <Settings className="h-4 w-4 text-sky-400" />
          <h3 className="text-sm font-medium text-slate-300">
            Pi-hole Configuration
          </h3>
        </div>

        <div className="space-y-4 p-4">
          {/* Mode */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Mode
            </label>
            <div className="flex gap-2">
              {(["docker", "remote", "disabled"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => updateField("mode", mode)}
                  className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                    config.mode === mode
                      ? "bg-sky-600 text-white"
                      : "bg-slate-700/50 text-slate-400 hover:bg-slate-700 hover:text-slate-200"
                  }`}
                >
                  {mode === "docker"
                    ? "Docker"
                    : mode === "remote"
                      ? "Remote"
                      : "Disabled"}
                </button>
              ))}
            </div>
          </div>

          {/* Pi-hole URL (remote mode) */}
          {config.mode === "remote" && (
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">
                Pi-hole URL
              </label>
              <input
                type="url"
                value={config.pihole_url ?? ""}
                onChange={(e) => updateField("pihole_url", e.target.value)}
                placeholder="http://192.168.1.2"
                className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
              />
            </div>
          )}

          {/* Password */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Password
            </label>
            <div className="flex gap-2">
              <input
                type={passwordVisible ? "text" : "password"}
                value={config.password ?? ""}
                onChange={(e) => updateField("password", e.target.value)}
                placeholder={config.has_password ? "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022  (auto-generated)" : "Pi-hole admin password"}
                className="flex-1 rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
              />
              <button
                type="button"
                onClick={() => setPasswordVisible(!passwordVisible)}
                className="rounded-lg bg-slate-700/50 px-3 py-2 text-xs text-slate-400 hover:bg-slate-700 hover:text-slate-200"
              >
                {passwordVisible ? "Hide" : "Show"}
              </button>
            </div>
            {config.has_password && !config.password && (
              <p className="mt-1 text-xs text-slate-500">
                Password is set. Leave empty to keep current.
              </p>
            )}
          </div>

          {/* Upstream DNS */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Upstream DNS
            </label>
            <input
              type="text"
              value={config.upstream_dns ?? ""}
              onChange={(e) => updateField("upstream_dns", e.target.value)}
              placeholder="1.1.1.1;8.8.8.8"
              className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
            />
            <p className="mt-1 text-xs text-slate-600">
              Semicolon-separated list of upstream DNS servers
            </p>
          </div>

          {/* Docker image tag */}
          {config.mode === "docker" && (
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">
                Docker Image Tag
              </label>
              <input
                type="text"
                value={config.docker_image_tag ?? ""}
                onChange={(e) => updateField("docker_image_tag", e.target.value)}
                placeholder="latest"
                className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
              />
            </div>
          )}

          {/* Web port */}
          {config.mode === "docker" && (
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">
                Web Port
              </label>
              <input
                type="number"
                value={config.web_port ?? 8080}
                onChange={(e) =>
                  updateField("web_port", parseInt(e.target.value, 10) || 8080)
                }
                min={1}
                max={65535}
                className="w-48 rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
              />
            </div>
          )}

          {/* VPN DNS toggle */}
          <div className="flex items-center justify-between rounded-lg bg-slate-900/40 px-3 py-2.5">
            <div>
              <p className="text-sm text-slate-300">Use as VPN DNS</p>
              <p className="text-xs text-slate-500">
                Route VPN client DNS queries through Pi-hole
              </p>
            </div>
            <button
              onClick={() =>
                updateField("vpn_dns_enabled", !config.vpn_dns_enabled)
              }
              className={`relative h-6 w-11 p-0 rounded-full transition-colors ${
                config.vpn_dns_enabled ? "bg-sky-600" : "bg-slate-600"
              }`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                  config.vpn_dns_enabled ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* Remote Pi-hole (Failover) */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/60">
        <div className="flex items-center gap-2 border-b border-slate-700/50 px-4 py-3">
          <Monitor className="h-4 w-4 text-violet-400" />
          <h3 className="text-sm font-medium text-slate-300">
            Raspberry Pi (Remote Primary)
          </h3>
          {failoverStatus && failoverStatus.remote_configured && (
            <span
              className={`ml-auto flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                failoverStatus.remote_connected
                  ? "bg-emerald-500/20 text-emerald-400"
                  : "bg-red-500/20 text-red-400"
              }`}
            >
              {failoverStatus.remote_connected ? (
                <Wifi className="h-3 w-3" />
              ) : (
                <WifiOff className="h-3 w-3" />
              )}
              {failoverStatus.remote_connected ? "Connected" : "Not connected"}
            </span>
          )}
        </div>

        <div className="space-y-4 p-4">
          <p className="text-xs text-slate-500">
            Configure a remote Pi-hole (e.g. Raspberry Pi) as primary DNS filter.
            If the remote Pi goes offline, the NAS Pi-hole takes over automatically.
          </p>

          {/* Remote URL */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Remote Pi-hole URL
            </label>
            <input
              type="url"
              value={config.remote_pihole_url ?? ""}
              onChange={(e) =>
                updateField("remote_pihole_url", e.target.value || undefined)
              }
              placeholder="http://192.168.1.50:80"
              className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
            />
            <p className="mt-1 text-xs text-slate-600">
              Leave empty to disable failover and use NAS Pi-hole only
            </p>
          </div>

          {/* Remote Password */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Remote Password
            </label>
            <div className="flex gap-2">
              <input
                type={remotePasswordVisible ? "text" : "password"}
                value={config.remote_password ?? ""}
                onChange={(e) => updateField("remote_password", e.target.value)}
                placeholder={config.has_remote_password ? "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022  (auto-generated)" : "Remote Pi-hole admin password"}
                className="flex-1 rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
              />
              <button
                type="button"
                onClick={() => setRemotePasswordVisible(!remotePasswordVisible)}
                className="rounded-lg bg-slate-700/50 px-3 py-2 text-xs text-slate-400 hover:bg-slate-700 hover:text-slate-200"
              >
                {remotePasswordVisible ? "Hide" : "Show"}
              </button>
            </div>
            {config.has_remote_password && !config.remote_password && (
              <p className="mt-1 text-xs text-slate-500">
                Password is set. Leave empty to keep current.
              </p>
            )}
          </div>

          {/* Health Check Interval */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Health Check Interval (seconds)
            </label>
            <input
              type="number"
              value={config.health_check_interval ?? 30}
              onChange={(e) =>
                updateField(
                  "health_check_interval",
                  parseInt(e.target.value, 10) || 30
                )
              }
              min={10}
              max={300}
              className="w-48 rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
            />
          </div>

          {/* Failover Status Display */}
          {failoverStatus && failoverStatus.remote_configured && (
            <div className="rounded-lg bg-slate-900/40 px-3 py-2.5">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Active Source</span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    failoverStatus.active_source === "remote"
                      ? "bg-violet-500/20 text-violet-400"
                      : failoverStatus.failover_active
                        ? "bg-amber-500/20 text-amber-400"
                        : "bg-sky-500/20 text-sky-400"
                  }`}
                >
                  {failoverStatus.active_source === "remote"
                    ? "Pi (Remote)"
                    : failoverStatus.failover_active
                      ? "NAS (Failover)"
                      : "NAS (Local)"}
                </span>
              </div>
              {failoverStatus.last_failover_at && (
                <p className="mt-1 text-xs text-slate-600">
                  Last failover:{" "}
                  {new Date(failoverStatus.last_failover_at).toLocaleString()}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Advanced DNS Settings (Docker mode only) */}
      {config.mode === "docker" && (
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/60">
          <div className="flex items-center gap-2 border-b border-slate-700/50 px-4 py-3">
            <Shield className="h-4 w-4 text-amber-400" />
            <h3 className="text-sm font-medium text-slate-300">
              Advanced DNS Settings
            </h3>
            <span className="ml-auto rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-400">
              FTLCONF
            </span>
          </div>

          <div className="space-y-4 p-4">
            <p className="text-xs text-slate-500">
              These settings are applied as FTLCONF environment variables when
              the container is deployed. They are read-only in the Pi-hole web UI.
            </p>

            {/* DNSSEC */}
            <div className="flex items-center justify-between rounded-lg bg-slate-900/40 px-3 py-2.5">
              <div>
                <p className="text-sm text-slate-300">DNSSEC</p>
                <p className="text-xs text-slate-500">
                  Validate DNS responses using DNSSEC signatures
                </p>
              </div>
              <button
                onClick={() => updateField("dns_dnssec", !config.dns_dnssec)}
                className={`relative h-6 w-11 p-0 rounded-full transition-colors ${
                  config.dns_dnssec ? "bg-sky-600" : "bg-slate-600"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                    config.dns_dnssec ? "translate-x-5" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>

            {/* Never Forward non-FQDN */}
            <div className="flex items-center justify-between rounded-lg bg-slate-900/40 px-3 py-2.5">
              <div>
                <p className="text-sm text-slate-300">Never Forward non-FQDN</p>
                <p className="text-xs text-slate-500">
                  Do not forward A and AAAA queries for plain names
                </p>
              </div>
              <button
                onClick={() =>
                  updateField("dns_domain_needed", !config.dns_domain_needed)
                }
                className={`relative h-6 w-11 p-0 rounded-full transition-colors ${
                  config.dns_domain_needed ? "bg-sky-600" : "bg-slate-600"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                    config.dns_domain_needed
                      ? "translate-x-5"
                      : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>

            {/* Never Forward Reverse Lookups */}
            <div className="flex items-center justify-between rounded-lg bg-slate-900/40 px-3 py-2.5">
              <div>
                <p className="text-sm text-slate-300">
                  Never Forward Reverse Lookups
                </p>
                <p className="text-xs text-slate-500">
                  Do not forward reverse lookups for private IP ranges
                </p>
              </div>
              <button
                onClick={() =>
                  updateField("dns_bogus_priv", !config.dns_bogus_priv)
                }
                className={`relative h-6 w-11 p-0 rounded-full transition-colors ${
                  config.dns_bogus_priv ? "bg-sky-600" : "bg-slate-600"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                    config.dns_bogus_priv ? "translate-x-5" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>

            {/* Expand Hostnames */}
            <div className="flex items-center justify-between rounded-lg bg-slate-900/40 px-3 py-2.5">
              <div>
                <p className="text-sm text-slate-300">Expand Hostnames</p>
                <p className="text-xs text-slate-500">
                  Add domain name to plain hostnames in /etc/hosts
                </p>
              </div>
              <button
                onClick={() =>
                  updateField("dns_expand_hosts", !config.dns_expand_hosts)
                }
                className={`relative h-6 w-11 p-0 rounded-full transition-colors ${
                  config.dns_expand_hosts ? "bg-sky-600" : "bg-slate-600"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                    config.dns_expand_hosts
                      ? "translate-x-5"
                      : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>

            {/* Domain Name */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">
                Domain Name
              </label>
              <input
                type="text"
                value={config.dns_domain_name ?? "lan"}
                onChange={(e) => updateField("dns_domain_name", e.target.value)}
                placeholder="lan"
                className="w-64 rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
              />
              <p className="mt-1 text-xs text-slate-600">
                Local domain name for your network
              </p>
            </div>

            {/* Conditional Forwarding */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">
                Conditional Forwarding
              </label>
              <input
                type="text"
                value={config.dns_rev_server ?? ""}
                onChange={(e) =>
                  updateField("dns_rev_server", e.target.value || null)
                }
                placeholder="true,192.168.178.0/24,192.168.178.1,fritz.box"
                className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
              />
              <p className="mt-1 text-xs text-slate-600">
                Format: enabled,network/CIDR,router-IP,local-domain (leave empty
                to disable)
              </p>
            </div>

            {/* Rate Limiting */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">
                Rate Limiting
              </label>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={config.dns_rate_limit_count ?? 1000}
                    onChange={(e) =>
                      updateField(
                        "dns_rate_limit_count",
                        parseInt(e.target.value, 10) || 0
                      )
                    }
                    min={0}
                    max={100000}
                    className="w-28 rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
                  />
                  <span className="text-xs text-slate-500">queries per</span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={config.dns_rate_limit_interval ?? 60}
                    onChange={(e) =>
                      updateField(
                        "dns_rate_limit_interval",
                        parseInt(e.target.value, 10) || 0
                      )
                    }
                    min={0}
                    max={86400}
                    className="w-28 rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
                  />
                  <span className="text-xs text-slate-500">seconds</span>
                </div>
              </div>
              <p className="mt-1 text-xs text-slate-600">
                Set count to 0 to disable rate limiting
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Save Configuration
        </button>
      </div>
    </div>
  );
}
