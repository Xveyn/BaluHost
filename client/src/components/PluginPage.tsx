/**
 * Dynamic Plugin Page Component
 *
 * Renders plugin UI inside a sandboxed iframe via PluginSandboxHost.
 */
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { usePlugins } from '../contexts/PluginContext';
import { AlertTriangle } from 'lucide-react';
import { PluginBadge } from './ui/PluginBadge';
import PluginSandboxHost from './plugins/PluginSandboxHost';

export default function PluginPage() {
  const { user } = useAuth();

  const { t } = useTranslation('plugins');
  const { pluginName } = useParams<{ pluginName: string }>();
  const navigate = useNavigate();
  const { enabledPlugins } = usePlugins();

  // Find the plugin info
  const pluginInfo = enabledPlugins.find((p) => p.name === pluginName);

  if (!user) return null;

  // Derive "not found" error — no effect needed
  if (pluginName && !pluginInfo) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <div className="p-4 rounded-full bg-red-500/10">
          <AlertTriangle className="h-8 w-8 text-red-400" />
        </div>
        <div className="text-center">
          <h3 className="text-lg font-medium text-white mb-1">{t('error')}</h3>
          <p className="text-sm text-slate-400 max-w-md">
            {`Plugin "${pluginName}" is not enabled or does not exist.`}
          </p>
        </div>
        <button
          onClick={() => navigate('/')}
          className="px-4 py-2 text-sm font-medium rounded-lg border border-slate-700 text-slate-300 hover:border-sky-500/50"
        >
          {t('goToDashboard')}
        </button>
      </div>
    );
  }

  const displayName = pluginInfo?.display_name ?? pluginName ?? '';

  // Render the plugin in a sandboxed iframe via PluginSandboxHost
  return (
    <div className="plugin-container">
      <div className="mb-6 flex items-center gap-3">
        <h1 className="text-2xl font-semibold text-white">{displayName}</h1>
        <PluginBadge pluginName={displayName} size="md" className="ml-2" />
      </div>
      <PluginSandboxHost
        pluginName={pluginName!}
        user={user}
        grantedScopes={pluginInfo?.granted_api_scopes ?? []}
      />
    </div>
  );
}
