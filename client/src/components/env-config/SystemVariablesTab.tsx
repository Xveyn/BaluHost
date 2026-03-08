/**
 * System Variables Tab
 *
 * Admin UI for viewing and editing .env configuration files.
 * Curated variables grouped by category with sensitive value masking.
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Eye, EyeOff, ChevronDown, ChevronRight, RefreshCw, Save, Undo2, Info } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getEnvConfig,
  updateEnvConfig,
  revealEnvVar,
  type EnvVarResponse,
  type EnvConfigResponse,
} from '../../api/env-config';

type FileTab = 'backend' | 'client';

interface ModifiedValues {
  [key: string]: string;
}

interface RevealedKeys {
  [key: string]: string;
}

export default function SystemVariablesTab() {
  const { t } = useTranslation('system');
  const { t: tc } = useTranslation('common');

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<EnvConfigResponse | null>(null);
  const [activeFile, setActiveFile] = useState<FileTab>('backend');
  const [modified, setModified] = useState<ModifiedValues>({});
  const [revealedKeys, setRevealedKeys] = useState<RevealedKeys>({});
  const [revealingKey, setRevealingKey] = useState<string | null>(null);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());
  const [showRestartBanner, setShowRestartBanner] = useState(false);

  const loadConfig = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getEnvConfig();
      setConfig(data);
    } catch {
      toast.error(tc('toast.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [tc]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const currentVars: EnvVarResponse[] = config
    ? activeFile === 'backend'
      ? config.backend
      : config.client
    : [];

  // Group variables by category
  const grouped: Record<string, EnvVarResponse[]> = {};
  for (const v of currentVars) {
    if (!grouped[v.category]) grouped[v.category] = [];
    grouped[v.category].push(v);
  }
  const categoryOrder = Object.keys(grouped);

  const modifiedCount = Object.keys(modified).length;

  const getDisplayValue = (v: EnvVarResponse): string => {
    if (v.key in modified) return modified[v.key];
    if (v.key in revealedKeys) return revealedKeys[v.key];
    return v.value;
  };

  const handleChange = (key: string, value: string, originalValue: string) => {
    // If reverted to original, remove from modified
    const compareOriginal = key in revealedKeys ? revealedKeys[key] : originalValue;
    if (value === compareOriginal) {
      const next = { ...modified };
      delete next[key];
      setModified(next);
    } else {
      setModified({ ...modified, [key]: value });
    }
  };

  const handleReveal = async (key: string) => {
    if (key in revealedKeys) {
      // Hide it again
      const next = { ...revealedKeys };
      delete next[key];
      setRevealedKeys(next);
      return;
    }
    try {
      setRevealingKey(key);
      const value = await revealEnvVar(key);
      setRevealedKeys((prev) => ({ ...prev, [key]: value }));
    } catch {
      toast.error(tc('toast.loadFailed'));
    } finally {
      setRevealingKey(null);
    }
  };

  const handleSave = async () => {
    if (modifiedCount === 0) return;
    try {
      setSaving(true);
      await updateEnvConfig({
        file: activeFile,
        updates: Object.entries(modified).map(([key, value]) => ({ key, value })),
      });
      toast.success(tc('toast.configSaved'));
      setModified({});
      setRevealedKeys({});
      setShowRestartBanner(true);
      await loadConfig();
    } catch {
      toast.error(tc('toast.configFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    setModified({});
  };

  const toggleCategory = (cat: string) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-6 w-6 text-slate-400 animate-spin" />
        <span className="ml-3 text-slate-400">{tc('status.loading')}</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Warning Banner */}
      <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
        <AlertTriangle className="h-5 w-5 text-amber-400 mt-0.5 flex-shrink-0" />
        <div>
          <p className="text-sm font-semibold text-amber-300">{t('envConfig.warning.title')}</p>
          <p className="text-xs text-amber-300/80 mt-1">{t('envConfig.warning.message')}</p>
        </div>
      </div>

      {/* Restart Banner */}
      {showRestartBanner && (
        <div className="flex items-start gap-3 rounded-lg border border-yellow-500/40 bg-yellow-500/10 p-4">
          <Info className="h-5 w-5 text-yellow-400 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-yellow-300">{t('envConfig.warning.restartTitle')}</p>
            <p className="text-xs text-yellow-300/80 mt-1">{t('envConfig.warning.restartMessage')}</p>
          </div>
          <button
            onClick={() => setShowRestartBanner(false)}
            className="text-yellow-400 hover:text-yellow-300 text-xs"
          >
            {tc('buttons.close')}
          </button>
        </div>
      )}

      {/* File Tabs + Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex gap-2">
          <button
            onClick={() => { setActiveFile('backend'); setModified({}); setRevealedKeys({}); }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeFile === 'backend'
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
            }`}
          >
            {t('envConfig.files.backend')}
          </button>
          <button
            onClick={() => { setActiveFile('client'); setModified({}); setRevealedKeys({}); }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeFile === 'client'
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
            }`}
          >
            {t('envConfig.files.client')}
          </button>
        </div>

        <div className="flex items-center gap-2">
          {modifiedCount > 0 && (
            <span className="text-xs text-amber-400">
              {modifiedCount} {t('envConfig.labels.modified')}
            </span>
          )}
          <button
            onClick={handleDiscard}
            disabled={modifiedCount === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-300 hover:bg-slate-800/50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            <Undo2 className="h-3.5 w-3.5" />
            {t('envConfig.actions.discard')}
          </button>
          <button
            onClick={loadConfig}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-300 hover:bg-slate-800/50 transition-all"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            {t('envConfig.actions.refresh')}
          </button>
          <button
            onClick={handleSave}
            disabled={modifiedCount === 0 || saving}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            <Save className="h-3.5 w-3.5" />
            {saving ? tc('status.processing') : t('envConfig.actions.save')}
          </button>
        </div>
      </div>

      {/* Category Accordions */}
      <div className="space-y-3">
        {categoryOrder.map((cat) => {
          const vars = grouped[cat];
          const isCollapsed = collapsedCategories.has(cat);
          const hasModified = vars.some((v) => v.key in modified);

          return (
            <div key={cat} className="rounded-lg border border-slate-700/60 bg-slate-800/30 overflow-hidden">
              {/* Category Header */}
              <button
                onClick={() => toggleCategory(cat)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800/50 transition-colors"
              >
                <div className="flex items-center gap-2">
                  {isCollapsed
                    ? <ChevronRight className="h-4 w-4 text-slate-500" />
                    : <ChevronDown className="h-4 w-4 text-slate-500" />}
                  <span className="text-sm font-semibold text-slate-200">
                    {t(`envConfig.categories.${cat}`)}
                  </span>
                  <span className="text-xs text-slate-500">({vars.length})</span>
                  {hasModified && (
                    <span className="h-2 w-2 rounded-full bg-amber-400" />
                  )}
                </div>
              </button>

              {/* Variables */}
              {!isCollapsed && (
                <div className="border-t border-slate-700/40">
                  {vars.map((v) => {
                    const displayValue = getDisplayValue(v);
                    const isModified = v.key in modified;
                    const isRevealed = v.key in revealedKeys;
                    const isSensitive = v.is_sensitive;

                    return (
                      <div
                        key={v.key}
                        className={`px-4 py-3 border-b border-slate-700/20 last:border-b-0 ${
                          isModified ? 'bg-amber-500/5' : ''
                        }`}
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
                          {/* Label */}
                          <div className="sm:w-1/3 min-w-0">
                            <div className="flex items-center gap-2">
                              <code className="text-xs text-slate-300 font-mono truncate">{v.key}</code>
                              {isModified && (
                                <span className="h-1.5 w-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                              )}
                            </div>
                            {v.default != null && (
                              <p className="text-[10px] text-slate-500 mt-0.5">
                                {t('envConfig.labels.default')}: {v.default || '""'}
                              </p>
                            )}
                          </div>

                          {/* Input */}
                          <div className="flex-1 flex items-center gap-2">
                            {v.input_type === 'boolean' ? (
                              <button
                                onClick={() => {
                                  const current = displayValue.toLowerCase();
                                  const next = (current === 'true' || current === '1') ? 'false' : 'true';
                                  handleChange(v.key, next, v.value);
                                }}
                                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                                  ['true', '1'].includes(displayValue.toLowerCase())
                                    ? 'bg-blue-500'
                                    : 'bg-slate-600'
                                }`}
                              >
                                <span
                                  className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                                    ['true', '1'].includes(displayValue.toLowerCase())
                                      ? 'translate-x-6'
                                      : 'translate-x-1'
                                  }`}
                                />
                              </button>
                            ) : (
                              <div className="flex-1 flex items-center gap-1.5">
                                <input
                                  type={isSensitive && !isRevealed ? 'password' : v.input_type === 'number' ? 'number' : 'text'}
                                  value={displayValue}
                                  onChange={(e) => handleChange(v.key, e.target.value, v.value)}
                                  className="flex-1 bg-slate-900/60 border border-slate-600/50 rounded px-3 py-1.5 text-xs text-slate-200 font-mono focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 outline-none transition-all"
                                  placeholder={v.default || ''}
                                />
                                {isSensitive && (
                                  <button
                                    onClick={() => handleReveal(v.key)}
                                    disabled={revealingKey === v.key}
                                    className="p-1.5 text-slate-400 hover:text-slate-300 transition-colors"
                                    title={isRevealed ? t('envConfig.labels.hide') : t('envConfig.labels.reveal')}
                                  >
                                    {revealingKey === v.key ? (
                                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                    ) : isRevealed ? (
                                      <EyeOff className="h-3.5 w-3.5" />
                                    ) : (
                                      <Eye className="h-3.5 w-3.5" />
                                    )}
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
