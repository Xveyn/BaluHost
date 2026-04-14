/**
 * Marketplace tab for the plugins page.
 *
 * Fetches the upstream plugin index, lets admins search through it, and
 * install/uninstall plugins. Resolver conflicts are surfaced inline with a
 * "force install" escape hatch.
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  AlertTriangle,
  Download,
  ExternalLink,
  Package,
  RefreshCw,
  Search,
  Shield,
  Trash2,
} from 'lucide-react';

import {
  listMarketplace,
  installMarketplacePlugin,
  uninstallMarketplacePlugin,
  type MarketplaceConflict,
  type MarketplaceIndex,
  type MarketplacePlugin,
} from '../../api/plugins-marketplace';
import { usePlugins } from '../../contexts/PluginContext';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import { getApiErrorMessage } from '../../lib/errorHandling';

interface ConflictState {
  plugin: MarketplacePlugin;
  conflicts: MarketplaceConflict[];
}

function extractConflicts(err: unknown): MarketplaceConflict[] | null {
  const detail = (err as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  if (
    detail &&
    typeof detail === 'object' &&
    (detail as { error?: string }).error === 'resolver_conflict' &&
    Array.isArray((detail as { conflicts?: unknown }).conflicts)
  ) {
    return (detail as { conflicts: MarketplaceConflict[] }).conflicts;
  }
  return null;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function MarketplaceTab() {
  const { t } = useTranslation('plugins');
  const { plugins, refreshPlugins } = usePlugins();
  const { confirm, dialog } = useConfirmDialog();

  const [index, setIndex] = useState<MarketplaceIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [installingName, setInstallingName] = useState<string | null>(null);
  const [conflictState, setConflictState] = useState<ConflictState | null>(null);

  const installedNames = useMemo(
    () => new Set(plugins.map((p) => p.name)),
    [plugins],
  );

  const load = async (forceRefresh = false) => {
    if (forceRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await listMarketplace(forceRefresh);
      setIndex(data);
    } catch (err) {
      setError(getApiErrorMessage(err, t('marketplace.loadError')));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleInstall = async (
    plugin: MarketplacePlugin,
    force: boolean = false,
  ) => {
    setInstallingName(plugin.name);
    try {
      const result = await installMarketplacePlugin(plugin.name, { force });
      toast.success(
        t('marketplace.installSuccess', {
          name: plugin.display_name,
          version: result.version,
        }),
      );
      setConflictState(null);
      await refreshPlugins();
    } catch (err) {
      const conflicts = extractConflicts(err);
      if (conflicts) {
        setConflictState({ plugin, conflicts });
      } else {
        toast.error(getApiErrorMessage(err, t('marketplace.installFailed')));
      }
    } finally {
      setInstallingName(null);
    }
  };

  const handleUninstall = async (plugin: MarketplacePlugin) => {
    const ok = await confirm(
      t('marketplace.confirmUninstall', { name: plugin.display_name }),
      {
        title: t('buttons.uninstall'),
        variant: 'danger',
        confirmLabel: t('buttons.uninstall'),
      },
    );
    if (!ok) return;

    try {
      await uninstallMarketplacePlugin(plugin.name);
      toast.success(
        t('marketplace.uninstallSuccess', { name: plugin.display_name }),
      );
      await refreshPlugins();
    } catch (err) {
      toast.error(getApiErrorMessage(err, t('marketplace.uninstallFailed')));
    }
  };

  const filtered = useMemo(() => {
    if (!index) return [] as MarketplacePlugin[];
    const q = search.trim().toLowerCase();
    if (!q) return index.plugins;
    return index.plugins.filter((p) => {
      return (
        p.name.toLowerCase().includes(q) ||
        p.display_name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q) ||
        p.author.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q)
      );
    });
  }, [index, search]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Toolbar: search + refresh */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('marketplace.searchPlaceholder')}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg bg-slate-900/50 border border-slate-700 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500/50"
          />
        </div>
        <button
          onClick={() => void load(true)}
          disabled={refreshing}
          className="flex items-center gap-2 rounded-lg px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40 disabled:opacity-50"
        >
          <RefreshCw
            className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`}
          />
          {t('marketplace.refresh')}
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          {error}
        </div>
      )}

      {/* Plugin list */}
      {!error && filtered.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center">
          <Package className="h-12 w-12 mx-auto text-slate-600 mb-4" />
          <p className="text-sm text-slate-500">
            {search ? t('marketplace.emptySearch') : t('marketplace.empty')}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filtered.map((plugin) => {
            const latest = plugin.versions.find(
              (v) => v.version === plugin.latest_version,
            );
            const isInstalled = installedNames.has(plugin.name);
            const isBusy = installingName === plugin.name;

            return (
              <div
                key={plugin.name}
                className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 flex flex-col"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-medium text-white truncate">
                        {plugin.display_name}
                      </h3>
                      <span className="text-xs text-slate-500">
                        v{plugin.latest_version}
                      </span>
                      {isInstalled && (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-green-500/20 text-green-400 border border-green-500/30">
                          {t('marketplace.installed')}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-400 mt-1 line-clamp-2">
                      {plugin.description}
                    </p>
                    <div className="flex items-center gap-2 mt-2 text-xs text-slate-500 flex-wrap">
                      <span>{plugin.author}</span>
                      <span>•</span>
                      <span className="capitalize">{plugin.category}</span>
                      {latest && (
                        <>
                          <span>•</span>
                          <span>{formatBytes(latest.size_bytes)}</span>
                        </>
                      )}
                      {plugin.homepage && (
                        <>
                          <span>•</span>
                          <a
                            href={plugin.homepage}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-400 hover:underline inline-flex items-center gap-1"
                          >
                            {t('details.link')}
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {latest && latest.required_permissions.length > 0 && (
                  <div className="mt-3 flex items-start gap-2 text-xs text-slate-500">
                    <Shield className="h-3.5 w-3.5 mt-0.5 text-amber-400 flex-shrink-0" />
                    <div>
                      <span className="text-slate-400">
                        {t('marketplace.requiresPermissions')}:
                      </span>{' '}
                      <span className="text-slate-500">
                        {latest.required_permissions.join(', ')}
                      </span>
                    </div>
                  </div>
                )}

                {latest && latest.python_requirements.length > 0 && (
                  <div className="mt-2 text-xs text-slate-500">
                    <span className="text-slate-400">
                      {t('marketplace.requirements')}:
                    </span>{' '}
                    <span className="font-mono">
                      {latest.python_requirements.join(', ')}
                    </span>
                  </div>
                )}

                <div className="mt-4 flex justify-end gap-2">
                  {isInstalled ? (
                    <button
                      onClick={() => void handleUninstall(plugin)}
                      disabled={isBusy}
                      className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium border border-red-500/30 text-red-400 hover:bg-red-500/10 disabled:opacity-50 transition-all touch-manipulation active:scale-95"
                    >
                      <Trash2 className="h-4 w-4" />
                      {t('buttons.uninstall')}
                    </button>
                  ) : (
                    <button
                      onClick={() => void handleInstall(plugin)}
                      disabled={isBusy}
                      className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 border border-blue-500/30 disabled:opacity-50 transition-all touch-manipulation active:scale-95"
                    >
                      <Download className="h-4 w-4" />
                      {isBusy
                        ? t('marketplace.installing')
                        : t('marketplace.install')}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Conflict modal */}
      {conflictState && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-2xl mx-4 shadow-2xl">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 rounded-lg bg-amber-500/20">
                <AlertTriangle className="h-5 w-5 text-amber-400" />
              </div>
              <div>
                <h3 className="text-lg font-medium text-white">
                  {t('marketplace.conflictsTitle')}
                </h3>
                <p className="text-sm text-slate-400 mt-1">
                  {conflictState.plugin.display_name} v
                  {conflictState.plugin.latest_version}
                </p>
              </div>
            </div>
            <div className="space-y-3 max-h-96 overflow-y-auto mb-6">
              {conflictState.conflicts.map((c, idx) => (
                <div
                  key={`${c.package}-${idx}`}
                  className="p-3 rounded-lg bg-slate-800/50 border border-slate-700"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-sm text-white">
                      {c.package}
                    </span>
                    <span className="text-xs text-slate-500">{c.source}</span>
                  </div>
                  <div className="text-xs text-slate-400 space-y-0.5">
                    <div>
                      <span className="text-slate-500">
                        {t('marketplace.conflictRequirement')}:
                      </span>{' '}
                      <span className="font-mono">{c.requirement}</span>
                    </div>
                    {c.found && (
                      <div>
                        <span className="text-slate-500">
                          {t('marketplace.conflictFound')}:
                        </span>{' '}
                        <span className="font-mono">{c.found}</span>
                      </div>
                    )}
                  </div>
                  <p className="text-xs text-amber-400 mt-2">{c.suggestion}</p>
                </div>
              ))}
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => setConflictState(null)}
                className="flex-1 px-4 py-2 text-sm font-medium rounded-lg border border-slate-700 text-slate-300 hover:border-slate-600 transition-all touch-manipulation active:scale-95"
              >
                {t('buttons.cancel')}
              </button>
              <button
                onClick={() => void handleInstall(conflictState.plugin, true)}
                disabled={installingName === conflictState.plugin.name}
                className="flex-1 px-4 py-2 text-sm font-medium rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 disabled:opacity-50 transition-all touch-manipulation active:scale-95"
              >
                {t('marketplace.forceInstall')}
              </button>
            </div>
          </div>
        </div>
      )}

      {dialog}
    </div>
  );
}
