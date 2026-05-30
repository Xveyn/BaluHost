/**
 * Boost Rules Editor
 *
 * Lists boost rules and allows creating, toggling, and deleting them.
 * Also provides the "Boost Now" one-shot control.
 *
 * All mutating actions are disabled when channel != local.
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Lock, Trash2, Plus } from 'lucide-react';
import { AdminBadge } from '../ui/AdminBadge';
import { useChannelStatus } from '../../hooks/useChannelStatus';
import {
  listBoostRules,
  createBoostRule,
  updateBoostRule,
  deleteBoostRule,
  boostNow,
  type BoostRule,
  type BoostRuleKind,
} from '../../api/power-management';
import { getApiErrorMessage } from '../../lib/errorHandling';

const DURATION_OPTIONS: { labelKey: string; seconds: number }[] = [
  { labelKey: 'duration30m', seconds: 30 * 60 },
  { labelKey: 'duration1h', seconds: 60 * 60 },
  { labelKey: 'duration2h', seconds: 2 * 60 * 60 },
  { labelKey: 'duration4h', seconds: 4 * 60 * 60 },
  { labelKey: 'duration8h', seconds: 8 * 60 * 60 },
];

interface AddRuleFormState {
  kind: BoostRuleKind;
  label: string;
  pattern: string;
  target_max_mhz: string;
}

const BLANK_FORM: AddRuleFormState = {
  kind: 'process_glob',
  label: '',
  pattern: '',
  target_max_mhz: '',
};

interface BoostRulesEditorProps {
  isAdmin: boolean;
}

export function BoostRulesEditor({ isAdmin }: BoostRulesEditorProps) {
  const { t } = useTranslation(['system']);
  const { isLocal, isLoading: channelLoading } = useChannelStatus();

  const [rules, setRules] = useState<BoostRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [form, setForm] = useState<AddRuleFormState>(BLANK_FORM);

  // Boost-now state
  const [boostDuration, setBoostDuration] = useState(DURATION_OPTIONS[0].seconds);
  const [boostTargetMhz, setBoostTargetMhz] = useState('');
  const [boosting, setBoosting] = useState(false);

  const mutateDisabled = !isAdmin || !isLocal || busy || channelLoading;

  const loadRules = useCallback(async () => {
    try {
      const res = await listBoostRules();
      setRules(res.rules);
    } catch {
      // Non-fatal — empty list is fine
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  const handleToggleRule = async (rule: BoostRule) => {
    if (mutateDisabled) return;
    setBusy(true);
    try {
      const updated = await updateBoostRule(rule.id, { enabled: !rule.enabled });
      setRules((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (err) {
      toast.error(getApiErrorMessage(err, t('system:power.boostRules.updateFailed')));
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteRule = async (rule: BoostRule) => {
    if (mutateDisabled) return;
    setBusy(true);
    try {
      await deleteBoostRule(rule.id);
      setRules((prev) => prev.filter((r) => r.id !== rule.id));
    } catch (err) {
      toast.error(getApiErrorMessage(err, t('system:power.boostRules.deleteFailed')));
    } finally {
      setBusy(false);
    }
  };

  const handleAddRule = async () => {
    if (mutateDisabled) return;
    setBusy(true);
    try {
      const created = await createBoostRule({
        kind: form.kind,
        label: form.label.trim(),
        pattern: form.kind === 'process_glob' && form.pattern.trim() ? form.pattern.trim() : undefined,
        target_max_mhz: form.target_max_mhz ? Number(form.target_max_mhz) : undefined,
      });
      setRules((prev) => [...prev, created]);
      setForm(BLANK_FORM);
      setShowAddForm(false);
    } catch (err) {
      toast.error(getApiErrorMessage(err, t('system:power.boostRules.createFailed')));
    } finally {
      setBusy(false);
    }
  };

  const handleBoostNow = async () => {
    if (!isLocal || boosting || !isAdmin) return;
    setBoosting(true);
    try {
      const res = await boostNow({
        duration_seconds: boostDuration,
        target_max_mhz: boostTargetMhz ? Number(boostTargetMhz) : undefined,
      });
      const durationLabel = DURATION_OPTIONS.find((d) => d.seconds === res.duration_seconds)?.labelKey;
      toast.success(
        t('system:power.boostRules.boostNowSuccess', {
          duration: durationLabel ? t(`system:power.boostRules.${durationLabel}`) : `${res.duration_seconds}s`,
        })
      );
    } catch (err) {
      toast.error(getApiErrorMessage(err, t('system:power.boostRules.boostNowFailed')));
    } finally {
      setBoosting(false);
    }
  };

  const localOnlyHint = !isLocal && !channelLoading && (
    <p className="flex items-center gap-1 text-xs text-slate-500 mt-1">
      <Lock className="h-3 w-3" />
      {t('system:power.boostRules.localOnlyHint')}
    </p>
  );

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <h2 className="text-base sm:text-lg font-medium text-white flex items-center gap-2">
          {t('system:power.boostRules.title')}
          {isAdmin && <AdminBadge />}
        </h2>
      </div>

      {/* Rules list */}
      <div>
        <h3 className="text-sm font-medium text-slate-300 mb-3">
          {t('system:power.boostRules.rulesTitle')}
        </h3>

        {loading ? (
          <div className="space-y-2">
            {[0, 1].map((i) => (
              <div key={i} className="h-12 animate-pulse rounded bg-slate-700/40" />
            ))}
          </div>
        ) : rules.length === 0 ? (
          <p className="text-sm text-slate-500">{t('system:power.boostRules.noRules')}</p>
        ) : (
          <div className="space-y-2">
            {rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-white truncate">{rule.label}</span>
                    <span className="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">
                      {rule.kind === 'process_glob'
                        ? t('system:power.boostRules.kindProcessGlob')
                        : t('system:power.boostRules.kindGameSession')}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-0.5">
                    {rule.pattern && (
                      <span className="text-xs text-slate-500 font-mono">{rule.pattern}</span>
                    )}
                    {rule.target_max_mhz && (
                      <span className="text-xs text-slate-500">{rule.target_max_mhz} MHz</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {/* Enabled toggle */}
                  <button
                    role="switch"
                    aria-checked={rule.enabled}
                    onClick={() => handleToggleRule(rule)}
                    disabled={mutateDisabled}
                    title={t('system:power.boostRules.enabledLabel')}
                    className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                      rule.enabled ? 'bg-emerald-500' : 'bg-slate-600'
                    }`}
                  >
                    <span
                      className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                        rule.enabled ? 'translate-x-5' : 'translate-x-1'
                      }`}
                    />
                  </button>

                  {/* Delete */}
                  <button
                    onClick={() => handleDeleteRule(rule)}
                    disabled={mutateDisabled}
                    title={t('system:power.boostRules.deleteButton')}
                    className="rounded p-1 text-slate-500 hover:text-red-400 hover:bg-red-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add rule button / form */}
        {isAdmin && (
          <div className="mt-3">
            {!showAddForm ? (
              <div>
                <button
                  onClick={() => setShowAddForm(true)}
                  disabled={mutateDisabled}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <Plus className="h-4 w-4" />
                  {t('system:power.boostRules.addRule')}
                </button>
                {localOnlyHint}
              </div>
            ) : (
              <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 space-y-3">
                {/* Kind */}
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    {t('system:power.boostRules.kindLabel')}
                  </label>
                  <select
                    value={form.kind}
                    onChange={(e) => setForm({ ...form, kind: e.target.value as BoostRuleKind, pattern: '' })}
                    disabled={busy}
                    className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-blue-400 focus:outline-none disabled:opacity-50"
                  >
                    <option value="process_glob">{t('system:power.boostRules.kindProcessGlob')}</option>
                    <option value="game_session">{t('system:power.boostRules.kindGameSession')}</option>
                  </select>
                </div>

                {/* Label */}
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    {t('system:power.boostRules.labelLabel')}
                  </label>
                  <input
                    type="text"
                    value={form.label}
                    onChange={(e) => setForm({ ...form, label: e.target.value })}
                    disabled={busy}
                    className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-blue-400 focus:outline-none disabled:opacity-50"
                  />
                </div>

                {/* Pattern (process_glob only) */}
                {form.kind === 'process_glob' && (
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      {t('system:power.boostRules.patternLabel')}
                    </label>
                    <input
                      type="text"
                      value={form.pattern}
                      onChange={(e) => setForm({ ...form, pattern: e.target.value })}
                      disabled={busy}
                      placeholder="e.g. ffmpeg*"
                      className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-blue-400 focus:outline-none disabled:opacity-50 font-mono"
                    />
                  </div>
                )}

                {/* Target MHz */}
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    {t('system:power.boostRules.targetMhzLabel')}
                  </label>
                  <input
                    type="number"
                    min={400}
                    max={6000}
                    value={form.target_max_mhz}
                    onChange={(e) => setForm({ ...form, target_max_mhz: e.target.value })}
                    disabled={busy}
                    placeholder="— full boost"
                    className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-blue-400 focus:outline-none disabled:opacity-50"
                  />
                </div>

                {/* Actions */}
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => { setShowAddForm(false); setForm(BLANK_FORM); }}
                    disabled={busy}
                    className="rounded px-3 py-1.5 text-sm bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
                  >
                    {t('system:power.boostRules.cancelButton')}
                  </button>
                  <button
                    onClick={handleAddRule}
                    disabled={busy || !form.label.trim()}
                    className="rounded px-3 py-1.5 text-sm bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {t('system:power.boostRules.saveButton')}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Boost Now */}
      {isAdmin && (
        <div className="border-t border-slate-700/50 pt-4 space-y-3">
          <h3 className="text-sm font-medium text-slate-300">
            {t('system:power.boostRules.boostNowTitle')}
          </h3>

          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end">
            {/* Duration */}
            <div className="flex-1">
              <label className="block text-xs text-slate-400 mb-1">
                {t('system:power.boostRules.durationLabel')}
              </label>
              <select
                value={boostDuration}
                onChange={(e) => setBoostDuration(Number(e.target.value))}
                disabled={!isLocal || boosting}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-blue-400 focus:outline-none disabled:opacity-50"
              >
                {DURATION_OPTIONS.map((opt) => (
                  <option key={opt.seconds} value={opt.seconds}>
                    {t(`system:power.boostRules.${opt.labelKey}`)}
                  </option>
                ))}
              </select>
            </div>

            {/* Target MHz */}
            <div className="flex-1">
              <label className="block text-xs text-slate-400 mb-1">
                {t('system:power.boostRules.targetMhzBoostLabel')}
              </label>
              <input
                type="number"
                min={400}
                max={6000}
                value={boostTargetMhz}
                onChange={(e) => setBoostTargetMhz(e.target.value)}
                disabled={!isLocal || boosting}
                placeholder="— full boost"
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-blue-400 focus:outline-none disabled:opacity-50"
              />
            </div>

            {/* Boost button */}
            <button
              onClick={handleBoostNow}
              disabled={!isLocal || boosting || !isAdmin}
              className="rounded-lg px-4 py-2 text-sm font-medium bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap min-h-[40px]"
            >
              {t('system:power.boostRules.boostNowButton')}
            </button>
          </div>

          {localOnlyHint}
        </div>
      )}
    </div>
  );
}
