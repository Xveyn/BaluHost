/**
 * VCL Tracking Panel — manages automatic/manual mode and tracking rules
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Shield,
  ShieldOff,
  Plus,
  Trash2,
  RefreshCw,
  AlertCircle,
  Check,
  FolderTree,
  FileText,
  Regex,
} from 'lucide-react';
import {
  getTrackingRules,
  addTrackingRule,
  removeTrackingRule,
  updateUserSettings,
} from '../../api/vcl';
import type {
  FileTrackingListResponse,
  VCLMode,
} from '../../types/vcl';

export default function VCLTrackingPanel() {
  const [data, setData] = useState<FileTrackingListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Add rule form
  const [showAddForm, setShowAddForm] = useState(false);
  const [newPattern, setNewPattern] = useState('');
  const [addLoading, setAddLoading] = useState(false);

  const loadRules = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const rules = await getTrackingRules();
      setData(rules);
    } catch {
      setError('Failed to load tracking rules');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRules();
  }, [loadRules]);

  const handleModeChange = async (newMode: VCLMode) => {
    if (!data) return;
    if (newMode === data.mode) return;

    const confirmed = confirm(
      newMode === 'manual'
        ? 'Switch to Manual mode? Only explicitly tracked files will be versioned.'
        : 'Switch to Automatic mode? All files will be versioned (exclusion rules still apply).'
    );
    if (!confirmed) return;

    try {
      setError(null);
      await updateUserSettings({ vcl_mode: newMode });
      setSuccess(`Mode changed to ${newMode}`);
      setTimeout(() => setSuccess(null), 3000);
      loadRules();
    } catch {
      setError('Failed to update mode');
    }
  };

  const handleAddPattern = async () => {
    if (!newPattern.trim() || !data) return;
    try {
      setAddLoading(true);
      setError(null);
      const action = data.mode === 'automatic' ? 'exclude' : 'track';
      await addTrackingRule({ path_pattern: newPattern.trim(), action });
      setNewPattern('');
      setShowAddForm(false);
      setSuccess('Rule added');
      setTimeout(() => setSuccess(null), 3000);
      loadRules();
    } catch {
      setError('Failed to add rule');
    } finally {
      setAddLoading(false);
    }
  };

  const handleRemoveRule = async (ruleId: number) => {
    try {
      setError(null);
      await removeTrackingRule(ruleId);
      setSuccess('Rule removed');
      setTimeout(() => setSuccess(null), 3000);
      loadRules();
    } catch {
      setError('Failed to remove rule');
    }
  };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-sky-500"></div>
      </div>
    );
  }

  const mode = data?.mode ?? 'automatic';
  const rules = data?.rules ?? [];

  return (
    <div className="space-y-4">
      {/* Messages */}
      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}
      {success && (
        <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center gap-2 text-green-400 text-sm">
          <Check className="w-4 h-4 flex-shrink-0" />
          {success}
        </div>
      )}

      {/* Mode Toggle */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Shield className="w-4 h-4 text-sky-400" />
          VCL Mode
        </h3>
        <div className="flex gap-3">
          <button
            onClick={() => handleModeChange('automatic')}
            className={`flex-1 px-4 py-3 rounded-lg border text-sm font-medium transition-all ${
              mode === 'automatic'
                ? 'border-sky-500/50 bg-sky-500/10 text-sky-300'
                : 'border-slate-700/50 bg-slate-800/50 text-slate-400 hover:text-slate-300'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <Shield className="w-4 h-4" />
              Automatic
            </div>
            <p className="text-xs opacity-70 font-normal">
              All files versioned. Add exclusion rules below.
            </p>
          </button>
          <button
            onClick={() => handleModeChange('manual')}
            className={`flex-1 px-4 py-3 rounded-lg border text-sm font-medium transition-all ${
              mode === 'manual'
                ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                : 'border-slate-700/50 bg-slate-800/50 text-slate-400 hover:text-slate-300'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <ShieldOff className="w-4 h-4" />
              Manual
            </div>
            <p className="text-xs opacity-70 font-normal">
              Only tracked files versioned. Enable per file.
            </p>
          </button>
        </div>
      </div>

      {/* Rules */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Regex className="w-4 h-4 text-sky-400" />
            {mode === 'automatic' ? 'Exclusion Rules' : 'Tracking Rules'}
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={loadRules}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white transition-colors"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-300 hover:bg-sky-500/20 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Pattern
            </button>
          </div>
        </div>

        {/* Add Pattern Form */}
        {showAddForm && (
          <div className="mb-4 p-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
            <label className="block text-xs text-slate-400 mb-1.5">
              Glob pattern (e.g. *.log, node_modules/*, *.tmp)
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={newPattern}
                onChange={(e) => setNewPattern(e.target.value)}
                placeholder="*.log"
                className="flex-1 px-3 py-2 text-sm bg-slate-900/80 border border-slate-700/50 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500/50"
                onKeyDown={(e) => e.key === 'Enter' && handleAddPattern()}
              />
              <button
                onClick={handleAddPattern}
                disabled={addLoading || !newPattern.trim()}
                className="px-4 py-2 text-sm bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {addLoading ? '...' : 'Add'}
              </button>
            </div>
          </div>
        )}

        {/* Rules List */}
        {rules.length === 0 ? (
          <p className="text-sm text-slate-500 py-4 text-center">
            {mode === 'automatic'
              ? 'No exclusion rules. All files are versioned.'
              : 'No tracking rules. Enable VCL for files via the file manager.'}
          </p>
        ) : (
          <div className="space-y-1.5">
            {rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center justify-between py-2 px-3 rounded-lg bg-slate-800/30 border border-slate-800/50 group"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {rule.path_pattern ? (
                    <Regex className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  ) : rule.is_directory ? (
                    <FolderTree className="w-4 h-4 text-amber-400 flex-shrink-0" />
                  ) : (
                    <FileText className="w-4 h-4 text-sky-400 flex-shrink-0" />
                  )}
                  <span className="text-sm text-slate-300 truncate">
                    {rule.path_pattern || rule.file_path || rule.file_name || `File #${rule.file_id}`}
                  </span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    rule.action === 'track'
                      ? 'bg-green-500/20 text-green-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {rule.action}
                  </span>
                  {rule.is_directory && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/20 text-amber-300">
                      dir
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleRemoveRule(rule.id)}
                  className="p-1 rounded text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                  title="Remove rule"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
