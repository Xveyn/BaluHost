/**
 * OS Sleep Settings Banner
 *
 * Read-only card at the top of the Sleep page. Surfaces OS-level sleep
 * triggers (logind, sleep.conf, masked targets) so users understand which
 * sleep behaviour BaluHost actually owns. No edit functionality.
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, Info, RefreshCw, ShieldAlert } from 'lucide-react';

import {
  getOsSleepSettings,
  type OsSleepIssue,
  type OsSleepReport,
  type OsSleepSeverity,
} from '../../api/sleep';

const ICON_FOR: Record<OsSleepSeverity, typeof AlertTriangle> = {
  info: Info,
  warning: AlertTriangle,
  error: ShieldAlert,
};

const COLOR_FOR: Record<OsSleepSeverity, string> = {
  info: 'text-slate-300',
  warning: 'text-amber-400',
  error: 'text-red-400',
};

function IssueLine({ issue }: { issue: OsSleepIssue }) {
  const { t } = useTranslation('system');
  const Icon = ICON_FOR[issue.severity];
  const colorClass = COLOR_FOR[issue.severity];
  const text = t(`sleep.osSettings.issue.${issue.key}`, { defaultValue: issue.message });
  return (
    <div className="flex items-start gap-2 text-sm">
      <Icon className={`h-4 w-4 shrink-0 mt-0.5 ${colorClass}`} />
      <div>
        <span className="text-slate-200">{text}</span>
        {issue.detail && (
          <p className="mt-0.5 text-xs text-slate-400">{issue.detail}</p>
        )}
      </div>
    </div>
  );
}

function DetailsTable({ report }: { report: OsSleepReport }) {
  const { t } = useTranslation('system');
  const rows: Array<[string, string]> = [];
  for (const [k, v] of Object.entries(report.logind)) rows.push([`logind.${k}`, v]);
  for (const [k, v] of Object.entries(report.sleep_conf)) rows.push([`sleep.${k}`, v]);
  for (const [k, v] of Object.entries(report.targets)) rows.push([`targets.${k}`, v]);
  return (
    <details className="mt-3 group">
      <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200 select-none">
        {t('sleep.osSettings.detailsToggle')}
      </summary>
      <div className="mt-2 space-y-1 pl-4 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span className="text-slate-500 font-mono">{k}</span>
            <span className="text-slate-300 font-mono">= {v}</span>
          </div>
        ))}
        {report.sources.length > 0 && (
          <div className="pt-2 text-slate-500">
            {t('sleep.osSettings.sources')}: {report.sources.join(', ')}
          </div>
        )}
      </div>
    </details>
  );
}

export function OsSleepSettingsBanner() {
  const { t } = useTranslation('system');
  const [report, setReport] = useState<OsSleepReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (force = false) => {
    if (force) setRefreshing(true);
    setError(null);
    try {
      const data = await getOsSleepSettings(force);
      setReport(data);
    } catch {
      setError(t('sleep.osSettings.loadFailed'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [t]);

  useEffect(() => {
    load(false);
  }, [load]);

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-5 w-1/3 bg-slate-700/50 rounded" />
          <div className="h-4 w-2/3 bg-slate-700/40 rounded" />
        </div>
      </div>
    );
  }

  // Hide entirely on unsupported platforms (no banner, no placeholder).
  if (report && !report.platform_supported && !error) {
    return null;
  }

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-medium text-white">{t('sleep.osSettings.title')}</h4>
        <button
          type="button"
          onClick={() => load(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-700/40 transition-colors disabled:opacity-60"
          aria-label={t('sleep.osSettings.refresh')}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          {t('sleep.osSettings.refresh')}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 text-sm">
          <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-red-400" />
          <span className="text-slate-200">{error}</span>
        </div>
      )}

      {report && !error && (
        <>
          {report.issues.length === 0 ? (
            <div className="flex items-start gap-2 text-sm">
              <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-emerald-400" />
              <span className="text-slate-200">{t('sleep.osSettings.allClear')}</span>
            </div>
          ) : (
            <div className="space-y-2">
              {report.issues.map((issue) => (
                <IssueLine key={issue.key} issue={issue} />
              ))}
            </div>
          )}
          <DetailsTable report={report} />
        </>
      )}
    </div>
  );
}
