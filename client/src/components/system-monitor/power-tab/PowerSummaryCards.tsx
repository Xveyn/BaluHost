import { useTranslation } from 'react-i18next';
import { StatCard } from '../../ui/StatCard';
import { formatNumber } from '../../../lib/formatters';

interface PowerSummaryCardsProps {
  totalCurrentPower: number;
  onlineCount: number;
  deviceCount: number;
}

export function PowerSummaryCards({ totalCurrentPower, onlineCount, deviceCount }: PowerSummaryCardsProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
      <StatCard
        label={t('monitor.power.currentPower')}
        value={formatNumber(totalCurrentPower, 1)}
        unit="W"
        color="yellow"
        icon={<span className="text-yellow-400 text-base sm:text-xl">⚡</span>}
      />
      <StatCard
        label={t('monitor.power.onlineDevices', 'Online')}
        value={onlineCount}
        unit={`/ ${deviceCount}`}
        color="green"
        icon={<span className="text-green-400 text-base sm:text-xl">📊</span>}
      />
      <StatCard
        label={t('monitor.power.devices')}
        value={deviceCount}
        color="blue"
        icon={<span className="text-blue-400 text-base sm:text-xl">#</span>}
      />
    </div>
  );
}
