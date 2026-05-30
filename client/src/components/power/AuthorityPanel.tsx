/**
 * Authority Panel
 *
 * Shows and controls the CPU power authority status:
 * - Toggle for "BaluHost controls CPU exclusively" (masks power-profiles-daemon)
 * - Drift badge when an external override was detected and corrected
 * - Cap-unenforceable badge when the kernel/driver cannot honour the cap
 * - ppd_active / ppd_masked status indicators
 *
 * Mutating controls are disabled when channel != local (require Companion app).
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Lock } from 'lucide-react';
import { AdminBadge } from '../ui/AdminBadge';
import { useChannelStatus } from '../../hooks/useChannelStatus';
import {
  getAuthority,
  updateAuthority,
  type PowerAuthorityResponse,
} from '../../api/power-management';
import { getApiErrorMessage } from '../../lib/errorHandling';

interface AuthorityPanelProps {
  isAdmin: boolean;
}

export function AuthorityPanel({ isAdmin }: AuthorityPanelProps) {
  const { t } = useTranslation(['system']);
  const { isLocal, isLoading: channelLoading } = useChannelStatus();

  const [authority, setAuthority] = useState<PowerAuthorityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await getAuthority();
      setAuthority(data);
      setError(null);
    } catch (err) {
      setError(getApiErrorMessage(err, t('system:power.authority.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleToggleExternalAuthority = async () => {
    if (!authority || busy || !isLocal) return;
    const next = !authority.external_authority_enabled;
    setBusy(true);
    try {
      const updated = await updateAuthority({ external_authority_enabled: next });
      setAuthority(updated);
    } catch (err) {
      const msg = getApiErrorMessage(err, t('system:power.authority.saveFailed'));
      // If 403 local_channel_required or 500 (acquire failed / sudoers missing), show a specific hint
      toast.error(msg.includes('local_channel') ? t('system:power.authority.enableFailed') : msg);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="text-base sm:text-lg font-medium text-white mb-3">
          {t('system:power.authority.title')}
        </h2>
        <div className="h-10 animate-pulse rounded bg-slate-700/40" />
      </div>
    );
  }

  if (error && !authority) {
    return (
      <div className="card border-red-500/30 bg-red-500/10 p-4 sm:p-6">
        <h2 className="text-base sm:text-lg font-medium text-white mb-2">
          {t('system:power.authority.title')}
        </h2>
        <p className="text-sm text-red-300">{error}</p>
      </div>
    );
  }

  if (!authority) return null;

  const mutateDisabled = !isAdmin || !isLocal || busy || channelLoading;

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <h2 className="text-base sm:text-lg font-medium text-white flex items-center gap-2">
          {t('system:power.authority.title')}
          {isAdmin && <AdminBadge />}
        </h2>

        {/* Status badges */}
        <div className="flex flex-wrap items-center gap-2">
          {authority.cap_unenforceable && (
            <span
              className="rounded-full bg-red-500/20 px-2.5 py-0.5 text-xs font-medium text-red-300"
              title={t('system:power.authority.capUnenforceableTitle')}
            >
              {t('system:power.authority.capUnenforceableTitle')}
            </span>
          )}
          {authority.last_drift && (
            <span
              className="rounded-full bg-amber-500/20 px-2.5 py-0.5 text-xs font-medium text-amber-300 cursor-help"
              title={[
                `${t('system:power.authority.driftTooltipAt')}: ${new Date(authority.last_drift.at).toLocaleTimeString()}`,
                `${t('system:power.authority.driftTooltipExpected')}: ${authority.last_drift.expected}`,
                `${t('system:power.authority.driftTooltipFound')}: ${authority.last_drift.found}`,
              ].join(' | ')}
            >
              {t('system:power.authority.driftBadge')}
            </span>
          )}
        </div>
      </div>

      {/* External authority toggle */}
      {isAdmin && (
        <div className="flex items-center justify-between gap-4">
          <div className="flex-1">
            <p className="text-sm text-slate-300">
              {t('system:power.authority.externalAuthorityLabel')}
            </p>
            {!isLocal && !channelLoading && (
              <p className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                <Lock className="h-3 w-3" />
                {t('system:power.authority.localOnlyHint')}
              </p>
            )}
          </div>
          <button
            role="switch"
            aria-checked={authority.external_authority_enabled}
            onClick={handleToggleExternalAuthority}
            disabled={mutateDisabled}
            className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed ${
              authority.external_authority_enabled ? 'bg-blue-500' : 'bg-slate-600'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                authority.external_authority_enabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
      )}

      {/* ppd status row */}
      <div className="flex flex-wrap gap-3 border-t border-slate-700/50 pt-3">
        <div className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${authority.ppd_active ? 'bg-amber-400' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-400">{t('system:power.authority.ppdActive')}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${authority.ppd_masked ? 'bg-emerald-400' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-400">{t('system:power.authority.ppdMasked')}</span>
        </div>
      </div>
    </div>
  );
}
