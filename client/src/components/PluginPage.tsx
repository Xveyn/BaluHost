/**
 * Dynamic Plugin Page Component
 *
 * Renders plugin UI by dynamically loading the plugin's JavaScript bundle.
 */
import { useEffect, useState, Suspense, type ComponentType } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { usePlugins } from '../contexts/PluginContext';
import { loadPluginComponent, loadPluginStyles } from '../lib/pluginLoader';
import { AlertTriangle, Plug } from 'lucide-react';

interface PluginUser {
  id: number;
  username: string;
  role: string;
}

interface PluginComponentProps {
  user: PluginUser;
}

export default function PluginPage() {
  const { user } = useAuth();

  const { t } = useTranslation('plugins');
  const { pluginName } = useParams<{ pluginName: string }>();
  const navigate = useNavigate();
  const { enabledPlugins } = usePlugins();

  const [PluginComponent, setPluginComponent] = useState<ComponentType<PluginComponentProps> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Find the plugin info
  const pluginInfo = enabledPlugins.find((p) => p.name === pluginName);

  useEffect(() => {
    if (!pluginName) return;

    // Check if plugin is enabled
    if (!pluginInfo) {
      setError(`Plugin "${pluginName}" is not enabled or does not exist.`);
      setLoading(false);
      return;
    }

    // Load the plugin bundle
    let mounted = true;

    const loadPlugin = async () => {
      try {
        setLoading(true);
        setError(null);

        // Load styles if available
        if (pluginInfo.styles_path) {
          loadPluginStyles(pluginName, pluginInfo.styles_path);
        }

        // Load the main component
        const Component = await loadPluginComponent<ComponentType<PluginComponentProps>>(
          pluginName,
          'default',
          pluginInfo.bundle_path
        );

        if (mounted) {
          setPluginComponent(() => Component);
          setLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load plugin');
          setLoading(false);
        }
      }
    };

    loadPlugin();

    return () => {
      mounted = false;
      // Optionally unload styles when leaving
      // unloadPluginStyles(pluginName);
    };
  }, [pluginName, pluginInfo]);

  if (!user) return null;

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
        <p className="text-sm text-slate-400">{t('loading')}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <div className="p-4 rounded-full bg-red-500/10">
          <AlertTriangle className="h-8 w-8 text-red-400" />
        </div>
        <div className="text-center">
          <h3 className="text-lg font-medium text-white mb-1">{t('error')}</h3>
          <p className="text-sm text-slate-400 max-w-md">{error}</p>
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

  if (!PluginComponent) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <div className="p-4 rounded-full bg-slate-800">
          <Plug className="h-8 w-8 text-slate-500" />
        </div>
        <div className="text-center">
          <h3 className="text-lg font-medium text-white mb-1">{t('noContent')}</h3>
          <p className="text-sm text-slate-400">{t('noUIComponent')}</p>
        </div>
      </div>
    );
  }

  // Render the plugin component with user context
  return (
    <div className="plugin-container">
      <Suspense
        fallback={
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
          </div>
        }
      >
        <PluginComponent user={user} />
      </Suspense>
    </div>
  );
}
