/**
 * Plugin Management Page
 *
 * Admin-only page for managing installed plugins.
 */
import { useState, useEffect } from 'react';
import { usePlugins } from '../contexts/PluginContext';
import type {
  PluginDetail,
  PluginInfo,
  PermissionInfo,
} from '../api/plugins';
import {
  getPluginDetails,
  listPermissions,
  togglePlugin,
  uninstallPlugin,
} from '../api/plugins';
import { AlertTriangle, Check, X, Plug, Shield, Settings, Trash2, ExternalLink } from 'lucide-react';

export default function PluginsPage() {
  const { plugins, isLoading, error, refreshPlugins } = usePlugins();
  const [selectedPlugin, setSelectedPlugin] = useState<PluginDetail | null>(null);
  const [allPermissions, setAllPermissions] = useState<PermissionInfo[]>([]);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showPermissionModal, setShowPermissionModal] = useState(false);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);

  // Load all permissions on mount
  useEffect(() => {
    listPermissions()
      .then((res) => setAllPermissions(res.permissions))
      .catch(console.error);
  }, []);

  const loadPluginDetails = async (name: string) => {
    setDetailsLoading(true);
    setActionError(null);
    try {
      const details = await getPluginDetails(name);
      setSelectedPlugin(details);
    } catch (err) {
      setActionError('Failed to load plugin details');
    } finally {
      setDetailsLoading(false);
    }
  };

  const handleTogglePlugin = async (plugin: PluginInfo) => {
    if (plugin.is_enabled) {
      // Disable plugin
      setActionLoading(true);
      setActionError(null);
      try {
        await togglePlugin(plugin.name, { enabled: false });
        await refreshPlugins();
        if (selectedPlugin?.name === plugin.name) {
          await loadPluginDetails(plugin.name);
        }
      } catch (err) {
        setActionError('Failed to disable plugin');
      } finally {
        setActionLoading(false);
      }
    } else {
      // Show permission modal for enabling
      setSelectedPermissions(plugin.required_permissions);
      setShowPermissionModal(true);
    }
  };

  const handleEnableWithPermissions = async () => {
    if (!selectedPlugin) return;

    setActionLoading(true);
    setActionError(null);
    setShowPermissionModal(false);

    try {
      await togglePlugin(selectedPlugin.name, {
        enabled: true,
        grant_permissions: selectedPermissions,
      });
      await refreshPlugins();
      await loadPluginDetails(selectedPlugin.name);
    } catch (err) {
      setActionError('Failed to enable plugin');
    } finally {
      setActionLoading(false);
    }
  };

  const handleUninstall = async (name: string) => {
    if (!confirm(`Uninstall plugin "${name}"? This will remove its configuration.`)) {
      return;
    }

    setActionLoading(true);
    setActionError(null);
    try {
      await uninstallPlugin(name);
      await refreshPlugins();
      if (selectedPlugin?.name === name) {
        setSelectedPlugin(null);
      }
    } catch (err) {
      setActionError('Failed to uninstall plugin');
    } finally {
      setActionLoading(false);
    }
  };

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      monitoring: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
      storage: 'bg-green-500/20 text-green-400 border-green-500/30',
      network: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
      security: 'bg-red-500/20 text-red-400 border-red-500/30',
      general: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
    };
    return colors[category] || colors.general;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Plugins</h1>
          <p className="text-sm text-slate-400 mt-1">
            Manage installed plugins and extensions
          </p>
        </div>
        <button
          onClick={refreshPlugins}
          className="px-4 py-2 text-sm font-medium rounded-lg border border-slate-700 hover:border-sky-500/50 text-slate-300 hover:text-white transition"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400">
          {error}
        </div>
      )}

      {actionError && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          {actionError}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Plugin List */}
        <div className="lg:col-span-2 space-y-4">
          {plugins.length === 0 ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center">
              <Plug className="h-12 w-12 mx-auto text-slate-600 mb-4" />
              <h3 className="text-lg font-medium text-slate-300 mb-2">No plugins installed</h3>
              <p className="text-sm text-slate-500">
                Place plugin directories in the backend/app/plugins/installed/ folder
              </p>
            </div>
          ) : (
            plugins.map((plugin) => (
              <div
                key={plugin.name}
                onClick={() => loadPluginDetails(plugin.name)}
                className={`rounded-xl border p-4 cursor-pointer transition-all ${
                  selectedPlugin?.name === plugin.name
                    ? 'border-sky-500 bg-slate-900/80'
                    : 'border-slate-800 bg-slate-900/50 hover:border-slate-700'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${plugin.is_enabled ? 'bg-green-500/20' : 'bg-slate-800'}`}>
                      <Plug className={`h-5 w-5 ${plugin.is_enabled ? 'text-green-400' : 'text-slate-500'}`} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-white">{plugin.display_name}</h3>
                        <span className="text-xs text-slate-500">v{plugin.version}</span>
                        {plugin.is_enabled && (
                          <span className="px-2 py-0.5 text-xs rounded-full bg-green-500/20 text-green-400 border border-green-500/30">
                            Active
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-400 mt-0.5">{plugin.description}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <span className={`px-2 py-0.5 text-xs rounded-full border ${getCategoryColor(plugin.category)}`}>
                          {plugin.category}
                        </span>
                        {plugin.has_ui && (
                          <span className="px-2 py-0.5 text-xs rounded-full bg-purple-500/20 text-purple-400 border border-purple-500/30">
                            UI
                          </span>
                        )}
                        {plugin.dangerous_permissions.length > 0 && (
                          <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                            <Shield className="h-3 w-3" />
                            Requires Review
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleTogglePlugin(plugin);
                    }}
                    disabled={actionLoading}
                    className={`px-3 py-1.5 text-sm font-medium rounded-lg transition ${
                      plugin.is_enabled
                        ? 'bg-slate-800 text-slate-300 hover:bg-red-500/20 hover:text-red-400 hover:border-red-500/30'
                        : 'bg-sky-500/20 text-sky-400 hover:bg-sky-500/30'
                    } border border-slate-700`}
                  >
                    {plugin.is_enabled ? 'Disable' : 'Enable'}
                  </button>
                </div>
                {plugin.error && (
                  <div className="mt-3 p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
                    Error: {plugin.error}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Plugin Details Sidebar */}
        <div className="space-y-4">
          {detailsLoading ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
              <div className="animate-pulse space-y-4">
                <div className="h-6 bg-slate-800 rounded w-3/4" />
                <div className="h-4 bg-slate-800 rounded w-1/2" />
                <div className="h-20 bg-slate-800 rounded" />
              </div>
            </div>
          ) : selectedPlugin ? (
            <>
              {/* Details Card */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
                <h3 className="text-lg font-medium text-white mb-4">
                  {selectedPlugin.display_name}
                </h3>
                <dl className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Version</dt>
                    <dd className="text-white">{selectedPlugin.version}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Author</dt>
                    <dd className="text-white">{selectedPlugin.author}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Category</dt>
                    <dd className="text-white capitalize">{selectedPlugin.category}</dd>
                  </div>
                  {selectedPlugin.homepage && (
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Homepage</dt>
                      <dd>
                        <a
                          href={selectedPlugin.homepage}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sky-400 hover:underline flex items-center gap-1"
                        >
                          Link <ExternalLink className="h-3 w-3" />
                        </a>
                      </dd>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Status</dt>
                    <dd className={selectedPlugin.is_enabled ? 'text-green-400' : 'text-slate-400'}>
                      {selectedPlugin.is_enabled ? 'Enabled' : 'Disabled'}
                    </dd>
                  </div>
                  {selectedPlugin.installed_at && (
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Installed</dt>
                      <dd className="text-white">
                        {new Date(selectedPlugin.installed_at).toLocaleDateString()}
                      </dd>
                    </div>
                  )}
                </dl>
              </div>

              {/* Permissions Card */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
                <h4 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
                  <Shield className="h-4 w-4" />
                  Required Permissions
                </h4>
                {selectedPlugin.required_permissions.length === 0 ? (
                  <p className="text-sm text-slate-500">No special permissions required</p>
                ) : (
                  <ul className="space-y-2">
                    {selectedPlugin.required_permissions.map((perm) => {
                      const isDangerous = selectedPlugin.dangerous_permissions.includes(perm);
                      const isGranted = selectedPlugin.granted_permissions.includes(perm);
                      return (
                        <li
                          key={perm}
                          className={`flex items-center justify-between text-sm p-2 rounded-lg ${
                            isDangerous
                              ? 'bg-amber-500/10 border border-amber-500/20'
                              : 'bg-slate-800/50'
                          }`}
                        >
                          <span className={isDangerous ? 'text-amber-400' : 'text-slate-300'}>
                            {perm}
                          </span>
                          {isGranted ? (
                            <Check className="h-4 w-4 text-green-400" />
                          ) : (
                            <X className="h-4 w-4 text-slate-500" />
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              {/* Actions Card */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 space-y-3">
                <button
                  onClick={() => setShowPermissionModal(true)}
                  disabled={!selectedPlugin.is_enabled}
                  className="w-full px-4 py-2 text-sm font-medium rounded-lg border border-slate-700 text-slate-300 hover:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <Settings className="h-4 w-4" />
                  Configure
                </button>
                <button
                  onClick={() => handleUninstall(selectedPlugin.name)}
                  disabled={actionLoading || selectedPlugin.is_enabled}
                  className="w-full px-4 py-2 text-sm font-medium rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <Trash2 className="h-4 w-4" />
                  Uninstall
                </button>
                {selectedPlugin.is_enabled && (
                  <p className="text-xs text-slate-500 text-center">
                    Disable the plugin before uninstalling
                  </p>
                )}
              </div>
            </>
          ) : (
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-center">
              <Settings className="h-8 w-8 mx-auto text-slate-600 mb-3" />
              <p className="text-sm text-slate-500">
                Select a plugin to view details
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Permission Grant Modal */}
      {showPermissionModal && selectedPlugin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
            <h3 className="text-lg font-medium text-white mb-2">
              Enable {selectedPlugin.display_name}
            </h3>
            <p className="text-sm text-slate-400 mb-4">
              This plugin requires the following permissions:
            </p>
            <div className="space-y-2 mb-6 max-h-64 overflow-y-auto">
              {selectedPlugin.required_permissions.map((perm) => {
                const permInfo = allPermissions.find((p) => p.value === perm);
                const isChecked = selectedPermissions.includes(perm);
                return (
                  <label
                    key={perm}
                    className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition ${
                      permInfo?.dangerous
                        ? 'bg-amber-500/10 border border-amber-500/20'
                        : 'bg-slate-800/50 border border-slate-700'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedPermissions([...selectedPermissions, perm]);
                        } else {
                          setSelectedPermissions(selectedPermissions.filter((p) => p !== perm));
                        }
                      }}
                      className="mt-1 rounded border-slate-600 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900"
                    />
                    <div>
                      <div className={`text-sm font-medium ${permInfo?.dangerous ? 'text-amber-400' : 'text-white'}`}>
                        {perm}
                        {permInfo?.dangerous && (
                          <span className="ml-2 text-xs text-amber-500">(Dangerous)</span>
                        )}
                      </div>
                      {permInfo && (
                        <p className="text-xs text-slate-500 mt-0.5">{permInfo.description}</p>
                      )}
                    </div>
                  </label>
                );
              })}
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setShowPermissionModal(false)}
                className="flex-1 px-4 py-2 text-sm font-medium rounded-lg border border-slate-700 text-slate-300 hover:border-slate-600"
              >
                Cancel
              </button>
              <button
                onClick={handleEnableWithPermissions}
                disabled={!selectedPlugin.required_permissions.every((p) => selectedPermissions.includes(p))}
                className="flex-1 px-4 py-2 text-sm font-medium rounded-lg bg-sky-500 text-white hover:bg-sky-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Enable Plugin
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
