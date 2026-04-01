import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Cloud, KeyRound, Loader2, Trash2, ExternalLink, CheckCircle2,
  XCircle, Info, Users,
} from 'lucide-react';
import {
  getProviders, setOAuthConfig, deleteOAuthConfig, getAllOAuthConfigs,
  type CloudProvider, type ProvidersStatus, type OAuthConfigAdmin,
  PROVIDER_LABELS,
} from '../../api/cloud-import';
import { toast } from 'react-hot-toast';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';

interface IntegrationsTabProps {
  isAdmin: boolean;
}

const PROVIDERS: { id: CloudProvider; gradient: string; icon: string; capabilities: ('import' | 'export')[] }[] = [
  { id: 'google_drive', gradient: 'from-blue-500 to-green-500', icon: 'GD', capabilities: ['import', 'export'] },
  { id: 'onedrive', gradient: 'from-blue-600 to-sky-400', icon: 'OD', capabilities: ['import', 'export'] },
  { id: 'icloud', gradient: 'from-slate-400 to-slate-200', icon: 'iC', capabilities: ['import'] },
];

const PROVIDER_HELP_KEYS: Record<string, string> = {
  google_drive: 'helpGoogle',
  onedrive: 'helpOneDrive',
};

export default function IntegrationsTab({ isAdmin }: IntegrationsTabProps) {
  const { t } = useTranslation('settings');
  const { confirm, dialog } = useConfirmDialog();

  const [providerStatus, setProviderStatus] = useState<ProvidersStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [adminConfigs, setAdminConfigs] = useState<OAuthConfigAdmin[]>([]);

  // Inline config form
  const [configuring, setConfiguring] = useState<CloudProvider | null>(null);
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [status, configs] = await Promise.all([
        getProviders(),
        isAdmin ? getAllOAuthConfigs().catch(() => []) : Promise.resolve([]),
      ]);
      setProviderStatus(status);
      setAdminConfigs(configs);
    } catch {
      // handled by empty state
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSave = async () => {
    if (!configuring || !clientId || !clientSecret) return;
    setSaving(true);
    try {
      await setOAuthConfig(configuring, clientId, clientSecret);
      toast.success(t('integrations.saveSuccess'));
      setConfiguring(null);
      setClientId('');
      setClientSecret('');
      loadData();
    } catch {
      toast.error(t('integrations.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (provider: CloudProvider) => {
    const confirmed = await confirm(
      t('integrations.deleteConfirm', { provider: PROVIDER_LABELS[provider] }),
      { title: t('integrations.delete'), confirmLabel: t('integrations.delete'), variant: 'danger' }
    );
    if (!confirmed) return;

    try {
      await deleteOAuthConfig(provider);
      toast.success(t('integrations.deleteSuccess'));
      loadData();
    } catch {
      toast.error(t('integrations.deleteFailed'));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {dialog}

      {/* Header */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-1 flex items-center">
          <Cloud className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('integrations.title')}
        </h3>
        <p className="text-sm text-slate-400">{t('integrations.description')}</p>
      </div>

      {/* Provider cards */}
      <div className="space-y-4">
        {PROVIDERS.map((p) => {
          const info = providerStatus?.providers[p.id];
          const isConfigured = info?.configured ?? false;
          const isOAuth = info?.auth_type === 'oauth';
          const isExpanded = configuring === p.id;

          return (
            <div
              key={p.id}
              className="rounded-2xl border border-slate-800/60 bg-slate-900/55 backdrop-blur-xl shadow-[0_20px_60px_rgba(2,6,23,0.55)] p-5"
            >
              <div className="flex items-center gap-4">
                {/* Provider icon */}
                <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${p.gradient} text-sm font-bold text-white`}>
                  {p.icon}
                </div>

                {/* Provider info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-200">{PROVIDER_LABELS[p.id]}</span>
                    {/* Status badge */}
                    {isOAuth && (
                      isConfigured ? (
                        <span className="flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">
                          <CheckCircle2 className="h-3 w-3" />
                          {t('integrations.configured')}
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 rounded-full border border-slate-600/30 bg-slate-600/10 px-2 py-0.5 text-xs font-medium text-slate-500">
                          <XCircle className="h-3 w-3" />
                          {t('integrations.notConfigured')}
                        </span>
                      )
                    )}
                  </div>

                  {/* Capability badges */}
                  <div className="mt-1 flex items-center gap-2">
                    {p.capabilities.includes('import') && (
                      <span className="rounded-md bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 text-xs text-sky-400">
                        {t('integrations.cloudImport')}
                      </span>
                    )}
                    {p.capabilities.includes('export') && (
                      <span className="rounded-md bg-violet-500/10 border border-violet-500/20 px-2 py-0.5 text-xs text-violet-400">
                        {t('integrations.cloudExport')}
                      </span>
                    )}
                    {p.id === 'icloud' && (
                      <span className="flex items-center gap-1 text-xs text-slate-500">
                        <Info className="h-3 w-3" />
                        {t('integrations.importOnly')}
                      </span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                {isOAuth && (
                  <div className="flex items-center gap-2">
                    {isConfigured ? (
                      <button
                        onClick={() => handleDelete(p.id)}
                        className="flex items-center gap-1.5 rounded-lg border border-slate-700/50 px-3 py-1.5 text-xs text-slate-400 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-400"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        {t('integrations.delete')}
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setConfiguring(isExpanded ? null : p.id);
                          setClientId('');
                          setClientSecret('');
                        }}
                        className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
                      >
                        <KeyRound className="h-3.5 w-3.5" />
                        {t('integrations.configure')}
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Inline config form */}
              {isExpanded && isOAuth && (
                <div className="mt-4 space-y-3 border-t border-slate-700/40 pt-4">
                  {PROVIDER_HELP_KEYS[p.id] && (
                    <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 px-3 py-2">
                      <p className="text-xs text-sky-400">
                        <ExternalLink className="mr-1 inline h-3 w-3" />
                        {t(`integrations.${PROVIDER_HELP_KEYS[p.id]}`)}
                      </p>
                    </div>
                  )}
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-400">
                      {t('integrations.clientId')}
                    </label>
                    <input
                      type="text"
                      value={clientId}
                      onChange={(e) => setClientId(e.target.value)}
                      placeholder={t('integrations.clientIdPlaceholder')}
                      className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-sky-500/50"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-400">
                      {t('integrations.clientSecret')}
                    </label>
                    <input
                      type="password"
                      value={clientSecret}
                      onChange={(e) => setClientSecret(e.target.value)}
                      placeholder={t('integrations.clientSecretPlaceholder')}
                      className="w-full rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-sky-500/50"
                    />
                  </div>
                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => setConfiguring(null)}
                      className="rounded-lg border border-slate-700/50 px-4 py-2 text-sm text-slate-400 hover:bg-slate-800"
                    >
                      {t('integrations.cancel')}
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={saving || !clientId || !clientSecret}
                      className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                    >
                      {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                      {t('integrations.save')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Admin overview */}
      {isAdmin && (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <h3 className="text-base sm:text-lg font-semibold mb-1 flex items-center">
            <Users className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
            {t('integrations.adminOverview')}
          </h3>
          <p className="text-sm text-slate-400 mb-4">{t('integrations.adminOverviewDescription')}</p>

          {adminConfigs.length === 0 ? (
            <p className="text-sm text-slate-500 py-4 text-center">{t('integrations.noConfigs')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/40 text-left text-xs font-medium uppercase tracking-wider text-slate-500">
                    <th className="pb-2 pr-4">{t('integrations.user')}</th>
                    <th className="pb-2 pr-4">{t('integrations.provider')}</th>
                    <th className="pb-2 pr-4">{t('integrations.clientId')}</th>
                    <th className="pb-2">{t('integrations.lastUpdated')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/30">
                  {adminConfigs.map((c, i) => (
                    <tr key={`${c.user_id}-${c.provider}-${i}`} className="text-slate-300">
                      <td className="py-2.5 pr-4 font-medium">{c.username}</td>
                      <td className="py-2.5 pr-4">{PROVIDER_LABELS[c.provider] ?? c.provider}</td>
                      <td className="py-2.5 pr-4 font-mono text-xs text-slate-500">{c.client_id_hint ?? '—'}</td>
                      <td className="py-2.5 text-slate-500">
                        {c.updated_at ? new Date(c.updated_at).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
