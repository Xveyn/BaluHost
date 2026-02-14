import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { FolderOpen, Copy, Check, Monitor, Apple, Terminal, Loader2, AlertCircle, Lock, Unlock } from 'lucide-react';
import toast from 'react-hot-toast';
import { getWebdavConnectionInfo, type WebdavConnectionInfo } from '../../api/webdav';

const OS_ICONS: Record<string, React.ReactNode> = {
  windows: <Monitor className="h-5 w-5" />,
  macos: <Apple className="h-5 w-5" />,
  linux: <Terminal className="h-5 w-5" />,
};

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation('system');
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Failed to copy');
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 rounded-md bg-slate-700/50 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
      title={t('webdav.copyPath')}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? t('webdav.copied') : t('webdav.copyPath')}
    </button>
  );
}

export default function WebdavConnectionCard() {
  const { t } = useTranslation('system');
  const [info, setInfo] = useState<WebdavConnectionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getWebdavConnectionInfo()
      .then((data) => {
        if (!cancelled) {
          setInfo(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Failed to load');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        {t('webdav.loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-red-400">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }

  if (!info) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <FolderOpen className="h-6 w-6 text-blue-400" />
          {t('webdav.title')}
        </h2>
        <p className="mt-1 text-sm text-slate-400">{t('webdav.subtitle')}</p>
      </div>

      {/* Status Card */}
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
        <div className="flex flex-wrap items-center gap-4">
          {/* Running Status */}
          <div className="flex items-center gap-2">
            <div className={`h-2.5 w-2.5 rounded-full ${info.is_running ? 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.4)]' : 'bg-red-400'}`} />
            <span className={`text-sm font-medium ${info.is_running ? 'text-green-400' : 'text-red-400'}`}>
              {info.is_running ? t('webdav.running') : t('webdav.notRunning')}
            </span>
          </div>

          {/* Port */}
          <div className="flex items-center gap-1.5 text-sm text-slate-400">
            <span className="text-slate-500">{t('webdav.port')}:</span>
            <span className="font-mono text-slate-300">{info.port}</span>
          </div>

          {/* SSL */}
          <div className="flex items-center gap-1.5 text-sm text-slate-400">
            {info.ssl_enabled
              ? <Lock className="h-3.5 w-3.5 text-green-400" />
              : <Unlock className="h-3.5 w-3.5 text-amber-400" />
            }
            <span>{t('webdav.ssl')}: {info.ssl_enabled ? 'HTTPS' : 'HTTP'}</span>
          </div>

          {/* Connection URL */}
          {info.is_running && (
            <div className="flex items-center gap-2 ml-auto">
              <code className="rounded bg-slate-900/50 px-2.5 py-1 text-xs font-mono text-blue-300 border border-slate-700/50">
                {info.connection_url}
              </code>
              <CopyButton text={info.connection_url} />
            </div>
          )}
        </div>
      </div>

      {/* Not running message */}
      {!info.is_running && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 text-amber-300 text-sm">
          <AlertCircle className="h-4 w-4 inline mr-2" />
          {t('webdav.notRunningHint')}
        </div>
      )}

      {/* Mount Instructions */}
      <div>
        <h3 className="text-base font-medium text-white mb-3">
          {t('webdav.mountInstructions')}
        </h3>
        <p className="text-sm text-slate-400 mb-4">
          {t('webdav.authenticateAs', { username: info.username })}
        </p>

        <div className="space-y-3">
          {info.instructions.map((instr) => (
            <div
              key={instr.os}
              className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-slate-400">
                    {OS_ICONS[instr.os] || <Monitor className="h-5 w-5" />}
                  </span>
                  <span className="font-medium text-white">{instr.label}</span>
                </div>
                <CopyButton text={instr.command} />
              </div>

              <code className="block rounded-lg bg-slate-900/70 px-3 py-2.5 text-sm font-mono text-slate-300 border border-slate-700/30 break-all">
                {instr.command}
              </code>

              {instr.notes && (
                <p className="mt-2 text-xs text-slate-500">{instr.notes}</p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
