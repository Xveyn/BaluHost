/**
 * PowerStates -- presentational loading/error/empty states for PowerTab.
 */

import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

export function PowerLoading() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-blue-500" />
    </div>
  );
}

export function PowerError({ error }: { error: string }) {
  return <div className="text-red-400 text-center py-8">{error}</div>;
}

export function PowerEmptyState() {
  const { t } = useTranslation(['system', 'common']);

  return (
    <div className="text-center py-12">
      <svg
        className="mx-auto h-16 w-16 text-slate-600"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 10V3L4 14h7v7l9-11h-9z"
        />
      </svg>
      <p className="mt-4 text-slate-400">{t('monitor.power.noSmartDevices', 'No smart devices with power monitoring configured')}</p>
      <Link
        to="/smart-devices"
        className="inline-block mt-4 px-4 py-2 text-sm bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/40 rounded-lg transition-colors"
      >
        {t('monitor.power.configureSmartDevices', 'Configure Smart Devices')} →
      </Link>
    </div>
  );
}
