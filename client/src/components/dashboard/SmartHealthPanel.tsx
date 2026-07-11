import { useTranslation } from 'react-i18next';
import type { SmartStatusResponse } from '../../api/smart';
import { computeSmartDeviceUsage } from './computeSmartDeviceUsage';
import { SmartDeviceCard } from './SmartDeviceCard';

interface SmartHealthPanelProps {
  smartData: SmartStatusResponse | null;
  smartLoading: boolean;
  smartError: string | null;
  smartMode: string | null;
  smartModeLoading: boolean;
  onToggleSmartMode: () => void;
  storageUsed: number;
}

export function SmartHealthPanel({
  smartData,
  smartLoading,
  smartError,
  smartMode,
  smartModeLoading,
  onToggleSmartMode,
  storageUsed,
}: SmartHealthPanelProps) {
  const { t } = useTranslation('dashboard');

  return (
    <div className="grid grid-cols-1 gap-6">
      <div className="card border-slate-800/50 bg-slate-900/55">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.32em] text-slate-500">{t('smart.title')}</p>
            <h2 className="mt-2 text-xl font-semibold text-white">{t('smart.subtitle')}</h2>
          </div>
          <div className="flex items-center gap-2 text-xs">
            {smartMode && (
              <button
                onClick={onToggleSmartMode}
                disabled={smartModeLoading}
                className="rounded-full border border-slate-700/70 bg-slate-800/50 px-3 py-1 text-slate-300 transition hover:border-sky-500/50 hover:bg-slate-700/50 hover:text-white disabled:opacity-50"
                title={t('smart.modeToggle.current', { mode: smartMode === 'mock' ? t('smart.modeToggle.mock') : t('smart.modeToggle.real') })}
              >
                {smartModeLoading ? '...' : (smartMode === 'mock' ? '🔄 Mock' : '🔄 Real')}
              </button>
            )}
            {smartLoading ? (
              <span className="rounded-full border border-slate-700 px-3 py-1 text-slate-400">{t('network.loading')}</span>
            ) : smartError ? (
              <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-1 text-rose-200">{t('smart.error')}</span>
            ) : (
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-emerald-200">{t('smart.healthy')}</span>
            )}
          </div>
        </div>
        <div className="mt-6">
          {smartLoading ? (
            <div className="flex h-52 items-center justify-center rounded-2xl border border-slate-800/60 bg-slate-900/60 text-sm text-slate-500">
              {t('smart.loading')}
            </div>
          ) : smartError ? (
            <div className="flex h-52 items-center justify-center rounded-2xl border border-rose-500/30 bg-rose-500/10 text-sm text-rose-200">
              {smartError}
            </div>
          ) : smartData && smartData.devices.length > 0 ? (
            <div className="space-y-3">
              {smartData.devices.map((device) => {
                const { usedBytes, usagePercent } = computeSmartDeviceUsage(device, smartData.devices, storageUsed);
                return (
                  <SmartDeviceCard key={device.serial} device={device} usedBytes={usedBytes} usagePercent={usagePercent} />
                );
              })}
            </div>
          ) : (
            <div className="flex h-52 items-center justify-center rounded-2xl border border-slate-800/60 bg-slate-900/60 text-sm text-slate-500">
              {t('smart.noDevices')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
