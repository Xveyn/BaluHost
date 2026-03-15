import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Cpu,
  Wifi,
  RefreshCw,
  Copy,
  Check,
  Key,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Power,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getBaluPiConfig,
  updateBaluPiConfig,
  testBaluPiConnection,
  generateBaluPiSecret,
  type BaluPiConfig,
  type BaluPiTestResult,
} from '../../api/balupi';

export default function BaluPiSetup() {
  const { t } = useTranslation('common');

  const [config, setConfig] = useState<BaluPiConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<BaluPiTestResult | null>(null);
  const [generating, setGenerating] = useState(false);

  // Form state
  const [enabled, setEnabled] = useState(false);
  const [url, setUrl] = useState('');
  const [secret, setSecret] = useState('');
  const [secretDirty, setSecretDirty] = useState(false);
  const [copied, setCopied] = useState(false);

  const fetchConfig = async () => {
    try {
      const data = await getBaluPiConfig();
      setConfig(data);
      setEnabled(data.enabled);
      setUrl(data.url);
      setSecret('');
      setSecretDirty(false);
    } catch {
      toast.error(t('toast.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const update: Record<string, unknown> = {};
      if (enabled !== config?.enabled) update.enabled = enabled;
      if (url !== config?.url) update.url = url;
      if (secretDirty && secret) update.secret = secret;

      if (Object.keys(update).length === 0) {
        toast.error('No changes to save');
        return;
      }

      await updateBaluPiConfig(update);
      toast.success(t('toast.saved'));
      await fetchConfig();
      setTestResult(null);
    } catch {
      toast.error(t('toast.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testBaluPiConnection();
      setTestResult(result);
    } catch {
      setTestResult({ reachable: false, error: 'Request failed' });
    } finally {
      setTesting(false);
    }
  };

  const handleGenerateSecret = async () => {
    setGenerating(true);
    try {
      const { secret: newSecret } = await generateBaluPiSecret();
      setSecret(newSecret);
      setSecretDirty(true);
    } catch {
      toast.error('Failed to generate secret');
    } finally {
      setGenerating(false);
    }
  };

  const handleCopySecret = async () => {
    if (!secret) return;
    await navigator.clipboard.writeText(secret);
    setCopied(true);
    toast.success('Secret copied');
    setTimeout(() => setCopied(false), 2000);
  };

  const hasChanges =
    enabled !== config?.enabled ||
    url !== config?.url ||
    (secretDirty && secret.length > 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 text-sm font-bold text-white">
            BP
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">BaluPi Companion</h2>
            <p className="text-xs text-slate-400">
              Raspberry Pi companion device for WoL, energy monitoring & DNS failover
            </p>
          </div>
        </div>
        <button
          onClick={fetchConfig}
          className="flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-400 transition hover:border-slate-600 hover:text-slate-300"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          {t('refresh')}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Connection Settings */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <Wifi className="h-4 w-4 text-sky-400" />
            Connection Settings
          </h3>

          <div className="space-y-4">
            {/* Enable Toggle */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-200">Enable BaluPi</p>
                <p className="text-xs text-slate-500">
                  Send shutdown/startup notifications to Pi
                </p>
              </div>
              <button
                onClick={() => setEnabled(!enabled)}
                className={`relative h-6 w-11 rounded-full transition-colors ${
                  enabled ? 'bg-sky-500' : 'bg-slate-700'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                    enabled ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </div>

            {/* Pi URL */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">
                BaluPi URL
              </label>
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="http://192.168.178.20:8000"
                className="w-full rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
              <p className="mt-1 text-xs text-slate-500">
                The BaluPi backend API address on your local network
              </p>
            </div>

            {/* Shared Secret */}
            <div>
              <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-400">
                <Key className="h-3 w-3" />
                HMAC Shared Secret
              </label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={secret}
                    onChange={(e) => {
                      setSecret(e.target.value);
                      setSecretDirty(true);
                    }}
                    placeholder={
                      config?.has_secret
                        ? `${config.secret_preview} (configured)`
                        : 'Not configured'
                    }
                    className="w-full rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-2 pr-9 font-mono text-xs text-slate-200 placeholder-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                  {secret && (
                    <button
                      onClick={handleCopySecret}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                      title="Copy"
                    >
                      {copied ? (
                        <Check className="h-3.5 w-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </button>
                  )}
                </div>
                <button
                  onClick={handleGenerateSecret}
                  disabled={generating}
                  className="flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-300 transition hover:border-slate-600 hover:text-white disabled:opacity-50"
                >
                  {generating ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Key className="h-3.5 w-3.5" />
                  )}
                  Generate
                </button>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Must match BALUPI_HANDSHAKE_SECRET on the Pi (min. 32 chars)
              </p>
            </div>

            {/* Save Button */}
            <button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Save Configuration
            </button>
          </div>
        </div>

        {/* Connection Test & Status */}
        <div className="space-y-4">
          {/* Test Connection */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
              <Power className="h-4 w-4 text-emerald-400" />
              Connection Test
            </h3>

            <button
              onClick={handleTest}
              disabled={testing || !config?.url}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:border-sky-500/50 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {testing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Testing...
                </>
              ) : (
                <>
                  <Wifi className="h-4 w-4" />
                  Test Connection
                </>
              )}
            </button>

            {testResult && (
              <div
                className={`mt-3 rounded-lg border p-3 ${
                  testResult.reachable
                    ? 'border-emerald-500/30 bg-emerald-500/10'
                    : 'border-rose-500/30 bg-rose-500/10'
                }`}
              >
                <div className="flex items-center gap-2">
                  {testResult.reachable ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-rose-400" />
                  )}
                  <span
                    className={`text-sm font-medium ${
                      testResult.reachable ? 'text-emerald-300' : 'text-rose-300'
                    }`}
                  >
                    {testResult.reachable ? 'Connected' : 'Unreachable'}
                  </span>
                </div>
                {testResult.reachable && (
                  <div className="mt-2 space-y-1 text-xs text-emerald-200/70">
                    {testResult.version && (
                      <p>
                        Version: <span className="font-mono text-emerald-300">{testResult.version}</span>
                      </p>
                    )}
                    {testResult.hostname && (
                      <p>
                        Hostname: <span className="font-mono text-emerald-300">{testResult.hostname}</span>
                      </p>
                    )}
                  </div>
                )}
                {testResult.error && (
                  <p className="mt-1.5 text-xs text-rose-300/80">{testResult.error}</p>
                )}
              </div>
            )}

            {!config?.url && (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-amber-400/80">
                <AlertCircle className="h-3 w-3" />
                Configure the BaluPi URL first
              </p>
            )}
          </div>

          {/* How it works */}
          <div className="rounded-xl border border-slate-800/60 bg-slate-900/40 p-5">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
              <Cpu className="h-4 w-4 text-slate-500" />
              How it works
            </h3>
            <ul className="space-y-2.5 text-xs text-slate-400">
              <li className="flex gap-2">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-500/20 text-[10px] font-bold text-sky-400">
                  1
                </span>
                <span>
                  NAS sends shutdown snapshot to Pi via HMAC-signed request
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-500/20 text-[10px] font-bold text-sky-400">
                  2
                </span>
                <span>
                  Pi switches <span className="font-mono text-slate-300">baluhost.local</span> DNS to itself via Pi-hole
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-500/20 text-[10px] font-bold text-sky-400">
                  3
                </span>
                <span>
                  Pi serves status page, accepts SMB uploads to inbox, monitors energy via Tapo
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-500/20 text-[10px] font-bold text-sky-400">
                  4
                </span>
                <span>
                  User can Wake-on-LAN the NAS from Pi dashboard
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-500/20 text-[10px] font-bold text-sky-400">
                  5
                </span>
                <span>
                  On boot, NAS notifies Pi — inbox is flushed via rsync, DNS switches back
                </span>
              </li>
            </ul>
          </div>

          {/* Current Status */}
          <div className="rounded-xl border border-slate-800/60 bg-slate-900/40 p-5">
            <h3 className="mb-3 text-sm font-semibold text-slate-300">Current Status</h3>
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Integration</span>
                <span className={`flex items-center gap-1.5 font-medium ${config?.enabled ? 'text-emerald-400' : 'text-slate-500'}`}>
                  <div className={`h-1.5 w-1.5 rounded-full ${config?.enabled ? 'bg-emerald-500' : 'bg-slate-600'}`} />
                  {config?.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">URL</span>
                <span className="font-mono text-slate-300">
                  {config?.url || '—'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Secret</span>
                <span className={config?.has_secret ? 'text-emerald-400' : 'text-amber-400'}>
                  {config?.has_secret ? 'Configured' : 'Not set'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
