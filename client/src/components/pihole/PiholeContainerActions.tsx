import { useState, useEffect, useRef, useCallback } from "react";
import {
  Play,
  Square,
  Trash2,
  Download,
  RefreshCw,
  Terminal,
  Rocket,
  AlertTriangle,
  Copy,
  Check,
} from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import {
  deployContainer,
  startContainer,
  stopContainer,
  removeContainer,
  updateContainer,
  getContainerLogs,
} from "../../api/pihole";

export default function PiholeContainerActions() {
  const { t } = useTranslation();
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<string | null>(null);
  const [logs, setLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsVisible, setLogsVisible] = useState(false);
  const logsRef = useRef<HTMLPreElement>(null);

  // Deploy config
  const [deployImageTag, setDeployImageTag] = useState("latest");
  const [deployPort, setDeployPort] = useState("8080");
  const [deployUpstreamDns, setDeployUpstreamDns] = useState("1.1.1.1");
  const [showDeployForm, setShowDeployForm] = useState(false);

  // One-time password reveal after deploy
  const [deployedPassword, setDeployedPassword] = useState<string | null>(null);
  const [passwordCopied, setPasswordCopied] = useState(false);

  const scrollLogsToBottom = useCallback(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    scrollLogsToBottom();
  }, [logs, scrollLogsToBottom]);

  const runAction = async (
    action: string,
    fn: () => Promise<unknown>,
    successMsg: string
  ) => {
    setActionLoading(action);
    setConfirmAction(null);
    try {
      await fn();
      toast.success(successMsg);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || `Failed to ${action} container`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeploy = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionLoading("deploy");
    setConfirmAction(null);
    try {
      const result = await deployContainer({
        image_tag: deployImageTag,
        web_port: parseInt(deployPort, 10) || 8053,
        upstream_dns: deployUpstreamDns,
      });
      toast.success("Container deployed successfully");
      if (result.password) {
        setDeployedPassword(result.password);
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to deploy container");
    } finally {
      setActionLoading(null);
    }
    setShowDeployForm(false);
  };

  const handleCopyPassword = async () => {
    if (!deployedPassword) return;
    try {
      await navigator.clipboard.writeText(deployedPassword);
      setPasswordCopied(true);
      toast.success(t("pihole.copyPassword"));
      setTimeout(() => setPasswordCopied(false), 2000);
    } catch {
      toast.error("Failed to copy");
    }
  };

  const handleFetchLogs = async () => {
    setLogsLoading(true);
    setLogsVisible(true);
    try {
      const result = await getContainerLogs();
      setLogs(result.logs);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to fetch container logs");
    } finally {
      setLogsLoading(false);
    }
  };

  const actionBtn = (
    key: string,
    label: string,
    icon: React.ReactNode,
    color: string,
    needsConfirm: boolean
  ) => {
    const isLoading = actionLoading === key;

    if (confirmAction === key) {
      return (
        <div className="flex items-center gap-2">
          <span className="text-xs text-amber-400">Are you sure?</span>
          <button
            onClick={() => {
              if (key === "stop")
                runAction(key, stopContainer, "Container stopped");
              else if (key === "remove")
                runAction(key, removeContainer, "Container removed");
              else if (key === "update")
                runAction(key, updateContainer, "Container updated");
            }}
            className="rounded bg-red-600 px-2 py-1 text-xs text-white hover:bg-red-500"
          >
            Confirm
          </button>
          <button
            onClick={() => setConfirmAction(null)}
            className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
          >
            Cancel
          </button>
        </div>
      );
    }

    return (
      <button
        onClick={() => {
          if (needsConfirm) {
            setConfirmAction(key);
          } else if (key === "start") {
            runAction(key, startContainer, "Container started");
          }
        }}
        disabled={isLoading || actionLoading !== null}
        className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${color}`}
      >
        {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : icon}
        {label}
      </button>
    );
  };

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-slate-700/50 px-4 py-3">
        <Terminal className="h-4 w-4 text-sky-400" />
        <h3 className="text-sm font-medium text-slate-300">
          Container Management
        </h3>
      </div>

      <div className="space-y-4 p-4">
        {/* Action buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Deploy */}
          <button
            onClick={() => setShowDeployForm(!showDeployForm)}
            disabled={actionLoading !== null}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Rocket className="h-4 w-4" />
            Deploy
          </button>

          {actionBtn(
            "start",
            "Start",
            <Play className="h-4 w-4" />,
            "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30",
            false
          )}

          {actionBtn(
            "stop",
            "Stop",
            <Square className="h-4 w-4" />,
            "bg-amber-500/20 text-amber-400 hover:bg-amber-500/30",
            true
          )}

          {actionBtn(
            "remove",
            "Remove",
            <Trash2 className="h-4 w-4" />,
            "bg-red-500/20 text-red-400 hover:bg-red-500/30",
            true
          )}

          {actionBtn(
            "update",
            "Update",
            <Download className="h-4 w-4" />,
            "bg-violet-500/20 text-violet-400 hover:bg-violet-500/30",
            true
          )}

          <div className="flex-1" />

          {/* Logs toggle */}
          <button
            onClick={handleFetchLogs}
            disabled={logsLoading}
            className="flex items-center gap-1.5 rounded-lg bg-slate-700/50 px-3 py-2 text-sm text-slate-400 hover:bg-slate-700 hover:text-slate-200 disabled:opacity-50"
          >
            {logsLoading ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <Terminal className="h-4 w-4" />
            )}
            Logs
          </button>
        </div>

        {/* Deploy form */}
        {showDeployForm && (
          <form
            onSubmit={handleDeploy}
            className="rounded-lg border border-slate-700/50 bg-slate-900/60 p-4"
          >
            <h4 className="mb-3 text-sm font-medium text-slate-300">
              Deploy Configuration
            </h4>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-xs text-slate-500">
                  Image Tag
                </label>
                <input
                  type="text"
                  value={deployImageTag}
                  onChange={(e) => setDeployImageTag(e.target.value)}
                  placeholder="latest"
                  className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">
                  Web Port
                </label>
                <input
                  type="number"
                  value={deployPort}
                  onChange={(e) => setDeployPort(e.target.value)}
                  min={1}
                  max={65535}
                  className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">
                  Upstream DNS
                </label>
                <input
                  type="text"
                  value={deployUpstreamDns}
                  onChange={(e) => setDeployUpstreamDns(e.target.value)}
                  placeholder="1.1.1.1"
                  className="w-full rounded-lg border border-slate-700/50 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30"
                />
              </div>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowDeployForm(false)}
                className="rounded-lg bg-slate-700/50 px-3 py-1.5 text-sm text-slate-400 hover:bg-slate-700 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={actionLoading === "deploy"}
                className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {actionLoading === "deploy" ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Rocket className="h-4 w-4" />
                )}
                Deploy Container
              </button>
            </div>
          </form>
        )}

        {/* One-time password reveal */}
        {deployedPassword && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
            <div className="mb-3 flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
              <div>
                <h4 className="text-sm font-semibold text-amber-300">
                  {t("pihole.passwordRevealTitle")}
                </h4>
                <p className="mt-1 text-xs text-amber-400/80">
                  {t("pihole.passwordRevealWarning")}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-md border border-slate-700/50 bg-slate-900/80 px-3 py-2 font-mono text-sm text-slate-200">
                {deployedPassword}
              </code>
              <button
                onClick={handleCopyPassword}
                className="flex items-center gap-1.5 rounded-lg bg-slate-700/50 px-3 py-2 text-sm text-slate-300 hover:bg-slate-700 hover:text-white"
              >
                {passwordCopied ? (
                  <Check className="h-4 w-4 text-emerald-400" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
                {t("pihole.copyPassword")}
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              {t("pihole.passwordRevealInfo")}
            </p>
            <div className="mt-3 flex justify-end">
              <button
                onClick={() => setDeployedPassword(null)}
                className="rounded-lg bg-slate-700/50 px-3 py-1.5 text-sm text-slate-400 hover:bg-slate-700 hover:text-slate-200"
              >
                {t("pihole.done")}
              </button>
            </div>
          </div>
        )}

        {/* Container logs */}
        {logsVisible && (
          <div className="rounded-lg border border-slate-700/50 bg-slate-950">
            <div className="flex items-center justify-between border-b border-slate-700/50 px-3 py-2">
              <span className="text-xs font-medium text-slate-400">
                Container Logs
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleFetchLogs}
                  disabled={logsLoading}
                  className="rounded p-1 text-slate-500 hover:text-slate-300 disabled:opacity-50"
                >
                  <RefreshCw
                    className={`h-3.5 w-3.5 ${logsLoading ? "animate-spin" : ""}`}
                  />
                </button>
                <button
                  onClick={() => setLogsVisible(false)}
                  className="rounded p-1 text-slate-500 hover:text-slate-300"
                >
                  <Square className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <pre
              ref={logsRef}
              className="max-h-64 overflow-auto p-3 font-mono text-xs leading-relaxed text-slate-400"
            >
              {logsLoading ? (
                <span className="animate-pulse text-slate-600">
                  Loading logs...
                </span>
              ) : logs ? (
                logs
              ) : (
                <span className="text-slate-600">No logs available</span>
              )}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
