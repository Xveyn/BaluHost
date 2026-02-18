/**
 * Rate Limits Tab Component
 *
 * Admin-only component for managing API rate limits.
 * Moved from ApiCenterPage to SystemControlPage.
 */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Zap, Settings, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { buildApiUrl, extractErrorMessage } from '../../lib/api';
import { useAuth } from '../../contexts/AuthContext';

// ==================== Types ====================

export interface RateLimitConfig {
  id: number;
  endpoint_type: string;
  limit_string: string;
  description: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string | null;
  updated_by: number | null;
}

// ==================== Rate Limit Edit Modal ====================

interface RateLimitModalProps {
  config: RateLimitConfig | null;
  onClose: () => void;
  onSave: (endpointType: string, data: { limit_string: string; description: string; enabled: boolean }) => Promise<void>;
  t: (key: string) => string;
}

function RateLimitModal({ config, onClose, onSave, t }: RateLimitModalProps) {
  const [form, setForm] = useState({
    limit_string: config?.limit_string || '',
    description: config?.description || '',
    enabled: config?.enabled ?? true
  });
  const [saving, setSaving] = useState(false);

  if (!config) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(config.endpoint_type, form);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-slate-900 border border-slate-700/50 rounded-xl p-4 sm:p-6 w-full max-w-md max-h-[100vh] sm:max-h-[90vh] overflow-y-auto shadow-2xl">
        <h3 className="text-lg sm:text-xl font-bold text-white mb-4 flex items-center gap-2">
          <Zap className="w-5 h-5 text-yellow-400" />
          {t('system:apiCenter.modal.editRateLimit')}
        </h3>

        <div className="space-y-4">
          <div>
            <label className="block text-xs sm:text-sm font-medium text-slate-300 mb-1">{t('system:apiCenter.modal.endpoint')}</label>
            <code className="block w-full px-3 py-2 bg-slate-900/60 border border-slate-700/50 rounded-lg text-cyan-400 text-xs sm:text-sm truncate">
              {config.endpoint_type}
            </code>
          </div>

          <div>
            <label className="block text-xs sm:text-sm font-medium text-slate-300 mb-1">{t('system:apiCenter.modal.rateLimit')}</label>
            <input
              type="text"
              value={form.limit_string}
              onChange={(e) => setForm({ ...form, limit_string: e.target.value })}
              className="w-full px-3 py-2.5 bg-slate-900/60 border border-slate-700/50 rounded-lg text-white focus:border-cyan-500 focus:outline-none text-sm min-h-[44px]"
              placeholder="5/minute"
            />
            <p className="text-[10px] sm:text-xs text-slate-500 mt-1">{t('system:apiCenter.modal.rateLimitFormat')}</p>
          </div>

          <div>
            <label className="block text-xs sm:text-sm font-medium text-slate-300 mb-1">{t('system:apiCenter.modal.description')}</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2.5 bg-slate-900/60 border border-slate-700/50 rounded-lg text-white focus:border-cyan-500 focus:outline-none text-sm min-h-[44px]"
              placeholder={t('system:apiCenter.modal.descriptionPlaceholder')}
            />
          </div>

          <div className="flex items-center gap-3 min-h-[44px]">
            <input
              type="checkbox"
              id="enabled"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              className="w-5 h-5 rounded"
            />
            <label htmlFor="enabled" className="text-sm text-slate-300">{t('system:apiCenter.modal.enabled')}</label>
          </div>
        </div>

        <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 sm:gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors touch-manipulation active:scale-95 min-h-[44px]"
          >
            {t('system:apiCenter.modal.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors disabled:opacity-50 touch-manipulation active:scale-95 min-h-[44px]"
          >
            {saving ? t('system:apiCenter.modal.saving') : t('system:apiCenter.modal.saveChanges')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ==================== Main Component ====================

export default function RateLimitsTab() {
  const { t } = useTranslation(['system', 'common']);
  const { token } = useAuth();
  const [rateLimitsList, setRateLimitsList] = useState<RateLimitConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<RateLimitConfig | null>(null);

  useEffect(() => {
    loadRateLimits();
  }, []);

  const loadRateLimits = async () => {
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(buildApiUrl('/api/admin/rate-limits'), {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setRateLimitsList(data.configs);
      }
    } catch {
      // Non-critical: rate limits list will remain empty
    } finally {
      setLoading(false);
    }
  };

  const handleSaveRateLimit = async (
    endpointType: string,
    data: { limit_string: string; description: string; enabled: boolean }
  ) => {
    if (!token) {
      toast.error(t('system:apiCenter.toasts.notAuthenticated'));
      return;
    }

    const response = await fetch(buildApiUrl(`/api/admin/rate-limits/${endpointType}`), {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        limit_string: data.limit_string,
        description: data.description || null,
        enabled: data.enabled
      })
    });

    if (response.ok) {
      toast.success(t('system:apiCenter.toasts.rateLimitUpdated'));
      loadRateLimits();
    } else {
      const error = await response.json();
      toast.error(extractErrorMessage(error.detail, t('system:apiCenter.toasts.updateFailed')));
      throw new Error('Failed to save');
    }
  };

  const handleSeedDefaults = async () => {
    if (!confirm(t('system:apiCenter.rateLimits.seedConfirm'))) return;

    if (!token) return;

    try {
      const response = await fetch(buildApiUrl('/api/admin/rate-limits/seed-defaults'), {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        toast.success(t('system:apiCenter.toasts.defaultsSeeded'));
        loadRateLimits();
      } else {
        toast.error(t('system:apiCenter.toasts.seedFailed'));
      }
    } catch (error) {
      toast.error(t('system:apiCenter.toasts.seedFailed'));
    }
  };

  const handleToggleEnabled = async (config: RateLimitConfig) => {
    if (!token) return;

    try {
      const response = await fetch(buildApiUrl(`/api/admin/rate-limits/${config.endpoint_type}`), {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ enabled: !config.enabled })
      });

      if (response.ok) {
        toast.success(!config.enabled ? t('system:apiCenter.rateLimits.enabled') : t('system:apiCenter.rateLimits.disabled'));
        loadRateLimits();
      }
    } catch (error) {
      toast.error(t('system:apiCenter.toasts.updateFailed'));
    }
  };

  const getCategoryFromEndpoint = (endpoint: string): string => {
    if (endpoint.startsWith('auth_')) return t('system:apiCenter.categories.authentication');
    if (endpoint.startsWith('file_')) return t('system:apiCenter.categories.fileOperations');
    if (endpoint.startsWith('share_')) return t('system:apiCenter.categories.sharing');
    if (endpoint.startsWith('mobile_')) return t('system:apiCenter.categories.mobile');
    if (endpoint.startsWith('vpn_')) return t('system:apiCenter.categories.vpn');
    if (endpoint.startsWith('backup_')) return t('system:apiCenter.categories.backup', 'Backup');
    if (endpoint.startsWith('sync_')) return t('system:apiCenter.categories.sync', 'Sync');
    if (endpoint.includes('admin')) return t('system:apiCenter.categories.admin');
    if (endpoint.includes('user')) return t('system:apiCenter.categories.users');
    if (endpoint.includes('system')) return t('system:apiCenter.categories.system');
    return t('system:apiCenter.categories.other');
  };

  const groupedRateLimits = rateLimitsList.reduce((acc, config) => {
    const category = getCategoryFromEndpoint(config.endpoint_type);
    if (!acc[category]) acc[category] = [];
    acc[category].push(config);
    return acc;
  }, {} as Record<string, RateLimitConfig[]>);

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Actions */}
      <div className="flex flex-wrap gap-2 sm:gap-3">
        <button
          onClick={handleSeedDefaults}
          className="px-3 sm:px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors flex items-center gap-2 text-xs sm:text-sm touch-manipulation active:scale-95 min-h-[40px]"
        >
          🌱 <span className="hidden sm:inline">{t('system:apiCenter.rateLimits.seedDefaults')}</span>
        </button>
        <button
          onClick={loadRateLimits}
          className="px-3 sm:px-4 py-2 bg-slate-700/50 hover:bg-slate-700 text-white rounded-lg transition-colors flex items-center gap-2 text-xs sm:text-sm touch-manipulation active:scale-95 min-h-[40px]"
        >
          <RefreshCw className="w-4 h-4" />
          <span className="hidden sm:inline">{t('system:apiCenter.buttons.refresh')}</span>
        </button>
      </div>

      {/* Info Box */}
      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-3 sm:p-4">
        <h3 className="text-yellow-400 font-semibold text-sm sm:text-base mb-2 flex items-center gap-2">
          <Zap className="w-4 h-4 sm:w-5 sm:h-5" />
          {t('system:apiCenter.rateLimits.title')}
        </h3>
        <p className="text-slate-300 text-xs sm:text-sm">
          <span className="hidden sm:inline">{t('system:apiCenter.rateLimits.description')} </span>{t('system:apiCenter.rateLimits.format')}: <code className="bg-slate-900/60 px-1.5 sm:px-2 py-0.5 rounded text-[10px] sm:text-xs">number/unit</code>
          {' '}({t('system:apiCenter.rateLimits.example')}, <code className="bg-slate-900/60 px-1.5 sm:px-2 py-0.5 rounded text-[10px] sm:text-xs">5/min</code>)
        </p>
      </div>

      {/* Rate Limits by Category */}
      {loading ? (
        <div className="text-slate-400 text-sm">{t('system:apiCenter.rateLimits.loading')}</div>
      ) : Object.keys(groupedRateLimits).length === 0 ? (
        <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-slate-700/50 p-8 sm:p-12 text-center">
          <p className="text-slate-400 text-sm mb-4">{t('system:apiCenter.rateLimits.noConfigs')}</p>
          <button
            onClick={handleSeedDefaults}
            className="px-4 sm:px-6 py-2.5 sm:py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors text-sm touch-manipulation active:scale-95 min-h-[44px]"
          >
            🌱 {t('system:apiCenter.rateLimits.seedDefaults')}
          </button>
        </div>
      ) : (
        Object.entries(groupedRateLimits).map(([category, configs]) => (
          <div key={category} className="bg-slate-800/40 backdrop-blur-sm rounded-xl border-2 border-amber-500/40 overflow-hidden">
            {/* Category Header */}
            <div className="flex items-center gap-2 sm:gap-3 p-3 sm:p-4 border-b border-amber-500/30 bg-slate-800/60">
              <div className="p-1.5 bg-amber-500/20 rounded-lg text-amber-400">
                <Zap className="w-4 h-4" />
              </div>
              <h2 className="text-base sm:text-lg font-bold text-white">{category}</h2>
              <span className="text-xs text-slate-500">({configs.length})</span>
            </div>

            {/* Desktop table */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-xs text-slate-400 border-b border-slate-700/30">
                    <th className="px-4 py-2 font-medium">{t('system:apiCenter.rateLimits.endpoint')}</th>
                    <th className="px-4 py-2 font-medium">{t('system:apiCenter.rateLimits.limit')}</th>
                    <th className="px-4 py-2 font-medium">{t('system:apiCenter.rateLimits.status')}</th>
                    <th className="px-4 py-2 font-medium text-right">{t('system:apiCenter.rateLimits.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {configs.map((config) => (
                    <tr
                      key={config.id}
                      className="border-b border-slate-700/20 last:border-b-0 hover:bg-slate-700/20 transition-colors"
                      title={config.description || undefined}
                    >
                      <td className="px-4 py-3">
                        <code className="text-cyan-400 font-mono text-sm">{config.endpoint_type}</code>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-emerald-400 font-semibold text-sm font-mono">{config.limit_string}</span>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => handleToggleEnabled(config)}
                          className={`px-2 py-1 rounded text-xs font-medium transition-colors touch-manipulation active:scale-95 ${
                            config.enabled
                              ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                              : 'bg-slate-600/30 text-slate-400 hover:bg-slate-600/50'
                          }`}
                        >
                          {config.enabled ? `✓ ${t('system:apiCenter.rateLimits.active')}` : `✗ ${t('system:apiCenter.rateLimits.off')}`}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => setEditingConfig(config)}
                          className="p-2 bg-blue-600/20 hover:bg-blue-600/40 text-blue-400 rounded-lg transition-colors touch-manipulation active:scale-95"
                          title={t('system:apiCenter.buttons.editRateLimit')}
                        >
                          <Settings className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile card view */}
            <div className="sm:hidden space-y-2 px-2">
              {configs.map((config) => (
                <div
                  key={`${config.id}-mobile`}
                  className="rounded-lg border border-slate-800/60 bg-slate-900/60 p-3"
                >
                  <div className="flex items-center justify-between">
                    <code className="text-cyan-400 font-mono text-xs truncate flex-1 min-w-0">{config.endpoint_type}</code>
                    <div className="flex items-center gap-1.5 ml-2 flex-shrink-0">
                      <button
                        onClick={() => handleToggleEnabled(config)}
                        className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors touch-manipulation ${
                          config.enabled
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-slate-600/30 text-slate-400'
                        }`}
                      >
                        {config.enabled ? '✓' : '✗'}
                      </button>
                      <button
                        onClick={() => setEditingConfig(config)}
                        className="p-1.5 bg-blue-600/20 text-blue-400 rounded-lg touch-manipulation"
                      >
                        <Settings className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-emerald-400 font-mono">{config.limit_string}</div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}

      {/* Edit Modal */}
      {editingConfig && (
        <RateLimitModal
          config={editingConfig}
          onClose={() => setEditingConfig(null)}
          onSave={handleSaveRateLimit}
          t={t}
        />
      )}
    </div>
  );
}
