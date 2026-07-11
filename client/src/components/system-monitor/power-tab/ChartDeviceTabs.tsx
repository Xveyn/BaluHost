import { useTranslation } from 'react-i18next';
import type { SmartDevice } from '../../../api/smart-devices';

interface ChartDeviceTabsProps {
  devices: SmartDevice[];
  selectedDeviceId: number | null;
  onSelect: (id: number | null) => void;
}

export function ChartDeviceTabs({ devices, selectedDeviceId, onSelect }: ChartDeviceTabsProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-2">
      <button
        onClick={() => onSelect(null)}
        className={`shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
          selectedDeviceId === null
            ? 'bg-blue-600 text-white'
            : 'bg-gray-700/50 text-gray-400 hover:text-gray-200'
        }`}
      >
        {t('monitor.power.total')}
      </button>
      {devices
        .filter(d => d.is_active && d.capabilities?.includes('power_monitor'))
        .map(device => (
          <button
            key={device.id}
            onClick={() => onSelect(device.id)}
            className={`shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              selectedDeviceId === device.id
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700/50 text-gray-400 hover:text-gray-200'
            }`}
          >
            {device.name}
          </button>
        ))}
    </div>
  );
}
