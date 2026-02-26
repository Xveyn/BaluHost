import { useTranslation } from 'react-i18next';
import { Activity, Smartphone, Monitor, CheckCircle, Link2 } from 'lucide-react';
import { DeviceCard } from './DeviceCard';
import type { Device } from '../../api/devices';

interface DevicesTabProps {
  devices: Device[];
  mobileDevices: Device[];
  desktopDevices: Device[];
  stats: { total: number; mobile: number; desktop: number; active: number };
  loading: boolean;
  error: string | null;
  onEdit: (device: Device) => void;
  onDelete: (device: Device) => void;
  onPair: () => void;
}

export function DevicesTab({
  mobileDevices,
  desktopDevices,
  stats,
  loading,
  error,
  onEdit,
  onDelete,
  onPair,
}: DevicesTabProps) {
  const { t } = useTranslation(['devices', 'common']);

  return (
    <>
      {/* Statistics Cards */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs sm:text-sm text-slate-400 truncate">{t('stats.totalDevices')}</p>
              <p className="mt-1 text-xl sm:text-2xl font-semibold text-white">{stats.total}</p>
            </div>
            <Activity className="h-6 w-6 sm:h-8 sm:w-8 text-sky-500 flex-shrink-0 ml-2" />
          </div>
        </div>

        <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs sm:text-sm text-slate-400 truncate">{t('stats.mobile')}</p>
              <p className="mt-1 text-xl sm:text-2xl font-semibold text-sky-400">{stats.mobile}</p>
            </div>
            <Smartphone className="h-6 w-6 sm:h-8 sm:w-8 text-sky-500 flex-shrink-0 ml-2" />
          </div>
        </div>

        <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs sm:text-sm text-slate-400 truncate">{t('stats.desktop')}</p>
              <p className="mt-1 text-xl sm:text-2xl font-semibold text-emerald-400">{stats.desktop}</p>
            </div>
            <Monitor className="h-6 w-6 sm:h-8 sm:w-8 text-emerald-500 flex-shrink-0 ml-2" />
          </div>
        </div>

        <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs sm:text-sm text-slate-400 truncate">{t('stats.active')}</p>
              <p className="mt-1 text-xl sm:text-2xl font-semibold text-green-400">{stats.active}</p>
            </div>
            <CheckCircle className="h-6 w-6 sm:h-8 sm:w-8 text-green-500 flex-shrink-0 ml-2" />
          </div>
        </div>
      </div>

      {error && (
        <div className="card border-red-900/60 bg-red-950/30 p-4">
          <p className="text-sm text-red-400">
            <strong>{t('error')}:</strong> {error}
          </p>
        </div>
      )}

      {loading ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
          <p className="text-sm text-slate-500">{t('loading')}</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Mobile Devices */}
          <div className="card border-slate-800/60 bg-slate-900/55">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{t('sections.mobileDevices')}</p>
                <h2 className="mt-2 text-xl font-semibold text-white">
                  {t('sections.smartphonesTablets', { count: mobileDevices.length })}
                </h2>
              </div>
            </div>

            {mobileDevices.length === 0 ? (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-sm text-slate-500">
                {t('empty.noMobileDevices')}
              </div>
            ) : (
              <div className="space-y-3">
                {mobileDevices.map((device) => (
                  <DeviceCard
                    key={device.id}
                    device={device}
                    colorTheme="sky"
                    onEdit={onEdit}
                    onDelete={onDelete}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Desktop Devices */}
          <div className="card border-slate-800/60 bg-slate-900/55">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{t('sections.desktopDevices')}</p>
                <h2 className="mt-2 text-xl font-semibold text-white">
                  {t('sections.baluDeskClients', { count: desktopDevices.length })}
                </h2>
              </div>
              <button
                onClick={onPair}
                className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-200 transition hover:border-emerald-500/50 hover:bg-emerald-500/20 touch-manipulation active:scale-95"
              >
                <Link2 className="h-4 w-4" />
                <span>{t('pairing.pairButton')}</span>
              </button>
            </div>

            {desktopDevices.length === 0 ? (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-sm text-slate-500">
                {t('empty.noDesktopClients')}
              </div>
            ) : (
              <div className="space-y-3">
                {desktopDevices.map((device) => (
                  <DeviceCard
                    key={device.id}
                    device={device}
                    colorTheme="emerald"
                    onEdit={onEdit}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
