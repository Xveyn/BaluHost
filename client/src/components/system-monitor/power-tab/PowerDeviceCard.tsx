import { useTranslation } from 'react-i18next';
import type { SmartDevice } from '../../../api/smart-devices';
import { parseDevicePower } from './parseDevicePower';
import { formatNumber } from '../../../lib/formatters';

interface PowerDeviceCardProps {
  device: SmartDevice;
}

export function PowerDeviceCard({ device }: PowerDeviceCardProps) {
  const { t } = useTranslation(['system', 'common']);
  const { watts, voltage, currentA, energyToday } = parseDevicePower(device);

  return (
    <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
      <div className="flex items-center justify-between mb-3 sm:mb-4">
        <h3 className="text-base sm:text-lg font-semibold text-white">{device.name}</h3>
        <span className={`text-xs px-2 py-0.5 rounded-full ${device.is_online ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
          {device.is_online ? t('monitor.power.online', 'Online') : t('monitor.power.offline', 'Offline')}
        </span>
      </div>
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <div>
          <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.powerLabel')}</p>
          <p className="text-lg sm:text-xl font-semibold text-white">
            {watts != null ? formatNumber(watts, 1) : '-'} <span className="text-sm sm:text-base text-slate-400">W</span>
          </p>
        </div>
        <div>
          <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.voltage')}</p>
          <p className="text-lg sm:text-xl font-semibold text-white">
            {voltage != null ? formatNumber(voltage, 1) : '-'} <span className="text-sm sm:text-base text-slate-400">V</span>
          </p>
        </div>
        <div>
          <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.current')}</p>
          <p className="text-lg sm:text-xl font-semibold text-white">
            {currentA != null ? formatNumber(currentA, 3) : '-'} <span className="text-sm sm:text-base text-slate-400">A</span>
          </p>
        </div>
        <div>
          <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.today')}</p>
          <p className="text-lg sm:text-xl font-semibold text-white">
            {energyToday != null ? formatNumber(energyToday, 2) : '-'} <span className="text-sm sm:text-base text-slate-400">kWh</span>
          </p>
        </div>
      </div>
    </div>
  );
}
