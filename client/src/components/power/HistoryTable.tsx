/**
 * HistoryTable -- displays power profile change history.
 */

import type { ServicePowerProperty, PowerHistoryEntry } from '../../api/power-management';
import { formatClockSpeed } from '../../api/power-management';
import { PropertyBadge } from './PropertyBadge';
import { formatTimestamp } from './utils';

interface HistoryTableProps {
  entries: PowerHistoryEntry[];
  t: (key: string, options?: Record<string, unknown>) => string;
}

export function HistoryTable({ entries, t }: HistoryTableProps) {
  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 sm:p-6 text-center text-sm text-slate-400">
        {t('system:power.noHistory')}
      </div>
    );
  }

  return (
    <>
      {/* Desktop Table */}
      <div className="hidden lg:block overflow-hidden rounded-lg border border-slate-700/50">
        <table className="min-w-full divide-y divide-slate-700/50">
          <thead className="bg-slate-800/50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                {t('system:power.tableHeaders.timestamp')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                {t('system:power.tableHeaders.property')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                {t('system:power.tableHeaders.reason')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                {t('system:power.tableHeaders.frequency')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/30 bg-slate-900/30">
            {entries.map((entry, idx) => (
              <tr key={`${entry.timestamp}-${idx}`} className="hover:bg-slate-800/30">
                <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-300">
                  {formatTimestamp(entry.timestamp)}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <PropertyBadge property={entry.profile as ServicePowerProperty} size="sm" />
                </td>
                <td className="px-4 py-3 text-sm text-slate-300">
                  <span className="font-mono text-xs">{entry.reason}</span>
                  {entry.source && (
                    <span className="ml-2 text-slate-500">({entry.source})</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-400">
                  {entry.frequency_mhz ? formatClockSpeed(entry.frequency_mhz) : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="lg:hidden space-y-2">
        {entries.map((entry, idx) => (
          <div
            key={`${entry.timestamp}-${idx}`}
            className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3"
          >
            <div className="flex items-center justify-between gap-2 mb-2">
              <PropertyBadge property={entry.profile as ServicePowerProperty} size="sm" />
              <span className="text-xs text-slate-400">{formatTimestamp(entry.timestamp)}</span>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-slate-300 font-mono truncate">{entry.reason}</p>
              <div className="flex items-center justify-between text-xs">
                {entry.source && <span className="text-slate-500">({entry.source})</span>}
                <span className="text-slate-400 font-medium">
                  {entry.frequency_mhz ? formatClockSpeed(entry.frequency_mhz) : '-'}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
